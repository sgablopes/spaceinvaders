"""Regressão do núcleo reaproveitado e conexão NASA; dados externos aqui são sintéticos."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
import httpx

from src.main import create_app
from src.nasa_power import NasaPower
from src.nasa_schemas import DailyRequest
from test_nasa import synthetic_response

ROOT = Path(__file__).resolve().parents[1]
LOCATION = {"latitude": -16.5, "longitude": -49.3}
AUTO_GDD = {"location": LOCATION, "crop_id": "maize", "start_date": "2025-10-01",
            "end_date": "2025-10-03", "base_temperature_c": 10, "timezone": "UTC"}
AUTO_RAIN = {"location": LOCATION, "reference_date": "2025-10-03", "day_basis": "UTC"}


def manual_gdd():
    return {**AUTO_GDD, "daily_temperatures": [
        {"date": "2025-10-01", "tmax_c": 30, "tmin_c": 14, "data_kind": "simulation"},
        {"date": "2025-10-02", "tmax_c": 18, "tmin_c": 0, "data_kind": "simulation"},
        {"date": "2025-10-03", "tmax_c": 22, "tmin_c": 10, "data_kind": "simulation"}]}


def manual_rain():
    return {**AUTO_RAIN, "source_kind": "simulation", "daily_precipitation": [
        {"date": (date(2025, 7, 6) + timedelta(days=i)).isoformat(), "precipitation_mm": 1} for i in range(90)]}


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        cls.calls = []
        cls.failure = None
        cls.missing = False

        def respond(request):
            cls.calls.append(request)
            if cls.failure:
                return httpx.Response(cls.failure)
            params = request.url.params
            query = DailyRequest(location={"latitude": float(params["latitude"]), "longitude": float(params["longitude"])},
                start_date=date.fromisoformat(params["start"][:4] + "-" + params["start"][4:6] + "-" + params["start"][6:]),
                end_date=date.fromisoformat(params["end"][:4] + "-" + params["end"][4:6] + "-" + params["end"][6:]),
                parameters=params["parameters"].split(","), time_standard=params["time-standard"])
            raw = synthetic_response(query)
            if cls.missing:
                first = next(iter(raw["properties"]["parameter"].values()))
                first[next(iter(first))] = -999
            return httpx.Response(200, json=raw)

        cls.nasa = NasaPower(httpx.Client(transport=httpx.MockTransport(respond)), retries=0)
        cls.client = TestClient(create_app(ROOT, Path(cls.temp.name) / "catalog.sqlite3", nasa=cls.nasa))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.temp.cleanup()

    def setUp(self):
        type(self).failure = None
        type(self).missing = False
        self.calls.clear()
        self.nasa.cache.clear()

    def post(self, include, inputs):
        return self.client.post("/v1/analysis/climate", json={"include": include, "inputs": inputs})

    def test_manual_results_and_no_network_unchanged(self):
        response = self.post(["I01", "I02"], {"gdd": manual_gdd(), "rainfall": manual_rain()})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"]["indicators"]["I01"]["value"], 18)
        self.assertEqual([w["total_mm"] for w in result["result"]["indicators"]["I02"]["windows"]], [7, 15, 30, 90])
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(result["provenance"][0]["provider"], "caller_supplied")
        self.assertEqual(result["traceability"]["request_id"], response.headers["X-Request-ID"])
        for path, body, identifier in (("gdd", manual_gdd(), "I01"), ("accumulated-rainfall", manual_rain(), "I02")):
            legacy = self.client.post("/v1/indicators/" + path, json=body)
            self.assertEqual(legacy.status_code, 200)
            self.assertEqual(legacy.json()["result"]["value"], result["result"]["indicators"][identifier]["value"])

    def test_automatic_independent_queries_and_true_provenance(self):
        response = self.post(["I01", "I02"], {"gdd": AUTO_GDD, "rainfall": AUTO_RAIN})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(self.calls), 2)
        gdd = body["result"]["indicators"]["I01"]
        rain = body["result"]["indicators"]["I02"]
        self.assertEqual(gdd["value"], 37.5)  # Fixture: 3 × ((30+15)/2−10).
        self.assertEqual(gdd["method"]["name"], "simple_average_no_upper_cap")
        self.assertEqual(gdd["series"][0]["data_kind"], "modeled_estimate")
        self.assertEqual(rain["source_type"], "nasa_power")
        self.assertEqual(rain["source_kind"], "modeled_estimate")
        self.assertEqual(rain["value"], 0)  # Zero é valor válido da fixture, não fallback.
        self.assertEqual(self.calls[0].url.params["parameters"], "T2M_MAX,T2M_MIN")
        self.assertEqual(self.calls[1].url.params["parameters"], "PRECTOTCORR")
        self.assertEqual(self.calls[1].url.params["start"], "20250706")
        for item in (gdd, rain):
            self.assertEqual(item["provenance"][0]["provider"], "NASA POWER")
            self.assertEqual(item["provenance"][0]["kind"], "modeled_estimate")
            self.assertTrue(any(s.startswith("nasa-response-sha256:") for s in item["traceability"]["input_references"]))
        self.post(["I01"], {"gdd": AUTO_GDD})
        self.assertEqual(len(self.calls), 2)  # Cache compartilhado com a integração INT.

    def test_rain_only_and_lst_without_tbase(self):
        response = self.post(["I02"], {"rainfall": {**AUTO_RAIN, "day_basis": "LST"}})
        self.assertEqual(response.status_code, 200, response.text)
        rain = response.json()["result"]["indicators"]["I02"]
        self.assertEqual(self.calls[0].url.params["time-standard"], "LST")
        self.assertIsNone(rain["period"]["timezone"])
        self.assertEqual(rain["day_basis"], "LST")

    def test_partial_and_all_unavailable(self):
        type(self).failure = 503
        response = self.post(["I01", "I02"], {"gdd": manual_gdd(), "rainfall": AUTO_RAIN})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "partial")
        unavailable = response.json()["result"]["indicators"]["I02"]
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertNotIn("value", unavailable)
        all_failed = self.post(["I02"], {"rainfall": AUTO_RAIN})
        self.assertEqual(all_failed.status_code, 502)

    def test_gaps_and_quota_do_not_turn_into_totals(self):
        type(self).missing = True
        result = self.post(["I01"], {"gdd": AUTO_GDD})
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.json()["error"]["code"], "DATA_INCOMPLETE")
        self.nasa.cache.clear()
        type(self).failure = 429
        result = self.post(["I02"], {"rainfall": AUTO_RAIN})
        self.assertEqual(result.status_code, 429)
        self.assertNotIn("value", result.json())

    def test_validation_no_network_and_private_errors(self):
        for include, inputs in ((["I01"], {"gdd": {**AUTO_GDD, "timezone": "America/Sao_Paulo"}}),
                                (["I02"], {"rainfall": {"reference_date": "2025-10-03", "day_basis": "UTC"}}),
                                (["I01", "I02"], {"gdd": AUTO_GDD}),
                                (["I01", "I01"], {"gdd": AUTO_GDD}),
                                (["I01"], {"gdd": {**AUTO_GDD, "leak_key": "do-not-echo"}})):
            with self.subTest(inputs=inputs):
                result = self.post(include, inputs)
                self.assertEqual(result.status_code, 422, result.text)
                self.assertNotIn("do-not-echo", result.text)
        self.assertEqual(len(self.calls), 0)
        forecast = self.post(["I01"], {"gdd": {**AUTO_GDD, "data_kind": "forecast"}})
        self.assertEqual(forecast.status_code, 503)
        self.assertEqual(len(self.calls), 0)

    def test_pending_ids_and_four_public_operations(self):
        dry_spell = {"location": LOCATION, "start_date": "2025-10-01", "end_date": "2025-10-03", "rain_threshold_mm": 1}
        partial = self.post(["I01", "I03"], {"gdd": manual_gdd(), "dry_spell": dry_spell})
        self.assertEqual(partial.status_code, 200)
        self.assertEqual(partial.json()["result"]["indicators"]["I03"]["status"], "ok")
        pending = self.post(["I03"], {"dry_spell": dry_spell})
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["result"]["indicators"]["I03"]["longest_run_days"], 3)
        schema = self.client.get("/openapi.json").json()
        operations = [item["post"]["operationId"] for path, item in schema["paths"].items() if path.startswith("/v1/analysis/")]
        self.assertEqual(set(operations), {"analyze_climate", "analyze_water", "analyze_agronomy", "analyze_economics"})
        self.assertFalse(any(p.startswith("/v1/indicators/") for p in schema["paths"]))
        catalog = self.client.get("/v1/capabilities").json()["capabilities"]
        self.assertEqual(len([c for c in catalog if c["category"] == "IND"]), 4)
        self.assertIn("nasa_power", next(c for c in catalog if c["id"] == "analyze_climate")["supported_indicators"][0]["modes"])

    def test_packaged_modules_are_fingerprinted(self):
        root = ROOT / "src/vendor/intelligence"
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for name, metadata in manifest["files"].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), metadata["packaged_sha256"], name)


if __name__ == "__main__":
    unittest.main()
