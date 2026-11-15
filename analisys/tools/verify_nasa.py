"""Smoke HTTP opt-in, NASA real: BR, exterior, período recente e cache."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import httpx


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    recent_end = datetime.now(timezone.utc).date() - timedelta(days=8)
    cases = [
        ("br_historical", {"latitude": -16.5, "longitude": -49.3}, "2025-10-01", "2025-10-03"),
        ("us_historical", {"latitude": 41.5, "longitude": -93.6}, "2025-10-01", "2025-10-03"),
        ("br_recent", {"latitude": -16.5, "longitude": -49.3},
         (recent_end - timedelta(days=2)).isoformat(), recent_end.isoformat()),
    ]
    report = {"synthetic": False, "checks": []}
    with httpx.Client(base_url=base, timeout=120) as client:
        for path in ("/health", "/docs", "/openapi.json", "/v1/capabilities"):
            response = client.get(path)
            response.raise_for_status()
        for label, location, start, end in cases:
            payload = {"location": location, "start_date": start, "end_date": end, "time_standard": "UTC"}
            response = client.post("/v1/data/nasa-power/daily", json=payload)
            item = {"case": label, "http_status": response.status_code, "response": response.json()}
            report["checks"].append(item)
            # Histórico deve ser consultável; recente pode ser indisponível, sem simular sucesso.
            if label != "br_recent":
                response.raise_for_status()
            if response.is_success:
                assert response.json()["result"]["days_expected"] == 3
                repeated = client.post("/v1/data/nasa-power/daily", json=payload)
                repeated.raise_for_status()
                assert repeated.json()["cache"]["hit"]
                item["repeated_cache_hit"] = True
    target = Path(__file__).resolve().parents[1] / ".runtime" / "nasa-live-check.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checks": [{"case": c["case"], "http_status": c["http_status"],
                     "status": c["response"].get("status"), "days_complete": c["response"].get("result", {}).get("days_complete"),
                     "cache_hit_verified": c.get("repeated_cache_hit", False)} for c in report["checks"]]}))


if __name__ == "__main__":
    main()
