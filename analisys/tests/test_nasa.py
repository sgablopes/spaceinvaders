"""Todas as respostas externas desta suíte são fixtures sintéticas identificadas."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.intelligence_bridge import climate_request
from src.main import create_app
from src.nasa_power import NasaError, NasaPower
from src.nasa_schemas import DailyRequest, PARAMETERS

ROOT = Path(__file__).resolve().parents[1]
REQUEST = {"location": {"latitude": -16.5, "longitude": -49.3}, "start_date": "2025-10-01", "end_date": "2025-10-03"}


def synthetic_response(payload=None):
    """Fixture sintética, sem alegação de valores observados da NASA."""
    payload = payload or DailyRequest.model_validate(REQUEST)
    days = [payload.start_date + timedelta(days=i) for i in range((payload.end_date - payload.start_date).days + 1)]
    values = {"T2M": 22, "T2M_MAX": 30, "T2M_MIN": 15, "PRECTOTCORR": 0, "RH2M": 60, "ALLSKY_SFC_SW_DWN": 20}
    return {"header": {"sources": ["TEST_SYNTHETIC"], "api": {"version": "test-only"}, "fill_value": -999,
                       "time_standard": payload.time_standard, "start": payload.start_date.strftime("%Y%m%d"),
                       "end": payload.end_date.strftime("%Y%m%d")},
            "geometry": {"type": "Point", "coordinates": [payload.location.longitude, payload.location.latitude]},
            "parameters": {p: {"units": PARAMETERS[p][1], "longname": "Synthetic " + p} for p in payload.parameters},
            "properties": {"parameter": {p: {d.strftime("%Y%m%d"): values[p] for d in days} for p in payload.parameters}}}


class NasaTests(unittest.TestCase):
    def make_client(self, raw=None, **settings):
        raw = raw if raw is not None else synthetic_response()
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=raw))
        service = NasaPower(httpx.Client(transport=transport), **settings)
        self.addCleanup(service.close)
        return service

    def test_units_zero_and_provenance(self):
        result = self.make_client().daily(DailyRequest.model_validate(REQUEST))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.result.series[0].precip_mm_day, 0)
        self.assertEqual(result.result.parameters["ALLSKY_SFC_SW_DWN"].unit, "MJ/m^2/day")
        self.assertEqual(result.result.days_complete, 3)
        self.assertEqual(result.provenance[0].kind, "modeled_estimate")
        self.assertEqual(result.provenance[0].api_version, "test-only")
        self.assertIsNone(result.quality.confidence)
        self.assertEqual(len(result.traceability.upstream_sha256), 64)

    def test_cache_expiry_and_bounded_capacity(self):
        calls, clock = [], [0]
        def respond(request):
            calls.append(request)
            self.assertEqual(request.url.host, "power.larc.nasa.gov")
            self.assertEqual(request.url.params["time-standard"], "UTC")
            return httpx.Response(200, json=synthetic_response())
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            service = NasaPower(client, ttl=5, capacity=1, clock=lambda: clock[0])
            first = service.daily(DailyRequest.model_validate(REQUEST))
            second = service.daily(DailyRequest.model_validate(REQUEST))
            self.assertFalse(first.cache.hit)
            self.assertTrue(second.cache.hit)
            self.assertEqual(first.provenance[0].accessed_at, second.provenance[0].accessed_at)
            self.assertNotEqual(first.traceability.request_id, second.traceability.request_id)
            self.assertEqual(len(calls), 1)
            clock[0] = 6
            self.assertFalse(service.daily(DailyRequest.model_validate(REQUEST)).cache.hit)
            self.assertEqual(len(calls), 2)
            service.daily(DailyRequest.model_validate({**REQUEST, "parameters": ["T2M"]}))
            self.assertEqual(len(service.cache), 1)

    def test_concurrent_calls_share_fetch(self):
        calls = []
        def respond(request):
            calls.append(1)
            return httpx.Response(200, json=synthetic_response())
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            service = NasaPower(client)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: service.daily(DailyRequest.model_validate(REQUEST)), range(4)))
            self.assertEqual(len(calls), 1)
            self.assertEqual(sum(r.cache.hit for r in results), 3)

    def test_missing_days_null_and_strict_mode(self):
        raw = synthetic_response()
        raw["properties"]["parameter"]["T2M_MIN"]["20251001"] = -999
        raw["properties"]["parameter"]["T2M_MAX"].pop("20251002")
        service = self.make_client(raw)
        result = service.daily(DailyRequest.model_validate(REQUEST))
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.result.series[0].tmin_c)
        self.assertEqual(result.result.series[0].precip_mm_day, 0)
        self.assertEqual(result.result.days_complete, 1)
        self.assertEqual(result.quality.missing_dates["T2M_MAX"], [date(2025, 10, 2)])
        with self.assertRaises(NasaError) as error:
            service.daily(DailyRequest.model_validate({**REQUEST, "require_complete": True}))
        self.assertEqual(error.exception.status, 404)

    def test_empty_series_is_unavailable(self):
        raw = synthetic_response()
        for values in raw["properties"]["parameter"].values():
            for key in values:
                values[key] = -999
        with self.assertRaises(NasaError) as error:
            self.make_client(raw).daily(DailyRequest.model_validate(REQUEST))
        self.assertEqual(error.exception.status, 404)

    def test_units_time_geometry_and_numbers_rejected(self):
        for mutation in ("unit", "time", "geometry", "nan", "boolean", "negative_rain", "inverted_temp", "date", "sources"):
            with self.subTest(mutation=mutation):
                raw = synthetic_response()
                if mutation == "unit": raw["parameters"]["T2M"]["units"] = "K"
                if mutation == "time": raw["header"]["time_standard"] = "LST"
                if mutation == "geometry": raw["geometry"]["coordinates"] = [0, 0]
                if mutation == "nan": raw["properties"]["parameter"]["T2M"]["20251001"] = "NaN"
                if mutation == "boolean": raw["properties"]["parameter"]["T2M"]["20251001"] = True
                if mutation == "negative_rain": raw["properties"]["parameter"]["PRECTOTCORR"]["20251001"] = -1
                if mutation == "inverted_temp": raw["properties"]["parameter"]["T2M_MIN"]["20251001"] = 40
                if mutation == "date": raw["header"]["end"] = "20251002"
                if mutation == "sources": raw["header"]["sources"] = None
                with self.assertRaises(NasaError) as error:
                    self.make_client(raw).daily(DailyRequest.model_validate(REQUEST))
                self.assertEqual(error.exception.status, 502)

    def test_invalid_request(self):
        for fields in ({"end_date": "2025-09-01"}, {"end_date": "9999-01-01"}, {"start_date": "1980-01-01"},
                       {"start_date": "2025-01-01", "end_date": "2026-01-02"}, {"time_standard": "America/Sao_Paulo"},
                       {"parameters": ["T2M", "T2M"]}, {"parameters": ["UNKNOWN"]}, {"parameters": []},
                       {"location": {"latitude": True, "longitude": 0}}, {"start_date": "2025-10-01T00:00:00"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                DailyRequest.model_validate({**REQUEST, **fields})

    def test_lst_preserved_and_no_implicit_timezone(self):
        request = DailyRequest.model_validate({**REQUEST, "time_standard": "LST"})
        result = self.make_client(synthetic_response(request)).daily(request)
        self.assertEqual(result.result.period.time_standard, "LST")
        self.assertIsNone(result.result.period.timezone)
        with self.assertRaises(ValueError):
            climate_request(result, "maize", 10)

    def test_retry_timeout_quota_and_invalid_json(self):
        for kind, expected, count in (("timeout", 504, 2), ("network", 503, 2), ("server", 502, 2),
                                      ("quota", 429, 1), ("missing", 404, 1), ("json", 502, 1)):
            calls = []
            def respond(request):
                calls.append(1)
                if kind == "timeout": raise httpx.ReadTimeout("test-only")
                if kind == "network": raise httpx.ConnectError("test-only")
                if kind == "json": return httpx.Response(200, text="not-json test-only")
                return httpx.Response({"server": 503, "quota": 429, "missing": 404}[kind])
            with self.subTest(kind=kind), httpx.Client(transport=httpx.MockTransport(respond)) as client:
                with self.assertRaises(NasaError) as error:
                    NasaPower(client, retries=1, sleep=lambda _: None).daily(DailyRequest.model_validate(REQUEST))
                self.assertEqual(error.exception.status, expected)
                self.assertEqual(len(calls), count)

    def test_bridge_reuses_existing_manual_contract(self):
        request = DailyRequest.model_validate({**REQUEST, "start_date": "2025-07-06"})
        data = self.make_client(synthetic_response(request)).daily(request)
        body = climate_request(data, "maize", 10)
        self.assertEqual(body["include"], ["I01", "I02"])
        self.assertEqual(len(body["inputs"]["rainfall"]["daily_precipitation"]), 90)
        self.assertEqual(body["inputs"]["gdd"]["base_temperature_c"], 10)
        self.assertEqual(body["inputs"]["gdd"]["daily_temperatures"][0]["data_kind"], "unspecified")
        short = self.make_client().daily(DailyRequest.model_validate(REQUEST))
        with self.assertRaises(ValueError):
            climate_request(short, "maize", 10)
        for mutation in ("unit", "temperature", "rain", "dates"):
            malformed = data.model_copy(deep=True)
            if mutation == "unit": malformed.result.parameters["T2M_MIN"].unit = "K"
            if mutation == "temperature": malformed.result.series[0].tmin_c = None
            if mutation == "rain": malformed.result.series[-1].precip_mm_day = None
            if mutation == "dates": malformed.result.series[0].date = malformed.result.series[1].date
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                climate_request(malformed, "maize", 10)


class NasaApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        cls.service = NasaPower(httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=synthetic_response()))))
        cls.client = TestClient(create_app(ROOT, Path(cls.temp.name) / "data.sqlite3", nasa=cls.service))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.temp.cleanup()

    def test_endpoint_capabilities_schema_and_legacy(self):
        response = self.client.post("/v1/data/nasa-power/daily", json=REQUEST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-request-id"], response.json()["traceability"]["request_id"])
        self.assertEqual(self.client.get("/v1/capabilities").json()["capabilities"][0]["path"], "/v1/data/nasa-power/daily")
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(schema["paths"]["/v1/data/nasa-power/daily"]["post"]["operationId"], "get_nasa_power_daily_weather")
        self.assertIn("DailyResponse", schema["components"]["schemas"])
        self.assertEqual(self.client.get("/api/v1/ecocrop/culturas?limit=1").json()["total"], 2568)
        invalid = self.client.post("/v1/data/nasa-power/daily", json={"secret": "do-not-echo"})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("do-not-echo", invalid.text)
        self.assertEqual(invalid.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("detail", self.client.get("/api/v1/ecocrop/culturas?limit=0").json())


if __name__ == "__main__":
    unittest.main()
