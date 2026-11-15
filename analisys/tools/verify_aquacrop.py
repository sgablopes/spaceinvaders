"""Prova HTTP real: NASA → ETo FAO-56 → AquaCrop-OSPy, hipóteses explicitamente declaradas."""
import json
from pathlib import Path
import sys
import httpx


def payload():
    return {"scenario_id": "maize_nasa_2024", "start_date": "2024-10-01", "end_date": "2025-05-28", "crop": "Maize",
        "location": {"latitude": -16.5, "longitude": -49.3},
        "weather": {"source": "nasa_power", "reference": "NASA POWER UTC; ETo FAO56 PM with documented ASCE cloudiness bounds"},
        "soil": {"preset": "SandyLoam", "depth_m": 2.4, "reference": "Generic engine preset; NOT measured/geolocated soil", "kind": "assumed_engine_preset"},
        "initial_water": {"method": "FC", "reference": "ASSUMED field capacity at planting, not measured", "kind": "assumed"},
        "co2": {"concentration_ppm": 369.41, "reference": "Engine reference CO2 baseline; NOT observed 2024 atmospheric concentration"},
        "management": {"irrigation": "rainfed", "reference": "Declared rainfed scenario, not actual farmer management record"},
        "assumptions_reference": "Generic library Maize, uncalibrated crop/soil; simulation is not observed field productivity"}


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    report = {"synthetic_weather": False, "soil_crop_management_are_assumptions": True, "request": payload()}
    with httpx.Client(base_url=base, timeout=240, trust_env=False) as client:
        response = client.post("/v1/simulations/aquacrop", json=report["request"])
        response.raise_for_status()
        result = response.json()
        assert result["engine"]["name"] == "AquaCrop-OSPy" and result["engine"]["version"] == "3.0.12"
        assert result["engine"]["official_fao_7_3"] is False
        assert result["quality"]["engine_executed"] and not result["quality"]["field_validated"]
        assert result["result"]["crop_mature"] and result["result"]["dry_yield_t_ha"] > 0
        assert abs(result["result"]["water_balance"]["residual_mm"]) < 1e-4
        assert result["provenance"][0]["provider"] == "NASA POWER"
        report["response"] = result
        # Reproduz com a MESMA série real explícita, mantendo os demais parâmetros.
        replay = payload()
        replay["scenario_id"] = "maize_replay_same_nasa_series"
        replay["weather"] = {"source": "caller_supplied", "reference": "Replay of the exact real NASA/FAO series above", "daily": result["weather"]}
        replay_response = client.post("/v1/simulations/aquacrop", json=replay)
        replay_response.raise_for_status()
        assert replay_response.json()["traceability"]["result_sha256"] == result["traceability"]["result_sha256"]
        report["replay_matches"] = True
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/api/v1/aquacrop/clima_diario").json()["total"] == 0
    destination = Path(__file__).resolve().parents[1] / ".runtime/aquacrop-http-check.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"engine": result["engine"]["name"], "version": result["engine"]["version"],
        "simulated_days": result["result"]["simulated_days"], "dry_yield_t_ha_simulated_scenario": result["result"]["dry_yield_t_ha"],
        "water_balance_residual_mm": result["result"]["water_balance"]["residual_mm"], "replay_matches": True,
        "report": str(destination)}))


if __name__ == "__main__": main()
