"""Prova de viabilidade OPeNDAP: metadados e três horários de UMA célula, nunca campo global."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re

import httpx

BASE = "https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/fcast/tavg1_2d_slv_Nx.latest"
MAX_BYTES = 64 * 1024


def read_small(client, url):
    with client.stream("GET", url) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes(chunk_size=8192):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError("Resposta excede limite de 64 KiB; leitura encerrada.")
        return bytes(data).decode("utf-8"), len(data)


def block(das, name):
    return re.search(r"\b" + re.escape(name) + r"\s*\{(.*?)\}", das, re.S).group(1)


def axis(das, name, coordinate):
    text = block(das, name)
    if 'grads_mapping "linear"' not in text:
        raise ValueError("Eixo não linear; não selecionar célula por suposição.")
    first = float(re.search(r"minimum\s+([-\d.]+);", text).group(1))
    step = float(re.search(r"resolution\s+([-\d.]+);", text).group(1))
    size = int(re.search(r'grads_size "(\d+)"', text).group(1))
    index = min(size - 1, max(0, int(math.floor((coordinate - first) / step + .5))))
    return index, first + step * index, size, step


def select(das, dds, latitude, longitude, now):
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Coordenadas WGS84 inválidas.")
    match = re.search(r"Float32 t2m\[time = (\d+)\]\[lat = (\d+)\]\[lon = (\d+)\]", dds)
    if not match:
        raise ValueError("Dimensões t2m incompatíveis; consulta cancelada.")
    nt, ny, nx = map(int, match.groups())
    iy, lat, sy, dy = axis(das, "lat", latitude)
    ix, lon, sx, dx = axis(das, "lon", -180 if longitude == 180 else longitude)
    if (sy, sx) != (ny, nx):
        raise ValueError("Metadados inconsistentes.")
    text = block(das, "time")
    start = datetime.strptime(re.search(r'grads_min "([^"]+)"', text).group(1), "%H:%Mz%d%b%Y").replace(tzinfo=timezone.utc)
    step = int(re.search(r'grads_step "(\d+)mn"', text).group(1))
    first = max(0, math.ceil((now - start).total_seconds() / (step * 60)))
    last = first + 2
    if last >= nt:
        raise ValueError("Coleção latest não contém três horários futuros; não usar ciclo antigo como forecast.")
    return {"lat_index": iy, "lon_index": ix, "grid_latitude": lat, "grid_longitude": lon,
        "latitude_step_deg": dy, "longitude_step_deg": dx, "time_start_index": first, "time_end_index": last,
        "valid_times_from_metadata": [(start + timedelta(minutes=i * step)).isoformat() for i in range(first, last + 1)],
        "collection_start": start.isoformat(), "collection_end": (start + timedelta(minutes=(nt - 1) * step)).isoformat(),
        "constraint": f"t2m[{first}:1:{last}][{iy}:1:{iy}][{ix}:1:{ix}]"}


def probe(latitude, longitude):
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "requested_latitude": latitude,
        "requested_longitude": longitude, "source": BASE, "global_field_downloaded": False,
        "production_integration": False, "synthetic": False}
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        dds, a = read_small(client, BASE + ".dds")
        das, b = read_small(client, BASE + ".das")
        selection = select(das, dds, latitude, longitude, datetime.now(timezone.utc))
        text, c = read_small(client, BASE + ".ascii?" + selection["constraint"])
        if not text.startswith("t2m, [3][1][1]"):
            raise ValueError("Subset retornado não é o solicitado.")
        values = [float(v) for v in re.findall(r"^\[\d+\]\[0\],\s*([-+\d.eE]+)", text, re.M)]
        fill = float(re.search(r"_FillValue\s+([-+\d.eE]+);", block(das, "t2m")).group(1))
        if len(values) != 3 or any(not math.isfinite(v) or v == fill for v in values):
            raise ValueError("Subset sem três valores válidos.")
        # latest pode mudar entre consultas: não promover os tempos do DAS a ciclo verificado.
        report.update(transport_validated=True, selection=selection, raw_t2m=values,
            response_ascii=text, bytes_received={"dds": a, "das": b, "point_subset": c},
            metadata_sha256=hashlib.sha256((dds + das).encode()).hexdigest(),
            limitation="Tempos derivados dos metadados latest; fixar ciclo e validar mapas/semântica/unidades antes de produção.")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--latitude", type=float, default=-16.5)
    parser.add_argument("--longitude", type=float, default=-49.3)
    args = parser.parse_args()
    try:
        report = probe(args.latitude, args.longitude)
    except (httpx.HTTPError, ValueError, AttributeError, KeyError) as exc:
        report = {"transport_validated": False, "production_integration": False, "global_field_downloaded": False,
                  "error_type": type(exc).__name__, "checked_at": datetime.now(timezone.utc).isoformat()}
    target = Path(__file__).resolve().parents[1] / ".runtime/geos-fp-point-check.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("transport_validated", "production_integration", "global_field_downloaded", "bytes_received") if k in report}))


if __name__ == "__main__":
    main()
