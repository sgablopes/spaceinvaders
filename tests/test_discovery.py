import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from app import create_app
from app.api.discovery import Patch, _origin_ok, _validate_value


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"TESTING": True}).test_client()
        self.body = {"interview_id": "9bb3c5d8-2900-4628-a09e-57324c3040d7", "property_id": "0f329783-5659-43cb-a34d-36c77c62e810", "turn_id": "t001", "sequence": 1, "speaker": "farmer", "transcript": "Não tenho irrigação.", "profile_revision": 0, "profile_snapshot": {"fields": {}}}

    def test_invalid_input_and_health(self):
        self.assertEqual(self.client.post('/api/interview/extract', json={}).status_code, 422)
        self.assertEqual(self.client.get('/api/health').status_code, 200)

    def test_https_origin_matches_public_host_behind_http_proxy(self):
        with patch.dict(os.environ, {"AGRION_PUBLIC_ORIGIN": ""}):
            with self.client.application.test_request_context('/api/interview/live-session', base_url='http://agrion.earth', headers={'Origin': 'https://agrion.earth'}):
                self.assertTrue(_origin_ok())
            with self.client.application.test_request_context('/api/interview/live-session', base_url='http://agrion.earth', headers={'Origin': 'https://other.example'}):
                self.assertFalse(_origin_ok())

    def test_missing_vertex_configuration_is_explicit(self):
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "", "GOOGLE_CLOUD_LOCATION": ""}):
            self.assertEqual(self.client.post('/api/interview/extract', json=self.body).status_code, 503)

    def test_patch_taxonomy_rejects_unknown_fields_and_enums(self):
        base = {"field": "irrigation", "operation": "set", "value": {"water_regime": "rainfed", "irrigation_method": "none", "automated": False}, "status": "confirmed", "confidence": "high", "evidence_excerpt": "Não tenho irrigação"}
        self.assertTrue(_validate_value(Patch(**base)))
        self.assertFalse(_validate_value(Patch(**{**base, "field": "geometry"})))
        self.assertFalse(_validate_value(Patch(**{**base, "value": {"water_regime": "magic"}})))

    def test_multiple_provider_patches_are_filtered_to_explicit_valid_facts(self):
        self.body['transcript'] = 'Plantei milho, antes soja, faltou chuva, não tenho irrigação e tenho trator pequeno.'
        patches = [
            {"field": "last_crop", "operation": "set", "value": {"crop": "milho"}, "status": "confirmed", "confidence": "high", "evidence_excerpt": "Plantei milho"},
            {"field": "previous_crop", "operation": "set", "value": {"crop": "soja"}, "status": "confirmed", "confidence": "high", "evidence_excerpt": "antes soja"},
            {"field": "main_difficulties", "operation": "set", "value": {"categories": ["drought"], "free_text": ["faltou chuva"]}, "status": "confirmed", "confidence": "high", "evidence_excerpt": "faltou chuva"},
            {"field": "irrigation", "operation": "set", "value": {"water_regime": "rainfed", "irrigation_method": "none", "automated": False}, "status": "confirmed", "confidence": "high", "evidence_excerpt": "não tenho irrigação"},
            {"field": "mechanization", "operation": "merge", "value": {"work_mode": "unknown", "equipment": ["trator pequeno"], "automation_level": "unknown"}, "status": "uncertain", "confidence": "medium", "evidence_excerpt": "tenho trator pequeno"},
            {"field": "geometry", "operation": "set", "value": {}, "status": "confirmed", "confidence": "high", "evidence_excerpt": "Plantei milho"},
        ]
        import json
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text=json.dumps({"patches": patches, "warnings": []}))))
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_CLOUD_LOCATION": "us-central1", "GOOGLE_CLOUD_EXTRACTION_LOCATION": "us"}), patch('app.api.discovery.genai.Client', return_value=fake) as client_factory:
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['patches']), 5)
        client_factory.assert_called_once_with(vertexai=True, project='test-project', location='us')


if __name__ == '__main__':
    unittest.main()
