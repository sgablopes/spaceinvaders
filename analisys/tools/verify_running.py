"""Verifica por HTTP uma instância local já iniciada; inclui duas consultas GAEZ reais."""
import json
from pathlib import Path
import sys
from time import perf_counter

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    report = {"base_url": base_url, "checks": []}
    with httpx.Client(base_url=base_url, timeout=90) as client:
        checks = [
            ("/health", {}, "status", "ok"),
            ("/api/v1/ecocrop/culturas", {"limit": 1}, "total", 2568),
            ("/api/v1/ecocrop/requisitos", {"filtros": '{"crop_id":"ECO_289"}'}, "total", 1),
            ("/api/v1/fao56/indice_atomico", {"limit": 1}, "total", 3097),
            ("/api/v1/conhecimento/evidencias", {"limit": 1}, "total", 249),
            ("/api/v1/aquacrop/clima_diario", {}, "total", 0),
        ]
        for path, params, key, expected in checks:
            started = perf_counter()
            response = client.get(path, params=params)
            response.raise_for_status()
            assert response.json()[key] == expected, path
            report["checks"].append({"path": path, "status": response.status_code,
                                     "elapsed_ms": round((perf_counter() - started) * 1000, 2)})
        schema = client.get("/openapi.json")
        schema.raise_for_status()
        assert "/api/v1/gaez/point" in schema.json()["paths"]
        for crop in ("MZE", "SOY"):
            layer = f"DATA/GAEZ-V5/MAPSET/RES05-SIX/GAEZ-V5.RES05-SIX.HP0120.AGERA5.HIST.{crop}.HRLM.tif"
            response = client.get("/api/v1/gaez/point", params={"layer": layer, "latitude": -16.5, "longitude": -49.3})
            report["checks"].append({"path": "/api/v1/gaez/point", "crop": crop,
                                     "status": response.status_code, "response": response.json()})
            response.raise_for_status()
    (root / ".runtime" / "http-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
