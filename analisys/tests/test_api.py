"""Testes de integração com fontes locais reais; externo usa fixtures sintéticas."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
import numpy as np
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from src.gaez import API, ExternalError, Gaez
from src.main import create_app
from src.store import FILES, Store, hashes

ROOT = Path(__file__).resolve().parents[1]
LAYER = "DATA/GAEZ-V5/MAPSET/RES05-SIX/GAEZ-V5.RES05-SIX.HP0120.HIST.HIST.MAIZ.HRLM.tif"


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = hashes(ROOT)
        (ROOT / ".runtime").mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        cls.database = Path(cls.temp.name) / "test.sqlite3"
        cls.mock = httpx.MockTransport(lambda request: httpx.Response(503))
        cls.app = create_app(ROOT, cls.database, Gaez(httpx.Client(transport=cls.mock)))
        cls.client = TestClient(cls.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.temp.cleanup()
        assert hashes(ROOT) == cls.before, "Os arquivos originais foram alterados."

    def test_catalog_and_health(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        data = self.client.get("/api/v1/datasets").json()
        self.assertEqual(len(data["local"]), 4)
        self.assertEqual(data["external"][0]["id"], "gaez")
        for item in data["local"]:
            self.assertEqual(item["sha256"], self.before[item["file"]])

    def test_ecocrop_values_and_search_synonyms(self):
        page = self.client.get("/api/v1/ecocrop/requisitos", params={"filtros": json.dumps({"crop_id": "ECO_289"})}).json()
        self.assertEqual(page["total"], 1)
        row = page["items"][0]
        self.assertEqual(row["source_row"], 2)
        self.assertEqual(row["data"]["temp_abs_min_C"], 12)
        self.assertIsNone(row["data"]["altitude_min_m"])
        crops = self.client.get("/api/v1/ecocrop/culturas").json()
        self.assertEqual(crops["total"], 2568)
        names = self.client.get("/api/v1/ecocrop/nomes_sinonimos", params={"q": "QUIABO"}).json()
        self.assertGreater(names["total"], 0)
        self.assertIn("ECO_289", [r["data"]["crop_id"] for r in names["items"]])
        zero = self.client.get("/api/v1/ecocrop/alertas", params={"filtros": '{"numero_alertas":0}'}).json()
        self.assertGreater(zero["total"], 0)
        self.assertTrue(all(r["data"]["numero_alertas"] == 0 for r in zero["items"]))
        absent = self.client.get("/api/v1/ecocrop/requisitos", params={"filtros": '{"altitude_min_m":null}'}).json()
        self.assertGreater(absent["total"], 0)
        self.assertTrue(all(r["data"]["altitude_min_m"] is None for r in absent["items"]))

    def test_pagination_and_invalid_filters(self):
        first = self.client.get("/api/v1/ecocrop/culturas", params={"limit": 2}).json()
        second = self.client.get("/api/v1/ecocrop/culturas", params={"limit": 2, "offset": 2}).json()
        self.assertNotEqual(first["items"], second["items"])
        self.assertEqual(first["total"], second["total"])
        for params in ({"limit": 0}, {"limit": 501}, {"offset": -1}, {"filtros": "[]"},
                       {"filtros": "no-json"}, {"filtros": '{"inexistente":"x"}'},
                       {"filtros": '{"crop_id":NaN}'},
                       {"filtros": '{"crop_id":["x"]}'}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/v1/ecocrop/culturas", params=params).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/ecocrop/missing").status_code, 404)
        attack = self.client.get("/api/v1/ecocrop/culturas", params={"filtros": json.dumps({"crop_id": "' OR 1=1 --"})}).json()
        self.assertEqual(attack["total"], 0)

    def test_fao_atomic_and_audit(self):
        atomic = self.client.get("/api/v1/fao56/indice_atomico", params={"filtros": '{"Parametro":"kc_ini"}'}).json()
        self.assertGreater(atomic["total"], 0)
        self.assertEqual(atomic["items"][0]["data"]["Unidade"], "adimensional")
        audited = self.client.get("/api/v1/fao56/auditoria_registros", params={"q": "PENDENTE"}).json()
        self.assertGreater(audited["total"], 0)
        ranges = self.client.get("/api/v1/fao56/ky_por_cultura", params={"filtros": '{"Cultura":"Banana"}'}).json()
        self.assertEqual(ranges["items"][0]["data"]["Ky_Min"], 1.2)
        self.assertEqual(ranges["items"][0]["data"]["Ky_Max"], 1.35)

    def test_knowledge_manifest_ids_and_quarantine(self):
        manifest = self.client.get("/api/v1/conhecimento/documentos/manifesto.json").json()["content"]
        for table, count in manifest["linhas_csv"].items():
            if table in {"culturas", "fontes", "evidencias", "rotacoes", "calendarios", "manejo_solo", "pragas_doencas", "fonte_culturas", "evidencia_culturas"}:
                result = self.client.get(f"/api/v1/conhecimento/{table}", params={"limit": 500}).json()
                self.assertEqual(result["total"], count)
        evidences = self.client.get("/api/v1/conhecimento/evidencias", params={"limit": 500}).json()["items"]
        ids = {r["data"]["evidencia_id"] for r in evidences}
        self.assertFalse(ids.intersection(manifest["quarentena"]))
        self.assertTrue(all("status_validacao_agronomica" in r["data"] for r in evidences))
        self.assertEqual(self.client.get("/api/v1/conhecimento/documentos/missing").status_code, 404)

    def test_knowledge_foreign_keys(self):
        def rows(table):
            return [r["data"] for r in self.client.get(f"/api/v1/conhecimento/{table}", params={"limit": 500}).json()["items"]]
        crop_ids = {r["cultura_id"] for r in rows("culturas")}
        source_ids = {r["fonte_id"] for r in rows("fontes")}
        evidence_ids = {r["evidencia_id"] for r in rows("evidencias")}
        self.assertTrue(all(r["fonte_id"] in source_ids for r in rows("evidencias")))
        self.assertTrue(all(r["cultura_id"] in crop_ids and r["evidencia_id"] in evidence_ids for r in rows("evidencia_culturas")))
        self.assertTrue(all(r["antecessora_id"] in crop_ids and r["sucessora_id"] in crop_ids for r in rows("rotacoes")))

    def test_aquacrop_empty_input_is_not_data(self):
        page = self.client.get("/api/v1/aquacrop/clima_diario").json()
        self.assertEqual(page["total"], 0)
        schema = self.client.get("/api/v1/aquacrop/tables/clima_diario").json()
        self.assertIn("eto_mm_day", schema["columns"])
        self.assertGreater(self.client.get("/api/v1/aquacrop/dicionario").json()["total"], 0)

    def test_unchanged_sources_reuse_index(self):
        before = self.database.stat().st_mtime_ns
        Store(ROOT, self.database).prepare()
        self.assertEqual(self.database.stat().st_mtime_ns, before)

    def test_openapi_and_external_errors(self):
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/v1/gaez/point", schema["paths"])
        self.assertEqual(self.client.get("/api/v1/gaez/layers").status_code, 502)
        self.assertEqual(self.client.get("/api/v1/gaez/point", params={"layer": LAYER, "latitude": 91, "longitude": 0}).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/gaez/point", params={"layer": "https://localhost/secret", "latitude": 0, "longitude": 0}).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/gaez/layers", params={"filename_prefix": "GAEZ-V5.RES05"}).status_code, 422)


class GaezTests(unittest.TestCase):
    def test_external_pagination_and_fixed_host(self):
        def respond(request):
            self.assertEqual(request.url.host, "storage.googleapis.com")
            self.assertEqual(request.url.params["prefix"], "DATA/GAEZ-V5/MAPSET/RES05-SIX/GAEZ-V5.RES05-SIX.HP0120")
            self.assertEqual(request.url.params["pageToken"], "next")
            return httpx.Response(200, json={"items": [{"name": LAYER, "size": "123"}], "nextPageToken": "last"})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            page = Gaez(client).layers("RES05-SIX", "GAEZ-V5.RES05-SIX.HP0120", 1, "next")
            self.assertEqual(page["next_page_token"], "last")
            self.assertEqual(page["items"][0]["layer"], LAYER)

    def test_timeout_and_missing_layer(self):
        def timeout(request):
            raise httpx.ReadTimeout("fixture sintética")
        with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
            with self.assertRaises(ExternalError) as error:
                Gaez(client).layers()
            self.assertEqual(error.exception.status, 504)
        with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(404))) as client:
            with self.assertRaises(ExternalError) as error:
                Gaez(client).point(LAYER, 0, 0)
            self.assertEqual(error.exception.status, 404)

    def test_pixel_nodata_scale_and_bounds_synthetic_raster(self):
        # Dados exclusivamente sintéticos: pixel 12, escala 0.5, offset 1 e NoData -999.
        with MemoryFile() as memory:
            with memory.open(driver="GTiff", height=1, width=2, count=1, dtype="int16", crs="EPSG:4326",
                             transform=from_origin(0, 1, 1, 1), nodata=-999) as dataset:
                dataset.write(np.array([[[12, -999]]], dtype="int16"))
                dataset.scales = [0.5]
                dataset.offsets = [1]
            original_open = __import__("rasterio").open
            def open_fixture(url):
                self.assertTrue(url.startswith("https://storage.googleapis.com/"))
                return original_open(memory.name)
            with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"name": LAYER}))) as client:
                gaez = Gaez(client)
                with patch("src.gaez.rasterio.open", side_effect=open_fixture):
                    value = gaez.point(LAYER, 0.5, 0.5)
                    self.assertEqual(value["raw_value"], 12)
                    self.assertEqual(value["value"], 7)
                    missing = gaez.point(LAYER, 0.5, 1.5)
                    self.assertEqual(missing["status"], "nodata")
                    self.assertIsNone(missing["value"])
                    with self.assertRaises(ExternalError) as error:
                        gaez.point(LAYER, 10, 10)
                    self.assertEqual(error.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
