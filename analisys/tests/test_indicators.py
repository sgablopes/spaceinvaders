"""Novos métodos: entradas controladas explicitamente sintéticas, sem alegar calibração local."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

import httpx
from fastapi.testclient import TestClient

from src.main import create_app
from src.nasa_power import NasaPower
from src.nasa_schemas import DailyRequest
from src.meteomatics import Meteomatics
from src.meteomatics_schemas import ForecastRequest
from test_nasa import synthetic_response
from test_meteomatics import fixture as forecast_fixture, NOW

ROOT = Path(__file__).resolve().parents[1]
DATES = [date(2025, 10, 1) + timedelta(days=i) for i in range(3)]
CONTEXT = {"start_date": "2025-10-01", "end_date": "2025-10-03", "timezone": "UTC"}
LOCATION = {"latitude": -16.5, "longitude": -49.3}


def dry():
    return {**CONTEXT, "rain_threshold_mm": 1, "series_kind": "simulation", "daily_precipitation": [
        {"date": d.isoformat(), "precipitation_mm": v} for d, v in zip(DATES, [0, 1, 0.5])]}


def thermal():
    return {**CONTEXT, "crop_id": "caller_crop", "growth_stage": "caller_stage", "threshold_catalog_version": "synthetic-test-only",
        "lower_threshold_c": 10, "upper_threshold_c": 30, "threshold_reference": "synthetic thresholds; not calibrated",
        "series_kind": "simulation", "daily_temperatures": [
            {"date": d.isoformat(), "tmin_c": lo, "tmax_c": hi} for d, lo, hi in zip(DATES, [9, 10, 8], [30, 31, 32])]}


def etc():
    return {**CONTEXT, "crop_id": "caller_crop", "growth_stage": "caller_stage", "kc_catalog_version": "synthetic-test-only",
        "series_kind": "simulation", "kc": 1.2, "kc_reference": "synthetic coefficient", "eto_reference": "synthetic ETo",
        "eto_series": [{"date": d.isoformat(), "eto_mm_day": v} for d, v in zip(DATES, [4, 0, 5])]}


def balance():
    return {**etc(), "assumptions_reference": "synthetic explicit fluxes, no field claim", "daily_fluxes": [
        {"date": d.isoformat(), "precipitation_mm": 5, "irrigation_mm": 1, "capillary_rise_mm": 0,
         "runoff_mm": 0.5, "deep_percolation_mm": 0.5} for d in DATES]}


def margin():
    return {**CONTEXT, "crop_id": "caller_crop", "area_ha": 2, "expected_yield_t_per_ha": 3, "price_per_t": 1000,
            "cost_per_ha": 2000, "currency": "BRL", "assumptions_reference": "synthetic economic scenario"}


class IndicatorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        cls.nasa_calls, cls.forecast_calls = [], []
        def nasa_response(request):
            cls.nasa_calls.append(request)
            q = request.url.params
            payload = DailyRequest(location={"latitude": float(q["latitude"]), "longitude": float(q["longitude"])},
                start_date=date.fromisoformat(q["start"][:4] + "-" + q["start"][4:6] + "-" + q["start"][6:]),
                end_date=date.fromisoformat(q["end"][:4] + "-" + q["end"][4:6] + "-" + q["end"][6:]), parameters=q["parameters"].split(","))
            return httpx.Response(200, json=synthetic_response(payload))
        def forecast_response(request):
            cls.forecast_calls.append(request)
            codes = request.url.path.split("/")[2]
            payload = ForecastRequest(location=LOCATION, start_time="2030-01-03T00:00:00Z", end_time="2030-01-04T00:00:00Z",
                step_hours=24, parameters=["precipitation"] if "precip_" in codes else ["temperature_min", "temperature_max"])
            return httpx.Response(200, json=forecast_fixture(payload))
        cls.nasa = NasaPower(httpx.Client(transport=httpx.MockTransport(nasa_response)), retries=0)
        cls.meteo = Meteomatics(httpx.Client(transport=httpx.MockTransport(forecast_response)), username="synthetic", password="synthetic", now=lambda: NOW)
        cls.client = TestClient(create_app(ROOT, Path(cls.temp.name) / "catalog.sqlite3", nasa=cls.nasa, meteomatics=cls.meteo))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.temp.cleanup()

    def setUp(self):
        self.nasa_calls.clear()
        self.forecast_calls.clear()
        self.nasa.cache.clear()
        self.meteo.cache.clear()

    def call(self, identifier, field, payload, group="climate"):
        return self.client.post("/v1/analysis/" + group, json={"include": [identifier], "inputs": {field: payload}})

    def item(self, response, identifier):
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["result"]["indicators"][identifier]

    def test_dry_spell_threshold_boundaries_and_censoring(self):
        body = dry()
        item = self.item(self.call("I03", "dry_spell", body), "I03")
        self.assertEqual(item["longest_run_days"], 1)
        self.assertEqual(item["trailing_run_days"], 1)
        self.assertEqual(item["dry_days"], 2)
        self.assertTrue(item["starts_dry"])
        self.assertFalse(item["series"][1]["is_dry"])
        self.assertEqual(self.nasa_calls, [])
        body["rain_threshold_mm"] = 0
        self.assertEqual(self.item(self.call("I03", "dry_spell", body), "I03")["value"], 0)

    def test_dry_nasa_and_thermal_ecocrop(self):
        body = {**CONTEXT, "location": LOCATION, "rain_threshold_mm": 1}
        item = self.item(self.call("I03", "dry_spell", body), "I03")
        self.assertEqual(item["value"], 3)
        self.assertEqual(item["provenance"][0]["provider"], "NASA POWER")
        body = {**CONTEXT, "location": LOCATION, "crop_id": "quiabo", "growth_stage": "not_stage_specific",
                "threshold_catalog_version": "ecocrop_local", "ecocrop_crop_id": "ECO_289"}
        item = self.item(self.call("I05", "thermal_stress", body), "I05")
        self.assertEqual(item["lower_threshold_c"], 12)
        self.assertEqual(item["upper_threshold_c"], 35)
        self.assertEqual(item["threshold_scope"], "ecocrop_general_species_envelope")
        self.assertEqual(item["provenance"][1]["kind"], "catalog_reference")
        self.assertIn("not_damage", item["validation_scope"])

    def test_thermal_exposure_is_not_a_damage_score(self):
        item = self.item(self.call("I05", "thermal_stress", thermal()), "I05")
        self.assertEqual(item["value"], 3)  # União dos dias, sem contar duas vezes frio+calor.
        self.assertEqual(item["cold_exposure_days"], 2)
        self.assertEqual(item["heat_exposure_days"], 2)
        self.assertNotIn("risk_probability", item)
        self.assertEqual(self.nasa_calls, [])

    def test_daily_integrity_and_units_for_all_new_series(self):
        for identifier, field, builder, group, series in (("I03", "dry_spell", dry, "climate", "daily_precipitation"),
            ("I05", "thermal_stress", thermal, "climate", "daily_temperatures"), ("I07", "crop_evapotranspiration", etc, "water", "eto_series"),
            ("I08", "water_balance", balance, "water", "daily_fluxes")):
            for kind in ("missing", "duplicate", "out_of_range"):
                payload = builder()
                if kind == "missing": payload[series].pop()
                if kind == "duplicate": payload[series][1] = deepcopy(payload[series][0])
                if kind == "out_of_range": payload[series][0]["date"] = "2025-09-30"
                with self.subTest(identifier=identifier, kind=kind):
                    self.assertEqual(self.call(identifier, field, payload, group).status_code, 422)
        body = etc()
        body["eto_series"][0]["eto_mm_day"] = "4"
        self.assertEqual(self.call("I07", "crop_evapotranspiration", body, "water").status_code, 422)

    def test_etc_standard_equation_and_zero(self):
        item = self.item(self.call("I07", "crop_evapotranspiration", etc(), "water"), "I07")
        self.assertAlmostEqual(item["value"], 10.8)
        self.assertEqual(item["series"][1]["etc_mm_day"], 0)
        self.assertEqual(item["unit"], "mm")
        self.assertEqual(item["quality"]["kind"], "scenario")
        self.assertEqual(self.nasa_calls, [])

    def test_fao_scalar_selection_retains_source_and_rejects_ambiguity(self):
        body = etc()
        body.pop("kc")
        body.pop("kc_reference")
        body["kc_selection"] = {"record_id": "FAO56-25-61-197-03", "parameter": "kc_mid"}
        item = self.item(self.call("I07", "crop_evapotranspiration", body, "water"), "I07")
        self.assertEqual(item["kc"], 1)
        self.assertEqual(item["value"], 9)
        self.assertTrue(any(h.startswith("fao56-sha256:") for h in item["traceability"]["input_references"]))
        body["kc_selection"]["record_id"] = "FAO56-25-61-197-05"  # Variantes mandioca 1/2 anos não resolvidas.
        self.assertIn(self.call("I07", "crop_evapotranspiration", body, "water").status_code, (404, 503))

    def test_water_balance_all_fluxes_and_no_soil_stock_claim(self):
        item = self.item(self.call("I08", "water_balance", balance(), "water"), "I08")
        self.assertAlmostEqual(item["value"], 4.2)  # 3×(5+1−0.5−0.5) − 10.8.
        self.assertAlmostEqual(item["series"][-1]["cumulative_storage_change_mm"], item["value"])
        self.assertEqual(item["interpretation"], "storage_change_accounting_not_soil_water_content")
        body = balance()
        body["daily_fluxes"][0].pop("deep_percolation_mm")
        self.assertEqual(self.call("I08", "water_balance", body, "water").status_code, 422)

    def test_nasa_precipitation_in_balance_and_no_implicit_mixed_source(self):
        body = balance()
        body["location"] = LOCATION
        for r in body["daily_fluxes"]: r.pop("precipitation_mm")
        item = self.item(self.call("I08", "water_balance", body, "water"), "I08")
        self.assertAlmostEqual(item["value"], -10.8)
        self.assertTrue(any(p["provider"] == "NASA POWER" for p in item["provenance"]))
        self.assertTrue(any(p["dataset"] == body["eto_reference"] for p in item["provenance"]))
        body["daily_fluxes"][0]["precipitation_mm"] = 0
        self.assertEqual(self.call("I08", "water_balance", body, "water").status_code, 422)

    def test_economic_margin_negative_and_cost_definition(self):
        body = margin()
        item = self.item(self.call("I14", "crop_margin", body, "economics"), "I14")
        self.assertEqual(item["value"], 2000)
        self.assertEqual(item["revenue"], 6000)
        self.assertEqual(item["declared_costs"], 4000)
        self.assertEqual(item["margin_definition"], "revenue_less_declared_costs")
        body.update(cost_per_ha=4000, cost_basis="variable_costs")
        item = self.item(self.call("I14", "crop_margin", body, "economics"), "I14")
        self.assertEqual(item["value"], -2000)
        self.assertEqual(item["margin_definition"], "gross_margin_variable_costs")

    def test_overflow_bool_nan_missing_parameters_no_fabrication(self):
        body = etc()
        body["kc"] = 1e308
        body["eto_series"][0]["eto_mm_day"] = 1e308
        self.assertEqual(self.call("I07", "crop_evapotranspiration", body, "water").status_code, 422)
        body = margin()
        body["area_ha"] = True
        self.assertEqual(self.call("I14", "crop_margin", body, "economics").status_code, 422)
        body = etc()
        body.pop("eto_series")
        result = self.call("I07", "crop_evapotranspiration", body, "water")
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()["error"]["code"], "ETO_SOURCE_PENDING")

    def test_forecast_controlled_series_no_network(self):
        for identifier, field, builder, group in (("I03", "dry_spell", dry, "climate"), ("I05", "thermal_stress", thermal, "climate"),
                                                ("I07", "crop_evapotranspiration", etc, "water"), ("I08", "water_balance", balance, "water")):
            payload = builder()
            payload.update(data_kind="forecast", series_kind="forecast")
            with self.subTest(identifier=identifier):
                item = self.item(self.call(identifier, field, payload, group), identifier)
                self.assertEqual(item["quality"]["kind"], "scenario")
                self.assertEqual(item["provenance"][0]["kind"], "caller_supplied")
        self.assertEqual(self.forecast_calls, [])
        self.assertEqual(self.nasa_calls, [])

    def test_forecast_daily_24h_utc_bridge_with_mock_only(self):
        body = {"start_date": "2030-01-02", "end_date": "2030-01-03", "timezone": "UTC", "location": LOCATION,
                "data_kind": "forecast", "rain_threshold_mm": 1}
        item = self.item(self.call("I03", "dry_spell", body), "I03")
        self.assertEqual(item["value"], 2)
        self.assertEqual(item["series"][0]["date"], "2030-01-02")
        self.assertEqual(item["provenance"][0]["kind"], "operational_forecast")
        self.assertIn("precip_24h:mm", self.forecast_calls[0].url.path)
        body.pop("rain_threshold_mm")
        body.update(crop_id="test", growth_stage="test", threshold_catalog_version="test", upper_threshold_c=25, threshold_reference="test-only")
        item = self.item(self.call("I05", "thermal_stress", body), "I05")
        self.assertEqual(item["heat_exposure_days"], 2)
        water = balance()
        water.update(start_date="2030-01-02", end_date="2030-01-03", location=LOCATION, data_kind="forecast")
        water["eto_series"] = [{"date": d, "eto_mm_day": 4} for d in ("2030-01-02", "2030-01-03")]
        water["daily_fluxes"] = [{"date": d, "irrigation_mm": 1, "capillary_rise_mm": 0,
            "runoff_mm": 0.5, "deep_percolation_mm": 0.5} for d in ("2030-01-02", "2030-01-03")]
        item = self.item(self.call("I08", "water_balance", water, "water"), "I08")
        self.assertAlmostEqual(item["value"], -9.6)
        self.assertEqual(item["series"][0]["date"], "2030-01-02")
        self.assertEqual(item["quality"]["kind"], "scenario")
        self.assertTrue(any(p["kind"] == "operational_forecast" for p in item["provenance"]))
        self.assertEqual(len(self.nasa_calls), 0)

    def test_groups_catalog_legacy_and_partial_remain_consistent(self):
        body = {"include": ["I07", "I08"], "inputs": {"crop_evapotranspiration": etc(), "water_balance": {**etc(), "assumptions_reference": "test"}}}
        result = self.client.post("/v1/analysis/water", json=body)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["status"], "partial")
        self.assertNotIn("value", result.json()["result"]["indicators"]["I08"])
        legacy = self.client.post("/v1/indicators/crop-margin", json=margin())
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()["result"]["value"], 2000)
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(len([p for p in schema["paths"] if p.startswith("/v1/analysis/")]), 4)
        self.assertFalse(any(p.startswith("/v1/indicators/") for p in schema["paths"]))
        capabilities = self.client.get("/v1/capabilities").json()["capabilities"]
        groups = [c for c in capabilities if c["category"] == "IND"]
        available = {i["id"] for c in groups for i in c["supported_indicators"] if i["available"]}
        self.assertEqual(available, {"I01", "I02", "I03", "I05", "I07", "I08", "I14"})


if __name__ == "__main__":
    unittest.main()
