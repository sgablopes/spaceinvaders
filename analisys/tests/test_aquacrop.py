"""Motor científico real; clima e hipóteses dos testes são SINTÉTICOS, sem chamadas externas."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from src.main import create_app
from src.aquacrop_service import SLOTS, WEATHER_PARAMETERS
from src.nasa_power import NasaPower
from src.nasa_schemas import DailyRequest, DEFAULT_PARAMETERS
from src.fao56_eto import daily_eto
from src.vendor.intelligence.core.errors import ServiceError
from test_nasa import synthetic_response

ROOT = Path(__file__).resolve().parents[1]
PATH = "/v1/simulations/aquacrop"


def scenario():
    start = date(2024, 10, 1)
    return {"scenario_id": "controlled_maize", "start_date": str(start), "end_date": str(start + timedelta(days=150)),
        "crop": "Maize", "location": {"latitude": -16.5, "longitude": -49.3},
        "soil": {"preset": "SandyLoam", "depth_m": 2.4, "reference": "synthetic scenario using library soil", "kind": "assumed_engine_preset"},
        "initial_water": {"method": "FC", "reference": "assumed test", "kind": "assumed"},
        "co2": {"concentration_ppm": 369.41, "reference": "engine reference baseline; not measured atmospheric concentration"},
        "management": {"irrigation": "rainfed", "reference": "controlled test"}, "assumptions_reference": "controlled synthetic test inputs",
        "weather": {"source": "caller_supplied", "reference": "synthetic weather for engine testing", "daily": [
            {"date": str(start + timedelta(days=i)), "tmin_c": 15, "tmax_c": 30, "precipitation_mm": 5, "eto_mm_day": 4} for i in range(151)]}}


class FAOTests(unittest.TestCase):
    def test_fao56_published_example_18_and_radiation(self):
        result = daily_eto(date(2001, 7, 6), 50.8, 100, 12.3, 21.5, 2.078, 22.07, 100.1, ea_kpa=1.409)
        self.assertAlmostEqual(result["eto_mm_day"], 3.88, delta=0.01)
        self.assertAlmostEqual(result["net_radiation_mj_m2_day"], 13.28, delta=0.01)
        self.assertAlmostEqual(result["extraterrestrial_radiation_mj_m2_day"], 41.09, delta=0.01)
        self.assertFalse(result["cloudiness_ratio_bounded"])

    def test_eto_rejects_inconsistent_inputs_and_exposes_cloudiness_bounds(self):
        bounded = daily_eto(date(2025, 10, 1), -16.5, 800, 15, 30, 2, 1, 92, dewpoint_c=10)
        self.assertTrue(bounded["cloudiness_ratio_bounded"])
        self.assertEqual(bounded["rs_rso_cloudiness_ratio"], 0.3)
        for kwargs in ({"wind_2m_m_s": -1}, {"pressure_kpa": 0}, {"rs_mj_m2_day": float("nan")}, {"dewpoint_c": 40}):
            inputs = dict(day=date(2025, 10, 1), latitude=-16.5, elevation_m=800, tmin_c=15, tmax_c=30,
                wind_2m_m_s=2, rs_mj_m2_day=20, pressure_kpa=92, dewpoint_c=10)
            inputs.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ServiceError): daily_eto(**inputs)


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        cls.calls, cls.missing = [], False
        def respond(request):
            cls.calls.append(request)
            q = request.url.params
            query = DailyRequest(location={"latitude": float(q["latitude"]), "longitude": float(q["longitude"])},
                start_date=f"{q['start'][:4]}-{q['start'][4:6]}-{q['start'][6:]}",
                end_date=f"{q['end'][:4]}-{q['end'][4:6]}-{q['end'][6:]}", parameters=q["parameters"].split(","), time_standard="UTC")
            raw = synthetic_response(query)
            raw["geometry"]["coordinates"].append(800)
            for d in raw["properties"]["parameter"].get("PRECTOTCORR", {}): raw["properties"]["parameter"]["PRECTOTCORR"][d] = 5
            if cls.missing:
                raw["properties"]["parameter"]["WS2M"][query.start_date.strftime("%Y%m%d")] = -999
            return httpx.Response(200, json=raw)
        cls.nasa = NasaPower(httpx.Client(transport=httpx.MockTransport(respond)), retries=0)
        cls.client = TestClient(create_app(ROOT, Path(cls.temp.name) / "catalog.sqlite3", nasa=cls.nasa))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.temp.cleanup()

    def setUp(self):
        self.calls.clear()
        self.nasa.cache.clear()
        type(self).missing = False

    def test_real_engine_complete_season_and_water_budget(self):
        response = self.client.post(PATH, json=scenario())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["engine"]["version"], "3.0.12")
        self.assertFalse(body["engine"]["official_fao_7_3"])
        result, budget = body["result"], body["result"]["water_balance"]
        self.assertTrue(result["crop_mature"])
        self.assertGreater(result["dry_yield_t_ha"], 0)
        self.assertEqual(len(result["daily"]), result["simulated_days"])
        self.assertEqual(result["daily"][-1]["date"], result["last_simulated_date"])
        self.assertAlmostEqual(budget["initial_soil_water_mm"], 528)
        self.assertAlmostEqual(budget["precipitation_mm"], 5 * result["simulated_days"])
        self.assertLess(abs(budget["residual_mm"]), 1e-6)
        self.assertTrue(all(abs(d["water_balance_residual_mm"]) < 1e-6 for d in result["daily"]))
        self.assertEqual(body["quality"]["kind"], "scenario")
        self.assertFalse(body["quality"]["field_validated"])
        self.assertEqual(self.calls, [])
        self.assertEqual(response.headers["X-Request-ID"], body["traceability"]["request_id"])

    def test_replay_is_deterministic_and_soil_assumption_affects_storage(self):
        payload = scenario()
        first = self.client.post(PATH, json=payload).json()
        replay = self.client.post(PATH, json=payload).json()
        self.assertEqual(first["traceability"]["result_sha256"], replay["traceability"]["result_sha256"])
        payload["soil"]["preset"] = "Loam"
        other = self.client.post(PATH, json=payload)
        self.assertEqual(other.status_code, 200, other.text)
        self.assertNotEqual(first["result"]["water_balance"]["initial_soil_water_mm"], other.json()["result"]["water_balance"]["initial_soil_water_mm"])

    def test_automatic_nasa_fao56_bridge_and_default_nasa_contract(self):
        payload = scenario()
        payload["weather"] = {"source": "nasa_power", "reference": "synthetic NASA mock only"}
        response = self.client.post(PATH, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(set(self.calls[0].url.params["parameters"].split(",")), set(WEATHER_PARAMETERS))
        self.assertEqual(body["provenance"][0]["provider"], "NASA POWER")
        self.assertEqual(body["provenance"][1]["elevation_source"], "NASA POWER geometry")
        self.assertTrue(body["inputs"]["eto_diagnostics"])
        self.assertTrue(all(d["eto_mm_day"] >= .1 for d in body["weather"]))
        original = DailyRequest(location=payload["location"], start_date="2024-10-01", end_date="2024-10-03")
        self.assertEqual(original.parameters, DEFAULT_PARAMETERS)

    def test_missing_nasa_input_stops_before_engine(self):
        type(self).missing = True
        payload = scenario()
        payload["weather"] = {"source": "nasa_power", "reference": "synthetic mock with missing wind"}
        with patch("src.aquacrop_service.subprocess.run") as worker:
            response = self.client.post(PATH, json=payload)
        self.assertEqual(response.status_code, 404, response.text)
        worker.assert_not_called()
        self.assertNotIn("dry_yield_t_ha", response.text)

    def test_request_daily_integrity_and_required_assumptions(self):
        for mutation in (lambda p: p["weather"]["daily"].pop(),
                         lambda p: p["weather"]["daily"].__setitem__(0, deepcopy(p["weather"]["daily"][1])),
                         lambda p: p["weather"]["daily"][0].update(eto_mm_day=0),
                         lambda p: p["weather"]["daily"][0].update(tmin_c=35),
                         lambda p: p["soil"].update(kind="measured"),
                         lambda p: p["soil"].update(depth_m=1.2),
                         lambda p: p["co2"].update(concentration_ppm=True),
                         lambda p: p["management"].update(irrigation="automatic"),
                         lambda p: p.update(crop="cassava"),
                         lambda p: p.pop("initial_water")):
            payload = scenario()
            mutation(payload)
            with self.subTest(mutation=mutation):
                r = self.client.post(PATH, json=payload)
                self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(self.calls, [])

    def test_short_run_does_not_report_partial_yield_as_harvest(self):
        payload = scenario()
        payload["end_date"] = "2024-10-10"
        payload["weather"]["daily"] = payload["weather"]["daily"][:10]
        result = self.client.post(PATH, json=payload)
        self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(result.json()["error"]["code"], "SEASON_INCOMPLETE")
        self.assertNotIn("dry_yield_t_ha", result.text)

    def test_timeout_failure_and_busy_do_not_return_results(self):
        with patch("src.aquacrop_service.subprocess.run", side_effect=subprocess.TimeoutExpired("test", 1)):
            response = self.client.post(PATH, json=scenario())
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"]["code"], "SIMULATION_TIMEOUT")
        for failure in ("ENGINE_DEPENDENCY_MISSING", "WATER_BALANCE_NOT_CLOSED", "ENGINE_EXECUTION_FAILED"):
            with patch("src.aquacrop_service.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"error": failure}))):
                response = self.client.post(PATH, json=scenario())
            self.assertEqual(response.status_code, 503 if failure == "ENGINE_DEPENDENCY_MISSING" else 502)
            self.assertNotIn("dry_yield_t_ha", response.text)
        SLOTS.acquire()
        try: self.assertEqual(self.client.post(PATH, json=scenario()).status_code, 429)
        finally: SLOTS.release()

    def test_worker_does_not_receive_service_credentials(self):
        with patch.dict("os.environ", {"METEOMATICS_PASSWORD": "synthetic-do-not-forward"}):
            with patch("src.aquacrop_service.subprocess.run", return_value=SimpleNamespace(returncode=1, stdout="")) as call:
                self.client.post(PATH, json=scenario())
        env = call.call_args.kwargs["env"]
        self.assertNotIn("METEOMATICS_PASSWORD", env)
        self.assertEqual(env["DEVELOPMENT"], "True")

    def test_schema_discovery_preserved_routes_and_private_errors(self):
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(schema["paths"][PATH]["post"]["operationId"], "simulate_aquacrop")
        self.assertIn("dry_yield_t_ha", schema["components"]["schemas"]["SimulationResult"]["properties"])
        self.assertEqual(len([p for p in schema["paths"] if p.startswith("/v1/analysis/")]), 4)
        self.assertIn("/v1/data/weather/forecast", schema["paths"])
        caps = self.client.get("/v1/capabilities").json()["capabilities"]
        self.assertTrue(any(c["id"] == "simulate_aquacrop" for c in caps))
        self.assertEqual(self.client.get("/api/v1/aquacrop/clima_diario").json()["total"], 0)
        invalid = self.client.post(PATH, json={**scenario(), "password": "synthetic-do-not-echo"})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("synthetic-do-not-echo", invalid.text)


if __name__ == "__main__": unittest.main()
