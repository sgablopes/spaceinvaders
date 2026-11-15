import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from app import create_app
from app.api.discovery import FIELDS, GenerationExtraction, GenerationPatch, Patch, _live_state_instruction, _live_text_frame, _origin_ok, _validate_value


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

    def test_vertex_binary_json_is_forwarded_as_text(self):
        self.assertEqual(_live_text_frame(b'{"setupComplete":{}}'), '{"setupComplete":{}}')
        self.assertEqual(_live_text_frame('{"setupComplete":{}}'), '{"setupComplete":{}}')

    def test_live_state_update_only_uses_canonical_statuses(self):
        fields = {field: 'pending' for field in ['last_crop', 'previous_crop', 'last_harvest_result', 'main_difficulties', 'irrigation', 'mechanization', 'primary_goal']}
        fields['last_crop'] = 'confirmed'
        text = _live_state_instruction('Agrion.', {'fields': fields, 'intro_stage': 2, 'clarify': True})
        self.assertIn('last_crop', text)
        self.assertIn('reformule-a uma vez', text)
        self.assertIn('despeça-se agora', _live_state_instruction('Agrion.', {'fields': fields, 'closing': True}))
        self.assertIsNone(_live_state_instruction('Agrion.', {'fields': {**fields, 'last_crop': 'malicious'}}))

    def test_history_patch_requires_evidence_in_named_farmer_turn(self):
        import json
        old_turn = 'farmer-earlier'
        self.body['history'] = [
            {'turn_id': old_turn, 'speaker': 'farmer', 'text': 'Foi banana.'},
            {'turn_id': 'assistant-later', 'speaker': 'agrion', 'text': 'A última cultura foi banana?'},
        ]
        self.body['transcript'] = 'Sim, foi boa.'
        generated = {'patches': [
            {'field': 'last_crop', 'operation': 'set', 'value': {'crop': 'banana'}, 'status': 'confirmed', 'evidence_excerpt': 'Foi banana', 'evidence_turn_id': old_turn},
            {'field': 'previous_crop', 'operation': 'set', 'value': {'crop': 'banana'}, 'status': 'confirmed', 'evidence_excerpt': 'banana', 'evidence_turn_id': 'assistant-later'},
        ], 'warnings': []}
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text=json.dumps(generated))))
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'GOOGLE_CLOUD_LOCATION': 'us-central1'}), patch('app.api.discovery.genai.Client', return_value=fake):
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['field'] for item in response.json['patches']], ['last_crop'])
        self.assertEqual(response.json['patches'][0]['evidence_turn_id'], old_turn)

    def test_unique_prior_evidence_recovers_missing_turn_id(self):
        import json
        self.body['history'] = [{'turn_id': 'farmer-earlier', 'speaker': 'farmer', 'text': 'Foi banana.'}]
        self.body['transcript'] = 'Sim.'
        generated = {'patches': [{'field': 'last_crop', 'operation': 'set', 'value': {'crop': 'banana'},
            'status': 'confirmed', 'evidence_excerpt': 'Foi banana'}]}
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text=json.dumps(generated))))
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'GOOGLE_CLOUD_LOCATION': 'us-central1'}), patch('app.api.discovery.genai.Client', return_value=fake):
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['patches'][0]['evidence_turn_id'], 'farmer-earlier')

    def test_harvest_allows_qualitative_and_explicit_estimates(self):
        base = {'field': 'last_harvest_result', 'operation': 'set', 'status': 'confirmed', 'evidence_excerpt': 'Foi boa'}
        self.assertTrue(_validate_value(Patch(**base, value={'qualitative_result': 'good'})))
        self.assertTrue(_validate_value(Patch(**base, value={'quantity': 50, 'unit': 'sacas'})))
        self.assertTrue(_validate_value(Patch(**base, value={'financial_amount': 12000, 'currency': 'BRL'})))
        self.assertFalse(_validate_value(Patch(**base, value={'quantity': 50})))

    def test_missing_vertex_configuration_is_explicit(self):
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "", "GOOGLE_CLOUD_LOCATION": ""}):
            self.assertEqual(self.client.post('/api/interview/extract', json=self.body).status_code, 503)

    def test_patch_taxonomy_rejects_unknown_fields_and_enums(self):
        base = {"field": "irrigation", "operation": "set", "value": {"water_regime": "rainfed", "irrigation_method": "none", "automated": False}, "status": "confirmed", "confidence": "high", "evidence_excerpt": "Não tenho irrigação"}
        self.assertTrue(_validate_value(Patch(**base)))
        self.assertFalse(_validate_value(Patch(**{**base, "field": "geometry"})))
        self.assertFalse(_validate_value(Patch(**{**base, "value": {"water_regime": "magic"}})))

    def test_generation_schema_uses_canonical_field_and_status_enums(self):
        properties = GenerationPatch.model_json_schema()['properties']
        self.assertEqual(set(properties['field']['enum']), FIELDS)
        self.assertEqual(set(properties['status']['enum']), {'confirmed', 'uncertain', 'unknown'})

    def test_goal_with_empty_generated_value_is_classified_from_explicit_evidence(self):
        import json
        self.body['transcript'] = 'É fazer dinheiro sem arriscar muito.'
        generated = {"patches": [{"field": "primary_goal", "operation": "set", "value": {}, "status": "confirmed", "confidence": "high", "evidence_excerpt": "fazer dinheiro sem arriscar muito"}], "warnings": []}
        responses = iter([generated, {"category": "maximize_profit"}])
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text=json.dumps(next(responses)))))
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_CLOUD_LOCATION": "us-central1", "GOOGLE_CLOUD_EXTRACTION_LOCATION": "us"}), patch('app.api.discovery.genai.Client', return_value=fake):
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['patches'][0]['field'], 'primary_goal')
        self.assertEqual(response.json['patches'][0]['value']['category'], 'maximize_profit')

    def test_recovery_covers_all_essential_value_shapes(self):
        import json
        examples = [
            ('last_crop', 'Foi banana.', {'crop': 'banana'}),
            ('previous_crop', 'Era cebola.', {'crop': 'cebola'}),
            ('last_harvest_result', 'A colheita foi ruim.', {'qualitative_result': 'poor'}),
            ('main_difficulties', 'Faltou chuva.', {'categories': ['drought']}),
            ('irrigation', 'Não tenho irrigação.', {'water_regime': 'rainfed', 'irrigation_method': 'none'}),
            ('mechanization', 'Tenho um trator pequeno.', {'work_mode': 'unknown', 'equipment': ['trator pequeno']}),
            ('primary_goal', 'Quero ganhar dinheiro.', {'category': 'maximize_profit'}),
        ]
        for field, transcript, recovered in examples:
            with self.subTest(field=field):
                self.body['transcript'] = transcript
                self.body['assistant_context'] = 'Pergunta anterior sobre a lavoura.'
                generated = {'patches': [{'field': field, 'operation': 'set', 'value': {}, 'status': 'confirmed', 'confidence': 'high', 'evidence_excerpt': transcript}], 'warnings': []}
                replies = iter([generated, recovered])
                calls = []
                def generate_content(**kwargs):
                    calls.append(kwargs)
                    return SimpleNamespace(text=json.dumps(next(replies)))
                fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
                with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'GOOGLE_CLOUD_LOCATION': 'us-central1'}), patch('app.api.discovery.genai.Client', return_value=fake):
                    response = self.client.post('/api/interview/extract', json=self.body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([item['field'] for item in response.json['patches']], [field])
                self.assertEqual(len(calls), 2)
                self.assertIn('Pergunta anterior', calls[0]['contents'])

    def test_short_answer_retries_with_previous_question(self):
        import json
        self.body['transcript'] = 'Foi banana.'
        self.body['assistant_context'] = 'O que você plantou por último nessa área?'
        generated = {'patches': [{'field': 'last_crop', 'operation': 'set', 'value': {}, 'status': 'confirmed', 'evidence_excerpt': 'banana'}], 'warnings': []}
        replies = iter([{'patches': [], 'warnings': []}, generated, {'crop': 'banana'}])
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text=json.dumps(next(replies)))))
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'GOOGLE_CLOUD_LOCATION': 'us-central1'}), patch('app.api.discovery.genai.Client', return_value=fake):
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['patches'][0]['field'], 'last_crop')

    def test_explicit_unknown_answer_gets_canonical_reason(self):
        import json
        self.body['transcript'] = 'Não lembro.'
        self.body['assistant_context'] = 'O que você plantou antes?'
        generated = {'patches': [{'field': 'previous_crop', 'operation': 'set', 'value': {}, 'status': 'unknown', 'evidence_excerpt': 'Não lembro'}], 'warnings': []}
        replies = iter([generated, {'reason': 'does_not_remember'}])
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: SimpleNamespace(text=json.dumps(next(replies)))))
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'GOOGLE_CLOUD_LOCATION': 'us-central1'}), patch('app.api.discovery.genai.Client', return_value=fake):
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['patches'][0]['status'], 'unknown')
        self.assertEqual(response.json['patches'][0]['unknown_reason'], 'does_not_remember')

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
        model_calls = []
        def generate_content(**kwargs):
            model_calls.append(kwargs)
            return SimpleNamespace(text=json.dumps({"patches": patches, "warnings": []}))
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project", "GOOGLE_CLOUD_LOCATION": "us-central1", "GOOGLE_CLOUD_EXTRACTION_LOCATION": "us"}), patch('app.api.discovery.genai.Client', return_value=fake) as client_factory:
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['patches']), 5)
        self.assertIs(model_calls[0]['config'].response_schema, GenerationExtraction)
        options = client_factory.call_args.kwargs
        self.assertEqual(options['project'], 'test-project')
        self.assertEqual(options['location'], 'us')
        self.assertTrue(options['vertexai'])
        self.assertEqual(options['http_options'].api_version, 'v1')
        self.assertEqual(options['http_options'].base_url, 'https://aiplatform.us.rep.googleapis.com')

    def test_audit_finds_second_field_after_partial_first_pass(self):
        import json
        self.body['transcript'] = 'Plantei milho, antes tinha soja.'
        self.body['profile_snapshot'] = {'fields': {
            'last_crop': {'status': 'pending', 'value': None},
            'previous_crop': {'status': 'pending', 'value': None},
        }}
        first = {'patches': [{'field': 'last_crop', 'operation': 'set', 'value': {'crop': 'milho'},
            'status': 'confirmed', 'evidence_excerpt': 'Plantei milho'}]}
        audit = {'patches': [{'field': 'previous_crop', 'operation': 'set', 'value': {'crop': 'soja'},
            'status': 'confirmed', 'evidence_excerpt': 'antes tinha soja'}]}
        replies = iter([first, audit])
        calls = []
        def generate_content(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=json.dumps(next(replies)))
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'GOOGLE_CLOUD_LOCATION': 'us-central1'}), patch('app.api.discovery.genai.Client', return_value=fake):
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item['field'] for item in response.json['patches']}, {'last_crop', 'previous_crop'})
        self.assertEqual(len(calls), 2)

    def test_audit_failure_preserves_first_pass(self):
        import json
        self.body['transcript'] = 'Plantei milho.'
        self.body['profile_snapshot'] = {'fields': {
            'last_crop': {'status': 'pending', 'value': None},
            'previous_crop': {'status': 'pending', 'value': None},
        }}
        first = {'patches': [{'field': 'last_crop', 'operation': 'set', 'value': {'crop': 'milho'},
            'status': 'confirmed', 'evidence_excerpt': 'Plantei milho'}]}
        calls = 0
        def generate_content(**_):
            nonlocal calls
            calls += 1
            if calls == 1:
                return SimpleNamespace(text=json.dumps(first))
            raise RuntimeError('audit unavailable')
        fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test-project', 'GOOGLE_CLOUD_LOCATION': 'us-central1'}), patch('app.api.discovery.genai.Client', return_value=fake):
            response = self.client.post('/api/interview/extract', json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['field'] for item in response.json['patches']], ['last_crop'])


if __name__ == '__main__':
    unittest.main()
