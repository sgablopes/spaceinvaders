import copy
import json
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch
from app import create_app
from app.services.engine import AgrionEngine, EngineUnavailableError
from app.services.planning import analyze


def sample():
    url = 'https://example.org/rotation'
    crop = {'id': 'milho', 'name': 'Milho', 'headline': 'Avaliar milho no próximo ciclo',
            'overview': 'Alternativa a confirmar.', 'conditions': 'Confirmar drenagem.',
            'management': 'Avaliar manejo local.', 'water': 'Verificar irrigação.',
            'labor': 'Confirmar equipe.', 'mechanization': 'Confirmar máquinas.',
            'market': 'Consultar mercado local.', 'caveat': 'Sem laudo de solo.',
            'confidence': 'baixa', 'source_urls': [url]}
    strategy = {'id': 'rotacao', 'name': 'Rotação em avaliação', 'headline': 'Diversificar os ciclos',
                'cycles': [{'crop_id': 'milho', 'purpose': 'Produção', 'window': 'Janela a confirmar'},
                           {'crop_id': 'cobertura', 'purpose': 'Cobertura do solo', 'window': 'Após a colheita'}],
                'benefits': ['Cobertura'], 'constraints': ['Confirmar solo'], 'confidence': 'baixa',
                'source_urls': [url]}
    for key in ('soil', 'water', 'risk', 'cost', 'labor'):
        strategy[key] = {'level': 'a confirmar', 'reason': 'Dados locais necessários.'}
    return {'headline': 'Opções preliminares', 'assumptions': ['Perfil informado'], 'missing_inputs': ['Laudo de solo'],
            'crops': [crop, {**crop, 'id': 'cobertura', 'name': 'Cobertura'}], 'strategies': [strategy]}


class PlanningTest(unittest.TestCase):
    def engine(self, data, evidence=True):
        return SimpleNamespace(run=lambda **kw: SimpleNamespace(text=json.dumps(data),
            tool_evidence=({'tool': 'rotacoes_agricolas', 'result': {'url': 'https://example.org/rotation'}},) if evidence else ()))

    def test_low_confidence_is_preserved(self):
        result = analyze({}, self.engine(sample()))
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(len(result['strategies']), 1)
        self.assertEqual(result['strategies'][0]['confidence'], 'baixa')

    def test_invented_source_becomes_conditional_without_losing_options(self):
        result = analyze({}, self.engine(sample(), False))
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['crops'][0]['source_urls'], [])
        self.assertEqual(result['strategies'][0]['cycles'][1]['window'], 'Janela a confirmar')

    def test_invalid_sibling_does_not_discard_valid_items(self):
        data = sample()
        data['crops'].append({'id': 'invalid'})
        data['strategies'].append({**copy.deepcopy(data['strategies'][0]), 'id': 'bad',
                                   'cycles': [{'crop_id': 'unknown', 'purpose': 'x'}, {'crop_id': 'milho', 'purpose': 'x'}]})
        result = analyze({}, self.engine(data))
        self.assertEqual(len(result['crops']), 2)
        self.assertEqual(len(result['strategies']), 1)
        self.assertEqual(result['status'], 'partial')

    def test_failure_returns_a_finite_empty_state(self):
        engine = SimpleNamespace(run=lambda **kw: (_ for _ in ()).throw(EngineUnavailableError()))
        result = analyze({}, engine)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['crops'], [])
        self.assertTrue(result['missing_inputs'])
        self.assertEqual(analyze({}, self.engine([]))['status'], 'unavailable')

    def test_planning_prompt_has_recovery_and_no_chat_length_limit(self):
        prompts = []
        engine = AgrionEngine(generate=lambda model, contents, instruction: prompts.append(instruction) or '{}')
        engine.run('Planeje', mode='planning')
        self.assertIn('pesquise na internet', prompts[0])
        self.assertIn('baixa confiança nunca', prompts[0])
        self.assertNotIn('até três frases', prompts[0])
        engine.run('Plan crops', context={'ui_language': 'en-US'}, mode='planning')
        self.assertIn('Responda no idioma en-US', prompts[-1])

    @patch('app.api.planning.analyze')
    def test_endpoint_validates_and_keeps_property_identity(self, analysis):
        client = create_app({'TESTING': True}).test_client()
        body = {'context': {'property': {'id': 'p1'}}, 'inputs': {'soil': 'Sem laudo', 'selected_crops': ['Milho']}}
        analysis.return_value = {'status': 'partial'}
        response = client.post('/api/planning/analyze', json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['property_id'], 'p1')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(analysis.call_args.args[0]['planning_inputs']['soil'], 'Sem laudo')
        self.assertEqual(client.post('/api/planning/analyze', json={**body, 'inputs': {'soil': 'x'*601}}).status_code, 400)

    def test_failed_internal_tool_triggers_supplemental_research(self):
        from app.services.planning_provider import generate
        calls = [SimpleNamespace(function_calls=[SimpleNamespace(name='requisitos_cultura', args={'q': 'milho'})],
                                 candidates=[SimpleNamespace(content=object())]),
                 SimpleNamespace(function_calls=[], text=json.dumps(sample()))]
        client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: calls.pop(0)))
        # MagicMock oferece protocolo de contexto para o cliente Vertex de teste.
        from unittest.mock import MagicMock
        manager = MagicMock();manager.__enter__.return_value = client
        types = SimpleNamespace(HttpOptions=lambda **kw: kw, GenerateContentConfig=lambda **kw: kw,
            Tool=lambda **kw: kw, AutomaticFunctionCallingConfig=lambda **kw: kw,
            Part=SimpleNamespace(from_function_response=lambda **kw: kw), Content=lambda **kw: kw)
        fake = SimpleNamespace(genai=SimpleNamespace(Client=lambda **kw: manager))
        with patch.dict(sys.modules, {'google': fake, 'google.genai': fake.genai, 'google.genai.types': types}), \
             patch('app.services.tools.AnalysisTools') as registry, \
             patch('app.services.web_search.search', return_value={'text': 'Referência', 'sources': []}) as search, \
             patch.dict('os.environ', {'GOOGLE_CLOUD_PROJECT': 'test'}):
            fake.genai.types = types
            registry.return_value.declarations.return_value = []
            registry.return_value.execute.return_value = {'error': 'analysis_unavailable'}
            contents = [{'role': 'user', 'parts': [{'text': '{"context":{"property":{"location_label":"Goiás"}}}'}]}]
            text, used, evidence = generate('model', contents, 'instruction')
        self.assertEqual(search.call_count, 2)
        self.assertIn('requisitos_cultura', used)
        self.assertEqual(len(evidence), 3)
        self.assertEqual(json.loads(text)['headline'], 'Opções preliminares')
