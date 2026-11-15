"""Prova opt-in por HTTP. Sem credenciais, informa bloqueio e nunca fabrica previsão."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--probe-unauthenticated", action="store_true", help="Confirma somente a exigência de autenticação do endpoint oficial, sem enviar credenciais.")
    args = parser.parse_args()
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    end = start + timedelta(hours=2)
    payload = {"location": {"latitude": -16.5, "longitude": -49.3}, "start_time": start.isoformat(),
               "end_time": end.isoformat(), "parameters": ["temperature", "precipitation", "relative_humidity", "wind_speed"],
               "step_hours": 1, "source": "mix"}
    report = {"synthetic": False, "weather_data_validated": False}
    with httpx.Client(base_url=args.base_url, timeout=180, trust_env=False) as client:
        schema = client.get("/openapi.json")
        schema.raise_for_status()
        assert "/v1/data/meteomatics/forecast" in schema.json()["paths"]
        assert "/v1/data/nasa-power/daily" in schema.json()["paths"]
        assert len([p for p in schema.json()["paths"] if p.startswith("/v1/analysis/")]) == 4
        catalog = client.get("/v1/capabilities")
        catalog.raise_for_status()
        report["capability"] = next(c for c in catalog.json()["capabilities"] if c["id"] == "get_meteomatics_forecast")
        response = client.post("/v1/data/meteomatics/forecast", json=payload)
        report["http_status"] = response.status_code
        report["response"] = response.json()
        report["weather_data_validated"] = response.is_success
        if response.is_success:
            assert response.json()["provenance"][0]["kind"] == "operational_forecast"
    if args.probe_unauthenticated and not report["capability"]["credentials_configured"]:
        # Teste de acesso real sem autenticação; não representa consulta de previsão aprovada.
        url = "https://api.meteomatics.com/" + start.strftime("%Y-%m-%dT%H:%M:%SZ") + "/t_2m:C/-16.5,-49.3/json"
        try:
            with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
                probe = client.get(url, params={"source": "mix"})
                report["unauthenticated_probe"] = {"http_status": probe.status_code,
                    "authentication_required": probe.status_code in {401, 403}, "weather_data_validated": False}
        except httpx.HTTPError:
            report["unauthenticated_probe"] = {"network_error": True, "weather_data_validated": False}
    destination = Path(__file__).resolve().parents[1] / ".runtime/meteomatics-live-check.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"http_status": report["http_status"], "weather_data_validated": report["weather_data_validated"],
                      "credentials_configured": report["capability"]["credentials_configured"],
                      "error_code": report["response"].get("error", {}).get("code"),
                      "unauthenticated_probe": report.get("unauthenticated_probe")}))


if __name__ == "__main__":
    main()
