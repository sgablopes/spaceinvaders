import unittest
from unittest.mock import patch

from app import create_app


class PropertyAssetsTest(unittest.TestCase):
    def test_map_key_comes_from_environment(self):
        with patch.dict("os.environ", {"MAPTILER_API_KEY": "test-browser-key"}):
            response = create_app({"TESTING": True}).test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'maptilerKey: "test-browser-key"', response.data)

    def test_missing_map_key_is_empty(self):
        with patch.dict("os.environ", {"MAPTILER_API_KEY": ""}):
            response = create_app({"TESTING": True}).test_client().get("/")
        self.assertIn(b'maptilerKey: ""', response.data)

    def test_map_assets_are_served(self):
        client = create_app({"TESTING": True}).test_client()
        for asset in ("property-store.js", "property-flow.js", "property-flow.css"):
            with self.subTest(asset=asset):
                response = client.get(f"/static/{asset}")
                self.assertEqual(response.status_code, 200)
                response.close()
