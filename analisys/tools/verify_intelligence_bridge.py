"""Reutiliza app e fórmulas originais somente em leitura, sem criar API adicional."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.intelligence_bridge import climate_request
from src.nasa_schemas import DailyResponse


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and not any(s in {".git", ".venv", "__pycache__", ".pytest_cache"} for s in p.relative_to(root).parts)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intelligence-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--base-temperature-c", type=float, required=True, help="Hipótese explícita para a prova técnica, não calibração agronômica.")
    args = parser.parse_args()
    directory = args.intelligence_dir.resolve()
    before = snapshot(directory)
    sys.path.insert(0, str(directory))
    from app.main import create_app
    from app.core.config import Settings

    query = {"location": {"latitude": -16.5, "longitude": -49.3},
             "start_date": "2025-07-06", "end_date": "2025-10-03", "time_standard": "UTC",
             "parameters": ["T2M_MIN", "T2M_MAX", "PRECTOTCORR"], "require_complete": True}
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        response = client.post("/v1/data/nasa-power/daily", json=query)
        response.raise_for_status()
        daily = DailyResponse.model_validate(response.json())
    payload = climate_request(daily, "maize", args.base_temperature_c)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post("/v1/analysis/climate", json=payload)
        response.raise_for_status()
        result = response.json()
        assert result["status"] == "ok"
        indicators = result["result"]["indicators"]
        assert set(indicators) == {"I01", "I02"}
        old_gdd = client.post("/v1/indicators/gdd", json=payload["inputs"]["gdd"])
        old_rain = client.post("/v1/indicators/accumulated-rainfall", json=payload["inputs"]["rainfall"])
        old_gdd.raise_for_status()
        old_rain.raise_for_status()
        assert old_gdd.json()["result"]["value"] == indicators["I01"]["value"]
        assert old_rain.json()["result"]["windows"] == indicators["I02"]["windows"]
        schema = client.get("/openapi.json").json()
        assert len([p for p in schema["paths"] if p.startswith("/v1/analysis/")]) == 4
    assert before == snapshot(directory), "O projeto original não deve ser alterado."
    report = {"synthetic_weather": False, "caller_assumption": {"crop_id": "maize", "base_temperature_c": args.base_temperature_c},
              "source": daily.provenance[0].model_dump(mode="json"), "upstream_sha256": daily.traceability.upstream_sha256,
              "result": result, "original_files_unchanged": True, "legacy_results_match": True,
              "note": "Série NASA obtida pela API de dados e fornecida manualmente ao consumidor existente. Modo automático do consumidor não foi alterado."}
    (ROOT / ".runtime" / "intelligence-bridge-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "gdd": indicators["I01"]["value"],
                     "rainfall_windows": indicators["I02"]["windows"], "original_files_unchanged": True,
                     "legacy_results_match": True, "base_temperature_c_assumption": args.base_temperature_c}))


if __name__ == "__main__":
    main()
