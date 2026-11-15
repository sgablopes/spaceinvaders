"""Mocks exclusivamente sintéticos; nenhuma credencial real ou dado de produção nesta suíte."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
import httpx
from pydantic import ValidationError

from src.main import create_app
from src.meteomatics import ForecastError, Meteomatics, stamp
from src.meteomatics_schemas import ForecastRequest, PARAMETERS

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
REQUEST = {"location": {"latitude": -16.5, "longitude": -49.3},
    "start_time": "2030-01-01T02:00:00Z", "end_time": "2030-01-01T04:00:00Z"}


def fixture(payload=None):
    """Formato oficial JSON com valores inteiramente sintéticos."""
    p = payload or ForecastRequest.model_validate(REQUEST)
    count = int((p.end_time - p.start_time).total_seconds() / (p.step_hours * 3600)) + 1
    sample = {"temperature": 24, "temperature_mean": 23, "temperature_min": 20, "temperature_max": 28,
              "precipitation": 0, "relative_humidity": 60, "wind_speed": 2, "solar_radiation": 400}
    return {"version": "3.0", "user": "private-test-account", "dateGenerated": stamp(NOW), "status": "OK", "data": [
        {"parameter": PARAMETERS[name][0].format(hours=p.step_hours), "coordinates": [{
            "lat": p.location.latitude, "lon": p.location.longitude, "dates": [
                {"date": stamp(p.start_time + timedelta(hours=i * p.step_hours)), "value": sample[name]} for i in range(count)]}]} for name in p.parameters]}


class MeteomaticsTests(unittest.TestCase):
    def service(self, raw=None, **kwargs):
        raw = raw if raw is not None else fixture()
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=raw)))
        service = Meteomatics(client, username="synthetic-user", password="synthetic-password", now=lambda: NOW, **kwargs)
        self.addCleanup(service.close)
        return service

    def test_auth_only_in_header_and_no_account_echo(self):
        requests = []
        def respond(request):
            requests.append(request)
            self.assertEqual(request.url.host, "api.meteomatics.com")
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(request.url.params["source"], "mix")
            expected = "Basic " + base64.b64encode(b"synthetic-user:synthetic-password").decode()
            self.assertEqual(request.headers["Authorization"], expected)
            self.assertEqual(request.url.username, "")
            self.assertNotIn("synthetic-password", str(request.url))
            return httpx.Response(200, json=fixture())
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            result = Meteomatics(client, username="synthetic-user", password="synthetic-password", now=lambda: NOW).forecast(ForecastRequest.model_validate(REQUEST))
        serialized = result.model_dump_json()
        for secret in ("synthetic-user", "synthetic-password", "private-test-account", "Authorization"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(result.provenance[0].kind, "operational_forecast")
        self.assertEqual(result.result.series[0].precipitation_mm, 0)

    def test_all_parameters_units_and_interval_semantics(self):
        request = ForecastRequest.model_validate({**REQUEST, "parameters": list(PARAMETERS)})
        result = self.service(fixture(request)).forecast(request)
        self.assertEqual(result.result.parameters["solar_radiation"].unit, "W/m²")
        self.assertIsNone(result.result.parameters["solar_radiation"].interval_hours)
        self.assertEqual(result.result.parameters["temperature_min"].provider_parameter, "t_min_2m_1h:C")
        self.assertEqual(result.result.parameters["precipitation"].interval_hours, 1)
        self.assertEqual(result.result.series[0].interval_start, request.start_time - timedelta(hours=1))
        self.assertIsNone(result.provenance[0].forecast_reference_time)
        self.assertIsNone(result.quality.confidence)

    def test_step_24_does_not_label_instants_as_daily_energy(self):
        request = ForecastRequest.model_validate({**REQUEST, "start_time": "2030-01-02T00:00:00Z", "end_time": "2030-01-03T00:00:00Z",
                                               "step_hours": 24, "parameters": ["temperature_min", "precipitation", "solar_radiation"]})
        result = self.service(fixture(request)).forecast(request)
        self.assertEqual(result.result.parameters["precipitation"].provider_parameter, "precip_24h:mm")
        self.assertEqual(result.result.parameters["solar_radiation"].temporal_semantics, "instantaneous")
        self.assertEqual(result.result.series[0].interval_start, datetime(2030, 1, 1, tzinfo=timezone.utc))

    def test_reserved_and_missing_times_are_partial_not_zero(self):
        raw = fixture()
        raw["data"][0]["coordinates"][0]["dates"][0]["value"] = -888
        raw["data"][1]["coordinates"][0]["dates"].pop()
        service = self.service(raw)
        request = ForecastRequest.model_validate(REQUEST)
        result = service.forecast(request)
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.result.series[0].temperature_c)
        self.assertEqual(result.result.series[0].precipitation_mm, 0)
        self.assertEqual(result.result.available_end_by_parameter["precipitation"], request.end_time - timedelta(hours=1))
        with self.assertRaises(ForecastError) as error:
            service.forecast(ForecastRequest.model_validate({**REQUEST, "require_complete": True}))
        self.assertEqual(error.exception.status, 404)

    def test_all_reserved_returns_no_data(self):
        raw = fixture()
        for i, item in enumerate(raw["data"]):
            for entry in item["coordinates"][0]["dates"]:
                entry["value"] = [-999, -888, -777, -666][i]
        with self.assertRaises(ForecastError) as error:
            self.service(raw).forecast(ForecastRequest.model_validate(REQUEST))
        self.assertEqual(error.exception.status, 404)

    def test_upstream_partial_206_remains_partial(self):
        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(206, json=fixture()))) as client:
            service = Meteomatics(client, username="test", password="test", now=lambda: NOW)
            result = service.forecast(ForecastRequest.model_validate(REQUEST))
            self.assertEqual(result.status, "partial")
            self.assertEqual(result.provenance[0].upstream_http_status, 206)
            with self.assertRaises(ForecastError) as error:
                service.forecast(ForecastRequest.model_validate({**REQUEST, "require_complete": True}))
            self.assertEqual(error.exception.status, 404)

    def test_cache_expiry_bounded_storage_and_accessed_time(self):
        calls, clock = [], [0]
        def respond(request):
            calls.append(1)
            return httpx.Response(200, json=fixture())
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            service = Meteomatics(client, username="test", password="test", now=lambda: NOW, clock=lambda: clock[0], ttl=5)
            service.capacity = 1
            request = ForecastRequest.model_validate(REQUEST)
            first, second = service.forecast(request), service.forecast(request)
            self.assertFalse(first.cache.hit)
            self.assertTrue(second.cache.hit)
            self.assertEqual(first.provenance[0].accessed_at, second.provenance[0].accessed_at)
            self.assertNotEqual(first.traceability.request_id, second.traceability.request_id)
            self.assertEqual(len(calls), 1)
            clock[0] = 6
            self.assertFalse(service.forecast(request).cache.hit)
            self.assertEqual(len(calls), 2)

    def test_invalid_times_parameters_and_credentials_in_request(self):
        for changes in ({"start_time": "2030-01-01"}, {"start_time": "2030-01-01T02:00:00"},
                        {"start_time": 1893456000}, {"step_hours": True}, {"step_hours": "1"}, {"step_hours": 2},
                        {"step_hours": 3}, {"start_time": "2030-01-01T02:30:00Z"}, {"source": "https://malicious.example"},
                        {"parameters": ["temperature", "temperature"]}, {"parameters": []}, {"username": "do-not-accept"},
                        {"end_time": "2030-02-01T04:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ForecastRequest.model_validate({**REQUEST, **changes})
        converted = ForecastRequest.model_validate({**REQUEST, "start_time": "2029-12-31T23:00:00-03:00"})
        self.assertEqual(converted.start_time.hour, 2)

    def test_horizon_and_previous_interval_are_validated(self):
        service = self.service()
        for changes in ({"start_time": "2030-01-01T00:00:00Z"},
                        {"start_time": "2029-12-31T22:00:00Z", "end_time": "2029-12-31T23:00:00Z"},
                        {"end_time": "2030-01-09T04:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(ForecastError) as error:
                service.forecast(ForecastRequest.model_validate({**REQUEST, **changes}))
            self.assertEqual(error.exception.status, 422)

    def test_unreadable_values_and_provider_errors_are_rejected(self):
        for kind in ("boolean", "status"):
            raw = fixture()
            if kind == "boolean": raw["data"][0]["coordinates"][0]["dates"][0]["value"] = True
            if kind == "status": raw["status"] = "ERROR"
            with self.subTest(kind=kind), self.assertRaises(ForecastError) as error:
                self.service(raw).forecast(ForecastRequest.model_validate(REQUEST))
            self.assertEqual(error.exception.status, 502)

    def test_response_coordinates_versions_duplicates_and_ranges_do_not_block(self):
        raw = fixture()
        raw["version"] = "3.0-beta"
        raw["data"][0]["coordinates"][0]["lat"] = 0
        records = raw["data"][0]["coordinates"][0]["dates"]
        records.append({**records[0], "value": 140})
        records.append({"date": "2030-01-01T10:00:00Z", "value": 30})
        raw["data"].append(deepcopy(raw["data"][0]))
        raw["data"].append({"parameter": "unrequested_parameter", "coordinates": []})
        raw["data"][1]["coordinates"][0]["dates"][0]["value"] = -1
        result = self.service(raw).forecast(ForecastRequest.model_validate(REQUEST))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.provenance[0].api_version, "3.0-beta")
        self.assertEqual(result.result.series[0].temperature_c, 140)
        self.assertEqual(result.result.series[0].precipitation_mm, -1)
        self.assertEqual(len(result.result.series), 3)

    def test_unrequested_units_are_ignored_without_inventing_conversion(self):
        raw = fixture()
        raw["data"][0]["parameter"] = "t_2m:K"
        result = self.service(raw).forecast(ForecastRequest.model_validate(REQUEST))
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.result.series[0].temperature_c)
        self.assertIn("temperature", result.result.series[0].missing_parameters)

    def test_auth_quota_errors_are_sanitized_and_not_retried(self):
        for status, code, expected in ((401, "UPSTREAM_AUTHENTICATION_FAILED", 503), (402, "UPSTREAM_ACCESS_DENIED", 503),
                                       (403, "UPSTREAM_ACCESS_DENIED", 503), (429, "UPSTREAM_RATE_LIMITED", 429)):
            calls = []
            def respond(request):
                calls.append(1)
                return httpx.Response(status, text="synthetic-password Authorization private-test-account")
            with self.subTest(status=status), httpx.Client(transport=httpx.MockTransport(respond)) as client:
                service = Meteomatics(client, username="synthetic-user", password="synthetic-password", now=lambda: NOW, retries=2)
                with self.assertRaises(ForecastError) as error:
                    service.forecast(ForecastRequest.model_validate(REQUEST))
                self.assertEqual(error.exception.status, expected)
                self.assertEqual(error.exception.error["code"], code)
                self.assertNotIn("synthetic-password", json.dumps(error.exception.error))
                self.assertEqual(len(calls), 1)

    def test_transient_timeout_and_invalid_json(self):
        for kind, expected, count in (("timeout", 504, 2), ("network", 503, 2), ("server", 502, 2), ("json", 502, 1)):
            calls = []
            def respond(request):
                calls.append(1)
                if kind == "timeout": raise httpx.ReadTimeout("test-only")
                if kind == "network": raise httpx.ConnectError("test-only")
                return httpx.Response(200 if kind == "json" else 503, text="not-json test-only")
            with self.subTest(kind=kind), httpx.Client(transport=httpx.MockTransport(respond)) as client:
                service = Meteomatics(client, username="test", password="test", now=lambda: NOW, retries=1, sleep=lambda _: None)
                with self.assertRaises(ForecastError) as error:
                    service.forecast(ForecastRequest.model_validate(REQUEST))
                self.assertEqual(error.exception.status, expected)
                self.assertEqual(len(calls), count)

    def test_missing_credentials_makes_no_external_request(self):
        calls = []
        with httpx.Client(transport=httpx.MockTransport(lambda req: calls.append(req))) as client:
            service = Meteomatics(client, username="", password="", now=lambda: NOW)
            self.assertFalse(service.configured)
            with self.assertRaises(ForecastError) as error:
                service.forecast(ForecastRequest.model_validate(REQUEST))
            self.assertEqual(error.exception.error["code"], "METEOMATICS_CREDENTIALS_MISSING")
            self.assertEqual(calls, [])


class MeteomaticsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        cls.service = Meteomatics(httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=fixture()))),
            username="synthetic-user", password="synthetic-password", now=lambda: NOW)
        cls.client = TestClient(create_app(ROOT, Path(cls.temp.name) / "catalog.sqlite3", meteomatics=cls.service))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.temp.cleanup()

    def test_forecast_endpoint_schema_catalog_and_legacy(self):
        response = self.client.post("/v1/data/meteomatics/forecast", json=REQUEST)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["X-Request-ID"], response.json()["traceability"]["request_id"])
        self.assertNotIn("private-test-account", response.text)
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(schema["paths"]["/v1/data/meteomatics/forecast"]["post"]["operationId"], "get_meteomatics_forecast")
        self.assertEqual(len([p for p in schema["paths"] if p.startswith("/v1/analysis/")]), 4)
        catalog = self.client.get("/v1/capabilities").json()
        meteomatics = next(c for c in catalog["capabilities"] if c["id"] == "get_meteomatics_forecast")
        self.assertEqual(meteomatics["status"], "configured_unverified")
        invalid = self.client.post("/v1/data/meteomatics/forecast", json={**REQUEST, "password": "do-not-echo"})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("do-not-echo", invalid.text)
        self.assertIn("detail", self.client.get("/api/v1/ecocrop/culturas?limit=0").json())
        self.assertEqual(self.client.get("/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
