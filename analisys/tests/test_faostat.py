"""FAOSTAT: fixtures sintéticas explícitas e uma conferência independente no CSV real."""
from copy import deepcopy
import csv
import itertools
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from src.main import create_app
from src.faostat_store import FaostatStore, HEADERS, CSV, COUNTRIES, sha256

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/v1/data/faostat"


def sample(area="21", m49="'076", name="Brazil", year=2024, element="5532", unit="USD", value="142.200000", month="7021", period="Annual value", flag="A"):
    labels = {"5530": "Producer Price (LCU/tonne)", "5531": "Producer Price (SLC/tonne)", "5532": "Producer Price (USD/tonne)", "5539": "Producer Price Index (2014-2016 = 100)"}
    return [area, m49, name, "56", "'0112", "Maize (corn)", element, labels[element], str(year), str(year), month, period, unit, value, flag]


def fixture():
    return [sample(), sample(year=2023, value="154.500000"), sample(element="5530", unit="LCU", value="800"),
        sample(element="5531", unit="SLC", value="800"), sample(element="5539", unit="", value="149.490000", flag="E"),
        sample(element="5530", unit="LCU", value="10", month="7001", period="January"),
        sample(element="5530", unit="LCU", value="20", month="7002", period="February"),
        sample(year=2025, element="5530", unit="LCU", value="11", month="7001", period="January"),
        sample(year=2022, value="0.000000"), sample(year=2021, value="", flag="I"),
        sample(area="231", m49="'840", name="United States of America", value="171.300000"),
        sample(area="62", m49="'230", name="Former Ethiopia", year=1991, value="1"),
        sample(area="238", m49="'231", name="Ethiopia", year=2024, value="2")]


def write_fixture(root, rows):
    with (root / CSV).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        writer.writerows(rows)


def margin_payload():
    return {"include": ["I14"], "inputs": {"crop_margin": {
        "crop_id": "maize", "start_date": "2026-01-01", "end_date": "2026-12-31", "area_ha": 2,
        "expected_yield_t_per_ha": 3, "cost_per_ha": 200, "currency": "USD",
        "assumptions_reference": "CONTROLLED yield/cost; national historical price is an explicit scenario assumption",
        "faostat_price": {"country_iso2": "BR", "item_code": "56", "year": 2024,
            "reference": "Use historical 2024 price in this scenario; not a forecast or field transaction"}}}}


class FaostatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        cls.root = Path(cls.temp.name)
        shutil.copyfile(ROOT / COUNTRIES, cls.root / COUNTRIES)
        write_fixture(cls.root, fixture())
        cls.store = FaostatStore(cls.root)
        cls.store.prepare()
        cls.client = TestClient(create_app(ROOT, cls.root / "catalog.sqlite3", faostat=cls.store))
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.temp.cleanup()

    def query(self, **changes):
        return self.client.get(PREFIX + "/prices", params={"country_iso2": "BR", "item_code": "56", "start_year": 2023, "end_year": 2024, "element_code": "5532", **changes})

    def test_counts_dimensions_country_codes_and_sources(self):
        metadata = self.client.get(PREFIX + "/metadata").json()
        self.assertEqual(metadata["records"], len(fixture()))
        self.assertEqual(metadata["country_mapping"]["records"], 182)
        self.assertIn("ET", metadata["ambiguous_iso2"])
        country = self.client.get(PREFIX + "/countries", params={"q": "Brasil"}).json()["items"][0]
        self.assertEqual((country["area_code"], country["m49"], country["iso2"], country["iso3"]), ("21", "076", "BR", "BRA"))
        self.assertEqual(country["raw"]["ID MapTiler (gid)"], 76)
        self.assertTrue(country["has_price_data"])
        items = self.client.get(PREFIX + "/items", params={"country_iso2": "BR", "q": "Maize"}).json()["items"]
        self.assertEqual(items[0]["item_code"], "56")
        self.assertEqual(items[0]["cpc_raw"], "'0112")

    def test_annual_prices_roundtrip_precision_and_stable_pagination(self):
        body = self.query().json()
        self.assertEqual(body["total"], 2)
        self.assertEqual([r["year"] for r in body["items"]], [2023, 2024])
        row = body["items"][1]
        self.assertEqual(row["raw"], dict(zip(HEADERS, fixture()[0])))
        self.assertEqual(row["value_text"], "142.200000")
        self.assertEqual(row["value"], 142.2)
        self.assertEqual(row["currency_iso3"], "USD")
        first = self.query(limit=1).json()
        second = self.query(limit=1, offset=1).json()
        self.assertEqual(first["total"], 2)
        self.assertNotEqual(first["items"][0]["source_row"], second["items"][0]["source_row"])

    def test_descending_history_keeps_default_and_stable_pages(self):
        descending = self.query(order="desc", limit=1).json()
        self.assertEqual(descending["items"][0]["year"], 2024)
        self.assertEqual(self.query(order="desc", limit=1, offset=1).json()["items"][0]["year"], 2023)
        self.assertEqual(self.query().json()["items"][0]["year"], 2023)
        self.assertEqual(self.query(order="desc; DROP TABLE observations").status_code, 422)

    def test_latest_price_has_explicit_frequency_element_and_period(self):
        response = self.client.get(PREFIX + "/prices/latest", params={"country_iso2": "BR", "item_code": "56"})
        self.assertEqual(response.status_code, 200, response.text)
        latest = response.json()
        self.assertEqual(latest["selection_status"], "found")
        self.assertEqual(latest["selected_period"], {"year": 2024, "month": None})
        self.assertEqual(latest["items"][0]["value"], 142.2)
        self.assertEqual(latest["items"][0]["element_code"], "5532")
        monthly = self.client.get(PREFIX + "/prices/latest", params={"area_code": "21", "item_code": "56",
            "frequency": "monthly", "element_code": "5530"}).json()
        self.assertEqual(monthly["selected_period"], {"year": 2025, "month": 1})
        self.assertEqual(monthly["items"][0]["value"], 11)
        february = self.store.latest_price("21", "56", frequency="monthly", month=2, element_code="5530")
        self.assertEqual(february["selected_period"], {"year": 2024, "month": 2})

    def test_latest_never_substitutes_frequency_or_product_and_keeps_zero(self):
        for params in ({"frequency": "monthly"}, {"item_code": "999999"}, {"start_year": 2030}):
            query = {"country_iso2": "BR", "item_code": "56", **params}
            latest = self.client.get(PREFIX + "/prices/latest", params=query).json()
            self.assertEqual(latest["selection_status"], "not_found")
            self.assertEqual(latest["items"], [])
            self.assertIsNone(latest["selected_period"])
        zero = self.store.latest_price("21", "56", end_year=2022)
        self.assertEqual(zero["items"][0]["value"], 0)
        self.assertTrue(zero["non_null_only"])
        self.assertEqual(self.store.latest_price("21", "56", end_year=2021)["selection_status"], "not_found")

    def test_latest_rejects_only_incompatible_query_filters(self):
        for params in ({"frequency": "all"}, {"month": 1}, {"start_year": 2025, "end_year": 2024},
                       {"country_iso2": "ET"}, {"area_code": "21"}, {"month": 13}):
            response = self.client.get(PREFIX + "/prices/latest", params={"country_iso2": "BR", "item_code": "56", **params})
            self.assertEqual(response.status_code, 422, response.text)

    def test_crop_candidates_use_existing_aliases_with_source_ids_and_no_automatic_selection(self):
        for query in ("milho", "maize", "Zea mays", "ECO_2175"):
            response = self.client.get(PREFIX + "/items/candidates", params={"q": query, "country_iso2": "BR"})
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertTrue(body["requires_review"])
            self.assertIsNone(body["selected_item_code"])
            self.assertEqual(body["mapping_status"], "candidate_unreviewed")
            self.assertEqual(body["candidates"][0]["item_code"], "56")
            self.assertEqual(body["knowledge_cultures"][0]["data"]["cultura_id"], "milho")
            self.assertTrue(any(c["data"]["crop_id"] == "ECO_2175" for c in body["ecocrop_cultures"]))
            self.assertTrue(body["sources"]["knowledge"]["sha256"])
        self.assertEqual(self.client.get(PREFIX + "/items/candidates", params={"q": "no_such_crop_xyz"}).json()["candidates"], [])
        self.assertEqual(self.client.get(PREFIX + "/items/candidates", params={"q": "  "}).status_code, 422)

    def test_months_indexes_and_local_currency_not_confused(self):
        months = self.query(frequency="monthly", start_year=2024, end_year=2025, element_code="5530").json()
        self.assertEqual(len(months["items"]), 3)
        january = self.query(frequency="monthly", month=1, start_year=2024, end_year=2024, element_code="5530").json()
        self.assertEqual(january["items"][0]["value"], 10)
        index = self.query(element_code="5539").json()["items"][0]
        self.assertEqual(index["unit"], "")
        self.assertEqual(index["flag"], "E")
        self.assertEqual(index["value_kind"], "index_2014_2016_100")
        self.assertIsNone(index["currency_iso3"])
        local = self.query(element_code="5530").json()["items"][0]
        self.assertIsNone(local["currency_iso3"])

    def test_null_zero_and_absent_are_distinct(self):
        zero = self.query(start_year=2022, end_year=2022).json()["items"][0]
        null = self.query(start_year=2021, end_year=2021).json()["items"][0]
        absent = self.query(start_year=2030, end_year=2030).json()
        self.assertEqual(zero["value"], 0)
        self.assertIsNone(null["value"])
        self.assertEqual(null["value_text"], "")
        self.assertEqual(absent["total"], 0)
        self.assertEqual(absent["items"], [])

    def test_validation_and_historical_iso_ambiguity(self):
        for changes in ({"end_year": 2022}, {"month": 1}, {"frequency": "monthly", "month": 13}, {"limit": 501}, {"country_iso2": "br"}, {"item_code": "56 OR 1=1"}, {"area_code": "21"}):
            with self.subTest(changes=changes): self.assertEqual(self.query(**changes).status_code, 422)
        ambiguous = self.query(country_iso2="ET")
        self.assertEqual(ambiguous.status_code, 422)
        self.assertEqual(ambiguous.json()["error"]["code"], "FAOSTAT_COUNTRY_AMBIGUOUS")
        explicit = self.client.get(PREFIX + "/prices", params={"area_code": "238", "item_code": "56", "start_year": 2024, "end_year": 2024})
        self.assertEqual(explicit.status_code, 200)
        self.assertEqual(explicit.json()["items"][0]["area"], "Ethiopia")
        self.assertEqual(self.query(country_iso2="ZZ").status_code, 404)

    def test_existing_i14_uses_exact_historical_price_only_and_keeps_cost_explicit(self):
        body = margin_payload()
        response = self.client.post("/v1/analysis/economics", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]["indicators"]["I14"]
        self.assertAlmostEqual(result["revenue"], 853.2)
        self.assertAlmostEqual(result["declared_costs"], 400)
        self.assertAlmostEqual(result["value"], 453.2)
        self.assertEqual(result["price_per_t_used"], 142.2)
        self.assertEqual(result["faostat_price_record"]["year"], 2024)
        self.assertEqual(result["faostat_price_record"]["raw"]["Value"], "142.200000")
        self.assertEqual(result["quality"]["kind"], "scenario")
        self.assertTrue(any(p["provider"] == "FAOSTAT" for p in result["provenance"]))
        legacy = self.client.post("/v1/indicators/crop-margin", json=body["inputs"]["crop_margin"])
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()["result"]["value"], result["value"])
        manual = deepcopy(body["inputs"]["crop_margin"])
        manual.pop("faostat_price")
        manual["price_per_t"] = 142.2
        comparison = self.client.post("/v1/analysis/economics", json={"include": ["I14"], "inputs": {"crop_margin": manual}})
        self.assertEqual(comparison.json()["result"]["indicators"]["I14"]["value"], result["value"])

    def test_i14_rejects_indexes_currency_ambiguity_missing_cost_or_price(self):
        for mutation in (lambda p: p.update(currency="BRL"), lambda p: p["faostat_price"].update(element_code="5539"),
                         lambda p: p.update(price_per_t=100), lambda p: p.pop("cost_per_ha"), lambda p: p.pop("faostat_price")):
            body = margin_payload()
            mutation(body["inputs"]["crop_margin"])
            with self.subTest(mutation=mutation): self.assertEqual(self.client.post("/v1/analysis/economics", json=body).status_code, 422)
        for year in (2021, 2030):
            body = margin_payload()
            body["inputs"]["crop_margin"]["faostat_price"]["year"] = year
            response = self.client.post("/v1/analysis/economics", json=body)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn('"value":', response.text)
        body = margin_payload()
        body["inputs"]["crop_margin"]["faostat_price"]["year"] = 2022
        result = self.client.post("/v1/analysis/economics", json=body).json()["result"]["indicators"]["I14"]
        self.assertEqual(result["price_per_t_used"], 0)
        self.assertEqual(result["value"], -400)

    def test_index_is_reused_and_query_uses_index(self):
        before = self.store.database.stat().st_mtime_ns
        self.store.prepare()
        self.assertEqual(self.store.database.stat().st_mtime_ns, before)
        with self.store.connect() as con:
            plan = list(con.execute("EXPLAIN QUERY PLAN SELECT * FROM observations WHERE area_code=? AND item_code=? AND year BETWEEN ? AND ?", ("21", "56", 2023, 2024)))
            self.assertTrue(any("prices_series" in r[3] and "SEARCH" in r[3] for r in plan))

    def test_atomic_refresh_preserves_previous_index_on_invalid_input(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / COUNTRIES, root / COUNTRIES)
            rows = fixture()
            write_fixture(root, rows)
            store = FaostatStore(root)
            store.prepare()
            before = sha256(store.database)
            rows[0][-2] = "NaN"
            write_fixture(root, rows)
            with self.assertRaises(ValueError): store.prepare()
            self.assertEqual(sha256(store.database), before)
            rows[0][-2] = "144.200000"
            write_fixture(root, rows)
            store.prepare()
            self.assertNotEqual(sha256(store.database), before)
            self.assertEqual(store.prices("21", "56", 2024, 2024, element_code="5532")["items"][0]["value"], 144.2)

    def test_duplicate_observations_are_preserved_but_not_picked_for_margin(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / COUNTRIES, root / COUNTRIES)
            write_fixture(root, [sample(), sample(value="145")])
            store = FaostatStore(root)
            store.prepare()
            self.assertEqual(store.metadata()["duplicate_keys"], 1)
            from src.faostat_margin import calculate
            from src.indicator_schemas import MarginRequest
            from src.vendor.intelligence.core.errors import ServiceError
            with self.assertRaises(ServiceError) as caught:
                calculate(store, MarginRequest.model_validate(margin_payload()["inputs"]["crop_margin"]), "test")
            self.assertEqual(caught.exception.code, "FAOSTAT_PRICE_AMBIGUOUS")
            latest = store.latest_price("21", "56")
            self.assertEqual(latest["selection_status"], "ambiguous")
            self.assertEqual(latest["total"], 2)
            self.assertEqual(len(latest["items"]), 2)

    def test_missing_files_do_not_fabricate_dataset(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as directory:
            store = FaostatStore(Path(directory))
            store.prepare()
            self.assertFalse(store.configured)
            from src.vendor.intelligence.core.errors import ServiceError
            with self.assertRaises(ServiceError): store.metadata()

    def test_openapi_discovery_and_original_analysis_groups(self):
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(schema["paths"][PREFIX + "/prices"]["get"]["operationId"], "get_faostat_producer_prices")
        self.assertEqual(schema["paths"][PREFIX + "/prices/latest"]["get"]["operationId"], "get_latest_faostat_producer_price")
        self.assertIn("CropCandidatePage", schema["components"]["schemas"])
        self.assertIn("LatestPricePage", schema["components"]["schemas"])
        self.assertEqual(len([p for p in schema["paths"] if p.startswith("/v1/analysis/")]), 4)
        self.assertTrue(any(c["id"] == "get_faostat_producer_prices" for c in self.client.get("/v1/capabilities").json()["capabilities"]))


class RealFaostatTests(unittest.TestCase):
    def test_latest_real_price_and_ambiguous_commercial_crop_candidates(self):
        from src.store import Store
        from src.faostat_candidates import candidates
        faostat = FaostatStore(ROOT)
        faostat.prepare()
        latest = faostat.latest_price("21", "56")
        self.assertEqual(latest["selected_period"], {"year": 2024, "month": None})
        self.assertEqual(latest["items"][0]["value"], 142.2)
        self.assertEqual(faostat.latest_price("21", "56", frequency="monthly")["selection_status"], "not_found")
        local = Store(ROOT, ROOT / ".runtime/catalog.sqlite3")
        local.prepare()
        maize = candidates(local, faostat, "milho")
        codes = {item["item_code"] for item in maize["candidates"]}
        self.assertIn("56", codes)
        self.assertIn("446", codes)  # Milho em grão e milho verde não são automaticamente equivalentes.
        self.assertTrue(maize["requires_review"])
        soy = candidates(local, faostat, "soja")
        self.assertEqual({item["item_code"] for item in soy["candidates"]}, {"236"})
        self.assertTrue(soy["additional_partial_candidates"])
        for query, label in (("tomate", "Tomatoes"), ("batata", "Potatoes")):
            self.assertIn(label, {item["name"] for item in candidates(local, faostat, query)["candidates"]})

    @unittest.skipUnless((ROOT / CSV).exists(), "Conferência independente requer CSV original; snapshot é validado nos testes de distribuição.")
    def test_real_sources_hashes_coverage_and_selected_csv_row(self):
        before = {name: sha256(ROOT / name) for name in (CSV, COUNTRIES)}
        store = FaostatStore(ROOT)
        store.prepare()
        self.assertEqual(store.metadata()["records"], 1319583)
        self.assertEqual(store.metadata()["country_mapping"]["price_areas_matched_by_code_and_m49"], 182)
        record = store.prices("21", "56", 2024, 2024, element_code="5532")["items"][0]
        self.assertEqual(record["value"], 142.2)
        with (ROOT / CSV).open(encoding="utf-8-sig", newline="") as stream:
            original = next(itertools.islice(csv.DictReader(stream), record["source_row"] - 2, record["source_row"] - 1))
        self.assertEqual(record["raw"], original)
        self.assertEqual({name: sha256(ROOT / name) for name in (CSV, COUNTRIES)}, before)


if __name__ == "__main__": unittest.main()
