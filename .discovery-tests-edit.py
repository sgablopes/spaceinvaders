from pathlib import Path
p=Path('tests/test_discovery.py');s=p.read_text(encoding='utf-8')
s=s.replace("from app.api.discovery import FIELDS,", "from app.api.discovery import ESSENTIAL_FIELDS, _speech_config, FIELDS,")
s=s.replace("self.assertTrue(_validate_value(Patch(**base, field='previous_crop', value={'crop': None, 'no_previous_cultivation': True})))", "self.assertTrue(_validate_value(Patch(**base, field='last_crop', value={'crop': None, 'no_previous_cultivation': True})))")
s=s.replace("self.assertEqual(values['previous_crop']['no_previous_cultivation'], True)", "self.assertNotIn('previous_crop', values)")
s=s.replace("('previous_crop', 'Era cebola.', {'crop': 'cebola'})", "('current_crop', 'Agora tenho cebola.', {'crop': 'cebola'})")
s=s.replace("{'field': 'previous_crop', 'operation': 'set', 'value': {}, 'status': 'unknown'", "{'field': 'last_crop', 'operation': 'set', 'value': {}, 'status': 'unknown'")
# Update multi-crop/audit fixtures to the two actual seasons, preserving their original assertions.
a=s.index('    def test_multiple_provider_patches');prefix=s[:a];tail=s[a:]
tail=tail.replace('"field": "last_crop"','"field": "current_crop"').replace('"field": "previous_crop"','"field": "last_crop"')
tail=tail.replace("'last_crop'", "'current_crop'").replace("'previous_crop'", "'last_crop'")
s=prefix+tail
s+='''
    def test_active_contract_and_voice_configuration(self):
        import re
        from pathlib import Path
        js = (Path(__file__).resolve().parents[1] / 'app/static/discovery-profile.js').read_text(encoding='utf-8')
        fields = re.search(r"const ESSENTIAL = \\[(.*?)\\]", js).group(1)
        self.assertEqual(set(re.findall(r"'([^']+)'", fields)), set(ESSENTIAL_FIELDS))
        self.assertNotIn('previous_crop', FIELDS)
        self.assertEqual(_speech_config('pt-BR')['voiceConfig']['prebuiltVoiceConfig']['voiceName'], 'Orus')
        self.assertEqual(_speech_config('en-US'), {'languageCode': 'en-US'})
        with self.assertRaises(ValueError):
            _speech_config('es-US')

    def test_no_current_crop_is_known_absence_not_unknown(self):
        base = {'field': 'current_crop', 'operation': 'set', 'status': 'confirmed', 'evidence_excerpt': 'Nothing planted'}
        self.assertTrue(_validate_value(Patch(**base, value={'crop': None, 'not_planted': True})))
        self.assertFalse(_validate_value(Patch(**base, value={'crop': 'corn', 'not_planted': True})))

    def test_qualitative_harvest_does_not_trigger_estimate_audit(self):
        import json
        self.body['transcript'] = 'The harvest was good.'
        self.body['profile_snapshot'] = {'fields': {'last_harvest_result': {'status': 'pending', 'value': None}}}
        generated = {'patches': [{'field': 'last_harvest_result', 'operation': 'set', 'status': 'confirmed',
            'value': {'qualitative_result': 'good'}, 'evidence_excerpt': 'harvest was good'}]}
        with patch.dict(os.environ, {'GOOGLE_CLOUD_PROJECT': 'test', 'GOOGLE_CLOUD_LOCATION': 'us-central1'}), patch('app.api.discovery.genai.Client') as factory:
            factory.return_value.models.generate_content.return_value = SimpleNamespace(text=json.dumps(generated))
            response = self.client.post('/api/interview/extract', json=self.body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(factory.return_value.models.generate_content.call_count, 1)
        states = {field: 'confirmed' for field in ESSENTIAL_FIELDS}
        prompt = _live_state_instruction('Agrion', {'fields': states, 'intro_stage': 2, 'harvest_estimate_pending': True})
        self.assertNotIn('sacas', prompt)
'''
p.write_text(s,encoding='utf-8')
