import unittest

from app import create_app


class HealthTest(unittest.TestCase):
    def test_health_endpoint(self):
        client = create_app({"TESTING": True}).test_client()
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"application": "Agrion", "version": "0.1.0", "status": "ok"})

    def test_home_serves_prototype(self):
        response = create_app({"TESTING": True}).test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NASA Space Apps Challenge 2026", response.data)
