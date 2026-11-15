"""Fixtures sintéticas: validam contrato/aritmética, não acurácia dos modelos."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
import httpx

from src.main import create_app
from src.meteomatics import Meteomatics, ForecastError
from src.meteomatics_schemas import ForecastRequest
from src.open_meteo import OpenMeteo, HOURLY, DAILY
from src.weather_schemas import WeatherRequest
from src.weather_service import Weather
from test_meteomatics import fixture as meteo_fixture, NOW
from tools.probe_geos_fp import select, read_small

ROOT = Path(__file__).resolve().parents[1]
QUERY = {"location": {"latitude": -16.5, "longitude": -49.3}, "start_time": "2030-01-03T00:00:00Z",
         "end_time": "2030-01-04T00:00:00Z", "step_hours": 24, "parameters": ["temperature_min", "temperature_max", "precipitation"]}


def fixture(payload):
    first = payload.start_time - timedelta(hours=payload.step_hours - 1) if "precipitation" in payload.parameters else payload.start_time
    times = [first + timedelta(hours=i) for i in range(int((payload.end_time - first).total_seconds() / 3600) + 1)]
    days = [payload.start_time - timedelta(days=1) + timedelta(days=i) for i in range((payload.end_time.date() - payload.start_time.date()).days + 1)]
    raw = {"latitude": -16.5, "longitude": -49.25, "elevation": 800, "utc_offset_seconds": 0, "timezone": "GMT",
           "hourly": {"time": [int(t.timestamp()) for t in times]}, "hourly_units": {"time": "unixtime"},
           "daily": {"time": [int(d.timestamp()) for d in days]}, "daily_units": {"time": "unixtime"}}
    for p in payload.parameters:
        if p in HOURLY:
            variable, unit = HOURLY[p]
            value = {"temperature": 25, "precipitation": 0.5, "relative_humidity": 60, "wind_speed": 2, "solar_radiation": 400}[p]
            raw["hourly"][variable] = [value] * len(times)
            raw["hourly_units"][variable] = unit
        else:
            raw["daily"][DAILY[p]] = [{"temperature_min": 15, "temperature_max": 30, "temperature_mean": 22}[p]] * len(days)
            raw["daily_units"][DAILY[p]] = "°C"
    return raw


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.query = WeatherRequest.model_validate(QUERY)
        self.raw = fixture(self.query)
        self.status = 200
        self.failure = None
        self.tick = 0
        def respond(request):
            self.calls.append(request)
            if self.failure:
                raise self.failure("synthetic upstream failure", request=request)
            return httpx.Response(self.status, json=self.raw)
        self.backup = OpenMeteo(httpx.Client(transport=httpx.MockTransport(respond)), now=lambda: NOW, clock=lambda: self.tick)
        self.addCleanup(self.backup.close)

    def primary(self, *, status=200, configured=True, raw=None, failure=None):
        self.primary_calls = []
        def respond(request):
            self.primary_calls.append(request)
            if failure:
                raise failure("synthetic error", request=request)
            return httpx.Response(status, json=raw or meteo_fixture(ForecastRequest.model_validate(QUERY)))
        service = Meteomatics(httpx.Client(transport=httpx.MockTransport(respond)), username="synthetic" if configured else "",
            password="synthetic" if configured else "", retries=0, now=lambda: NOW)
        self.addCleanup(service.close)
        return service

    def test_daily_extremes_precipitation_alignment_and_request_security(self):
        result = self.backup.forecast(self.query)
        self.assertEqual(result.result.series[0].temperature_min_c, 15)
        self.assertEqual(result.result.series[0].temperature_max_c, 30)
        self.assertEqual(result.result.series[0].precipitation_mm, 12)
        self.assertEqual(result.result.series[0].interval_start.isoformat(), "2030-01-02T00:00:00+00:00")
        self.assertEqual(result.provenance[0].grid_longitude, -49.25)
        self.assertIsNone(result.provenance[0].forecast_reference_time)
        self.assertIsNone(result.provenance[0].provider_generated_at)
        request = self.calls[0]
        self.assertEqual(request.url.host, "api.open-meteo.com")
        self.assertNotIn("authorization", request.headers)
        self.assertNotIn("apikey", request.url.params)
        self.assertEqual(request.url.params["timezone"], "GMT")
        self.assertIn("temperature_2m_min", request.url.params["daily"])

    def test_hourly_instantaneous_and_three_hour_sum(self):
        self.query = WeatherRequest.model_validate({**QUERY, "step_hours": 3,
            "parameters": ["temperature", "precipitation", "relative_humidity", "wind_speed", "solar_radiation"]})
        self.raw = fixture(self.query)
        result = self.backup.forecast(self.query)
        self.assertEqual(result.result.series[0].precipitation_mm, 1.5)
        self.assertEqual(result.result.series[0].wind_speed_10m_m_s, 2)
        self.assertEqual(result.result.series[0].solar_radiation_w_m2, 400)
        self.assertEqual(result.result.parameters["solar_radiation"].temporal_semantics, "instantaneous")
        self.assertIn("shortwave_radiation_instant", self.calls[0].url.params["hourly"])

    def test_gaps_and_null_are_not_partial_sums_zero_is_valid(self):
        self.raw["hourly"]["precipitation"][0] = None
        result = self.backup.forecast(self.query)
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.result.series[0].precipitation_mm)
        self.assertEqual(result.result.series[1].precipitation_mm, 12)
        with self.assertRaises(ForecastError) as caught:
            self.backup.forecast(self.query.model_copy(update={"require_complete": True}))
        self.assertEqual(caught.exception.error["code"], "DATA_INCOMPLETE")
        self.backup.cache.clear()
        self.raw["hourly"]["precipitation"] = [0] * len(self.raw["hourly"]["time"])
        self.assertEqual(self.backup.forecast(self.query).result.series[0].precipitation_mm, 0)

    def test_unreadable_numeric_values_are_rejected(self):
        for mutate in (lambda r: r["hourly"]["precipitation"].__setitem__(0, True),
                       lambda r: r["hourly"]["precipitation"].__setitem__(0, "not-a-number")):
            self.raw = fixture(self.query)
            mutate(self.raw)
            self.backup.cache.clear()
            with self.subTest(mutate=mutate), self.assertRaises(ForecastError) as caught:
                self.backup.forecast(self.query)
            self.assertEqual(caught.exception.status, 502)

    def test_response_metadata_ranges_and_duplicates_do_not_block(self):
        self.raw["hourly_units"]["precipitation"] = "inch"
        self.raw.update(latitude=40, utc_offset_seconds=3600, timezone="Provider/Local")
        self.raw["daily"]["temperature_2m_min"][0] = 140
        self.raw["daily"]["time"].append(self.raw["daily"]["time"][0])
        self.raw["daily"]["temperature_2m_min"].append(140)
        self.raw["daily"]["temperature_2m_max"].append(30)
        result = self.backup.forecast(self.query)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.result.parameters["precipitation"].unit, "inch")
        self.assertEqual(result.result.series[0].temperature_min_c, 140)
        self.assertEqual(result.provenance[0].grid_latitude, 40)
        self.assertEqual(result.provenance[0].source_timezone, "Provider/Local")
        self.assertEqual(result.provenance[0].source_utc_offset_seconds, 3600)

    def test_unordered_times_and_short_arrays_become_missing_not_rejection(self):
        for block in ("daily", "hourly"):
            for values in self.raw[block].values():
                values.reverse()
        self.raw["hourly"]["precipitation"].pop()
        result = self.backup.forecast(self.query)
        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.result.series[0].precipitation_mm)
        self.assertEqual(result.result.series[1].precipitation_mm, 12)

    def test_cache_expiry_capacity_and_copy(self):
        first = self.backup.forecast(self.query)
        first.result.series[0].precipitation_mm = 999
        second = self.backup.forecast(self.query)
        self.assertTrue(second.cache.hit)
        self.assertEqual(second.result.series[0].precipitation_mm, 12)
        self.assertEqual(len(self.calls), 1)
        self.tick = self.backup.ttl + 1
        self.assertFalse(self.backup.forecast(self.query).cache.hit)
        self.assertEqual(len(self.calls), 2)
        self.backup.capacity = 1
        self.backup.forecast(self.query.model_copy(update={"parameters": ["temperature_min"]}))
        self.assertEqual(len(self.backup.cache), 1)

    def test_unsupported_extremes_source_past_and_horizon_make_no_request(self):
        for changes, status in (({"step_hours": 1}, 503), ({"source": "ncep-gfs"}, 503),
            ({"start_time": datetime(2029, 12, 31, tzinfo=timezone.utc)}, 422),
            ({"end_time": NOW + timedelta(days=9)}, 422)):
            with self.subTest(changes=changes), self.assertRaises(ForecastError) as caught:
                self.backup.forecast(self.query.model_copy(update=changes))
            self.assertEqual(caught.exception.status, status)
        self.assertEqual(self.calls, [])

    def test_primary_success_no_fallback_and_explicit_provider(self):
        weather = Weather(self.primary(), self.backup)
        result = weather.forecast(self.query)
        self.assertEqual(result.provider_used, "Meteomatics")
        self.assertFalse(result.fallback_used)
        self.assertEqual(self.calls, [])
        result = weather.forecast(self.query.model_copy(update={"provider": "open_meteo"}))
        self.assertEqual(result.provider_used, "Open-Meteo")
        self.assertFalse(result.fallback_used)
        self.assertEqual(len(self.primary_calls), 1)

    def test_fallback_missing_auth_quota_timeout_denial_and_incomplete(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status=status):
                result = Weather(self.primary(status=status), self.backup).forecast(self.query)
                self.assertEqual(result.provider_used, "Open-Meteo")
                self.assertTrue(result.fallback_used)
                self.assertEqual(result.provider_failures[0].provider, "Meteomatics")
        result = Weather(self.primary(configured=False), self.backup).forecast(self.query)
        self.assertEqual(result.provider_failures[0].code, "METEOMATICS_CREDENTIALS_MISSING")
        result = Weather(self.primary(failure=httpx.ReadTimeout), self.backup).forecast(self.query)
        self.assertEqual(result.provider_failures[0].code, "UPSTREAM_TIMEOUT")
        raw = meteo_fixture(ForecastRequest.model_validate(QUERY))
        raw["data"][0]["coordinates"][0]["dates"][0]["value"] = -999
        result = Weather(self.primary(raw=raw), self.backup).forecast(self.query)
        self.assertEqual(result.provider_failures[0].code, "DATA_INCOMPLETE")
        self.assertEqual(result.result.series[0].precipitation_mm, 12)

    def test_both_sources_fail_no_fabrication_no_fallback_on_invalid_input(self):
        weather = Weather(self.primary(configured=False), self.backup)
        self.status = 429
        with self.assertRaises(ForecastError) as caught:
            weather.forecast(self.query)
        self.assertEqual(caught.exception.error["code"], "FORECAST_PROVIDERS_UNAVAILABLE")
        self.assertEqual(len(caught.exception.error["details"]["reasons"]), 2)
        self.calls.clear()
        with self.assertRaises(ForecastError) as caught:
            Weather(self.primary(), self.backup).forecast(self.query.model_copy(update={"end_time": NOW + timedelta(days=9)}))
        self.assertEqual(caught.exception.status, 422)
        self.assertEqual(self.calls, [])
        with self.assertRaises(ForecastError):
            weather.forecast(self.query.model_copy(update={"provider": "meteomatics"}))
        self.assertEqual(self.calls, [])

    def test_open_meteo_network_and_http_errors_sanitized(self):
        for status, expected in ((429, 429), (503, 502), (400, 502)):
            self.status = status
            with self.assertRaises(ForecastError) as caught:
                self.backup.forecast(self.query)
            self.assertEqual(caught.exception.status, expected)
        self.failure = httpx.ReadTimeout
        with self.assertRaises(ForecastError) as caught:
            self.backup.forecast(self.query)
        self.assertEqual(caught.exception.status, 504)
        self.failure = httpx.ConnectError
        with self.assertRaises(ForecastError) as caught:
            self.backup.forecast(self.query)
        self.assertEqual(caught.exception.status, 503)

    def test_api_fallback_indicators_provenance_and_private_validation(self):
        primary = self.primary(configured=False)
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as directory:
            with TestClient(create_app(ROOT, Path(directory) / "catalog.sqlite3", meteomatics=primary, open_meteo=self.backup)) as client:
                r = client.post("/v1/data/weather/forecast", json=QUERY)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["provider_used"], "Open-Meteo")
                self.assertTrue(r.json()["fallback_used"])
                bad = client.post("/v1/data/weather/forecast", json={**QUERY, "password": "synthetic-do-not-echo"})
                self.assertEqual(bad.status_code, 422)
                self.assertNotIn("synthetic-do-not-echo", bad.text)
                context = {"start_date": "2030-01-02", "end_date": "2030-01-03", "timezone": "UTC", "location": QUERY["location"], "data_kind": "forecast"}
                r = client.post("/v1/analysis/climate", json={"include": ["I03", "I05"], "inputs": {
                    "dry_spell": {**context, "rain_threshold_mm": 1}, "thermal_stress": {**context,
                        "crop_id": "test", "growth_stage": "test", "threshold_catalog_version": "synthetic",
                        "lower_threshold_c": 16, "threshold_reference": "synthetic test"}}})
                self.assertEqual(r.status_code, 200, r.text)
                values = r.json()["result"]["indicators"]
                self.assertEqual(values["I03"]["value"], 0)
                self.assertEqual(values["I05"]["value"], 2)
                for item in values.values():
                    self.assertEqual(item["provenance"][0]["provider"], "Open-Meteo")
                    self.assertTrue(item["provenance"][0]["fallback_used"])
                    self.assertEqual(item["provenance"][0]["fallback_reasons"], ["METEOMATICS_CREDENTIALS_MISSING"])
                schema = client.get("/openapi.json").json()
                self.assertEqual(len([p for p in schema["paths"] if p.startswith("/v1/analysis/")]), 4)
                self.assertIn("/v1/data/nasa-power/daily", schema["paths"])
                self.assertIn("/v1/data/meteomatics/forecast", schema["paths"])
                self.assertTrue(any(c["id"] == "get_weather_forecast" for c in client.get("/v1/capabilities").json()["capabilities"]))

    def test_geos_subset_selection_metadata_and_stale_cycle(self):
        das = '''lat { String grads_mapping "linear"; Float64 minimum -90; Float32 resolution 0.25; String grads_size "721"; }
        lon { String grads_mapping "linear"; Float64 minimum -180; Float32 resolution 0.3125; String grads_size "1152"; }
        time { String grads_min "00:30z01jan2030"; String grads_step "60mn"; }'''
        dds = "Float32 t2m[time = 33][lat = 721][lon = 1152]"
        result = select(das, dds, -16.5, -49.3, NOW)
        self.assertEqual(result["constraint"], "t2m[0:1:2][294:1:294][418:1:418]")
        self.assertEqual(result["grid_longitude"], -49.375)
        self.assertEqual(result["valid_times_from_metadata"][0], "2030-01-01T00:30:00+00:00")
        with self.assertRaises(ValueError):
            select(das, dds, -16.5, -49.3, NOW + timedelta(days=3))
        with self.assertRaises(ValueError):
            select(das, "incompatible", -16.5, -49.3, NOW)

    def test_geos_probe_rejects_oversized_response(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 65537))) as client:
            with self.assertRaises(ValueError):
                read_small(client, "https://opendap.nccs.nasa.gov/synthetic-test")


if __name__ == "__main__":
    unittest.main()
