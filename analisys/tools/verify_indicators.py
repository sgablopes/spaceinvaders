"""HTTP real NASA e cenários explicitamente controlados; sem credenciais no cliente."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import httpx


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": [],
              "forecast_real_validated": False}
    context = {"start_date": "2025-10-01", "end_date": "2025-10-03", "timezone": "UTC"}
    with httpx.Client(base_url=base, timeout=180) as client:
        def post(path, payload):
            r = client.post(path, json=payload)
            r.raise_for_status()
            return r.json()

        for label, location in (("BR", {"latitude": -16.5, "longitude": -49.3}),
                                ("US", {"latitude": 41.5, "longitude": -93.6})):
            weather = post("/v1/data/nasa-power/daily", {"location": location,
                "start_date": context["start_date"], "end_date": context["end_date"],
                "parameters": ["PRECTOTCORR", "T2M_MIN", "T2M_MAX"], "time_standard": "UTC", "require_complete": True})
            inputs = {"dry_spell": {**context, "location": location, "rain_threshold_mm": 1},
                "thermal_stress": {**context, "location": location, "crop_id": "ECO_289",
                    "growth_stage": "not_stage_calibrated", "threshold_catalog_version": "local_preserved",
                    "ecocrop_crop_id": "ECO_289"}}
            automatic = post("/v1/analysis/climate", {"include": ["I03", "I05"], "inputs": inputs})
            manual = deepcopy(inputs)
            manual["dry_spell"]["daily_precipitation"] = [{"date": r["date"], "precipitation_mm": r["precip_mm_day"]} for r in weather["result"]["series"]]
            manual["thermal_stress"]["daily_temperatures"] = [{"date": r["date"], "tmin_c": r["tmin_c"], "tmax_c": r["tmax_c"]} for r in weather["result"]["series"]]
            supplied = post("/v1/analysis/climate", {"include": ["I03", "I05"], "inputs": manual})
            for identifier in ("I03", "I05"):
                a = automatic["result"]["indicators"][identifier]
                b = supplied["result"]["indicators"][identifier]
                assert a["value"] == b["value"] and a["series"] == b["series"]
                assert a["provenance"][0]["kind"] == "modeled_estimate"
            report["checks"].append({"case": label, "weather_is_synthetic": False,
                "threshold_choice": "1 mm explicit; ECOCROP species envelope, not damage",
                "manual_and_automatic_match": True, "response": automatic})

        # ETo, fluxos e valores econômicos abaixo são controlados, não dados de campo.
        dates = ["2025-10-01", "2025-10-02", "2025-10-03"]
        etc = {**context, "crop_id": "asparagus", "growth_stage": "mid",
            "kc_catalog_version": "local_preserved", "series_kind": "simulation",
            "kc_selection": {"record_id": "FAO56-25-61-197-03", "parameter": "kc_mid"},
            "eto_reference": "CONTROLLED TEST: ETo synthetic, not a forecast",
            "eto_series": [{"date": d, "eto_mm_day": e} for d, e in zip(dates, (4, 0, 5))]}
        balance = {**deepcopy(etc), "assumptions_reference": "CONTROLLED TEST: all fluxes synthetic",
            "daily_fluxes": [{"date": d, "precipitation_mm": 5, "irrigation_mm": 1,
                "capillary_rise_mm": 0, "runoff_mm": .5, "deep_percolation_mm": .5} for d in dates]}
        water = post("/v1/analysis/water", {"include": ["I07", "I08"], "inputs": {
            "crop_evapotranspiration": etc, "water_balance": balance}})
        assert water["result"]["indicators"]["I07"]["value"] == 9
        assert water["result"]["indicators"]["I08"]["value"] == 6
        economic = post("/v1/analysis/economics", {"include": ["I14"], "inputs": {"crop_margin": {
            **context, "crop_id": "declared_test", "area_ha": 2, "expected_yield_t_per_ha": 3,
            "price_per_t": 1000, "cost_per_ha": 2000, "currency": "BRL",
            "assumptions_reference": "CONTROLLED TEST: no market observations"}}})
        assert economic["result"]["indicators"]["I14"]["value"] == 2000
        report["checks"].append({"case": "controlled_inputs_only", "eto_fluxes_prices_are_synthetic": True,
                                "water": water, "economics": economic})
        start = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        probe = client.post("/v1/analysis/climate", json={"include": ["I03"], "inputs": {"dry_spell": {
            "start_date": start, "end_date": start, "location": {"latitude": -16.5, "longitude": -49.3},
            "rain_threshold_mm": 1, "data_kind": "forecast"}}})
        if probe.status_code == 503:
            report["forecast_dependency"] = probe.json()["error"]["code"]
        else:
            probe.raise_for_status()
            report["forecast_real_validated"] = True
            report["forecast_provider"] = probe.json()["result"]["indicators"]["I03"]["provenance"][0]["provider"]
            report["forecast_response"] = probe.json()
        assert client.get("/health").json()["status"] == "ok"
    target = Path(__file__).resolve().parents[1] / ".runtime/indicators-live-check.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": [c["case"] for c in report["checks"]],
        "forecast_real_validated": report["forecast_real_validated"],
        "forecast_dependency": report.get("forecast_dependency"), "report": str(target)}))


if __name__ == "__main__":
    main()
