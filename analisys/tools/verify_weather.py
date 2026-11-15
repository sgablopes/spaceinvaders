"""Validação real HTTP + fallback induzido sem segredos; nunca imprime cabeçalhos de autenticação."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.meteomatics import Meteomatics
from src.open_meteo import OpenMeteo
from src.weather_service import Weather
from src.weather_schemas import WeatherRequest


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    now = datetime.now(timezone.utc)
    start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    day = now.date() + timedelta(days=1)
    report = {"checked_at": now.isoformat(), "weather_is_synthetic": False, "checks": []}
    with httpx.Client(base_url=base, timeout=180, trust_env=False) as client:
        def post(path, payload):
            r = client.post(path, json=payload)
            r.raise_for_status()
            return r.json()
        for name, location in (("BR", {"latitude": -16.5, "longitude": -49.3}),
                               ("US", {"latitude": 41.5, "longitude": -93.6})):
            hourly = {"location": location, "start_time": start.isoformat(), "end_time": (start + timedelta(hours=2)).isoformat(),
                "parameters": ["temperature", "precipitation", "relative_humidity", "wind_speed", "solar_radiation"], "require_complete": True}
            for provider in ("auto", "open_meteo", "meteomatics"):
                result = post("/v1/data/weather/forecast", {**hourly, "provider": provider})
                assert result["status"] == "ok" and result["result"]["points_complete"] == 3
                report["checks"].append({"case": name + "_hourly_" + provider, "response": result})
            daily = {"location": location, "start_time": (day + timedelta(days=1)).isoformat() + "T00:00:00Z",
                "end_time": (day + timedelta(days=2)).isoformat() + "T00:00:00Z", "step_hours": 24,
                "parameters": ["temperature_min", "temperature_max", "temperature_mean", "precipitation"], "require_complete": True}
            for provider in ("meteomatics", "open_meteo"):
                result = post("/v1/data/weather/forecast", {**daily, "provider": provider})
                assert result["result"]["points_complete"] == 2
                report["checks"].append({"case": name + "_daily_" + provider, "response": result})
            context = {"location": location, "start_date": day.isoformat(), "end_date": (day + timedelta(days=1)).isoformat(), "data_kind": "forecast", "timezone": "UTC"}
            analysis = post("/v1/analysis/climate", {"include": ["I03", "I05"], "inputs": {
                "dry_spell": {**context, "rain_threshold_mm": 1}, "thermal_stress": {**context,
                    "crop_id": "ECO_289", "ecocrop_crop_id": "ECO_289", "growth_stage": "not_stage_calibrated", "threshold_catalog_version": "local_preserved"}}})
            assert all(i["provenance"][0]["kind"] == "operational_forecast" for i in analysis["result"]["indicators"].values())
            report["checks"].append({"case": name + "_forecast_indicators", "response": analysis})
        # Falha induzida apenas no objeto local; mantém a conta/serviço em execução intactos.
        primary, backup = Meteomatics(username="", password="", retries=0), OpenMeteo()
        try:
            result = Weather(primary, backup).forecast(WeatherRequest.model_validate(daily))
            assert result.fallback_used and result.provider_used == "Open-Meteo"
            report["checks"].append({"case": "real_open_meteo_induced_missing_credentials",
                "primary_failure_is_controlled": True, "backup_weather_is_real": True, "response": result.model_dump(mode="json")})
        finally:
            primary.close()
            backup.close()
        # I08: chuva é forecast real; ETo/Kc/fluxos abaixo são hipóteses CONTROLADAS.
        water = {**context, "crop_id": "controlled_test", "growth_stage": "controlled_test", "kc_catalog_version": "controlled_test",
            "eto_reference": "CONTROLLED ETo, not field measurement", "kc": 1, "kc_reference": "CONTROLLED coefficient",
            "assumptions_reference": "CONTROLLED non-rain fluxes; no soil water stock claim", "series_kind": "simulation",
            "eto_series": [{"date": (day + timedelta(days=i)).isoformat(), "eto_mm_day": 4} for i in range(2)],
            "daily_fluxes": [{"date": (day + timedelta(days=i)).isoformat(), "irrigation_mm": 0, "capillary_rise_mm": 0, "runoff_mm": 0, "deep_percolation_mm": 0} for i in range(2)]}
        answer = post("/v1/analysis/water", {"include": ["I08"], "inputs": {"water_balance": water}})
        report["checks"].append({"case": "I08_real_rain_controlled_other_inputs", "response": answer})
        assert client.get("/health").json()["status"] == "ok"
    target = Path(__file__).resolve().parents[1] / ".runtime/weather-live-check.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": [c["case"] for c in report["checks"]], "report": str(target)}))


if __name__ == "__main__":
    main()
