"""Prova HTTP real NASA → cálculos, inteiramente no container único de analisys."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import httpx


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    report = {"synthetic_weather": False, "base_temperature_c_assumption": 10, "checks": []}
    recent = datetime.now(timezone.utc).date() - timedelta(days=8)
    with httpx.Client(base_url=base, timeout=180) as client:
        schema = client.get("/openapi.json")
        schema.raise_for_status()
        assert len([p for p in schema.json()["paths"] if p.startswith("/v1/analysis/")]) == 4
        for case, location, end in (
            ("BR", {"latitude": -16.5, "longitude": -49.3}, "2025-10-03"),
            ("US", {"latitude": 41.5, "longitude": -93.6}, "2025-10-03"),
            ("BR_recent", {"latitude": -16.5, "longitude": -49.3}, recent.isoformat()),
        ):
            finish = datetime.fromisoformat(end).date()
            start = (finish - timedelta(days=2)).isoformat()
            payload = {"include": ["I01", "I02"], "inputs": {
                "gdd": {"location": location, "crop_id": "maize", "start_date": start,
                        "end_date": end, "base_temperature_c": 10, "timezone": "UTC"},
                "rainfall": {"location": location, "reference_date": end, "day_basis": "UTC"}}}
            response = client.post("/v1/analysis/climate", json=payload)
            response.raise_for_status()
            body = response.json()
            assert body["status"] == "ok", body
            indicators = body["result"]["indicators"]
            assert all(item["provenance"][0]["kind"] == "modeled_estimate" for item in indicators.values())
            for slug, field, identifier in (("gdd", "gdd", "I01"), ("accumulated-rainfall", "rainfall", "I02")):
                legacy = client.post("/v1/indicators/" + slug, json=payload["inputs"][field])
                legacy.raise_for_status()
                assert legacy.json()["result"]["value"] == indicators[identifier]["value"]
            report["checks"].append({"case": case, "http_status": response.status_code, "response": body,
                                     "legacy_values_match": True})
        # Compatibilidade dos endpoints de dados já entregues.
        assert client.get("/api/v1/ecocrop/culturas?limit=1").json()["total"] == 2568
        assert client.get("/health").json()["status"] == "ok"
    target = Path(__file__).resolve().parents[1] / ".runtime/automatic-indicators-check.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checks": [{"case": c["case"], "http_status": c["http_status"],
        "gdd": c["response"]["result"]["indicators"]["I01"]["value"],
        "rainfall_90_days_mm": c["response"]["result"]["indicators"]["I02"]["value"],
        "legacy_values_match": True} for c in report["checks"]], "base_temperature_c_assumption": 10}))


if __name__ == "__main__":
    main()
