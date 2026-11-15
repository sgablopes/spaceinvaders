import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace, ModuleType


spec = importlib.util.spec_from_file_location('agrion_engine_test', Path(__file__).resolve().parents[1] / 'app' / 'services' / 'engine.py')
engine = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine
spec.loader.exec_module(engine)


class EngineTest(unittest.TestCase):
    def test_context_history_and_language_reach_provider(self):
        calls = []
        def generate(model, contents, instruction):
            calls.append((model, contents, instruction))
            return ' Resposta '
        service = engine.AgrionEngine(generate=generate, model='test-model')
        result = service.run('O que sabemos?', {'crop': 'milho'}, [{'role': 'user', 'text': 'Olá'}], 'pt-BR')
        self.assertEqual(result.text, 'Resposta')
        self.assertEqual(result.tools_used, ())
        self.assertEqual(calls[0][1][0]['parts'][0]['text'], 'Olá')
        self.assertIn('milho', calls[0][1][1]['parts'][0]['text'])
        self.assertIn('pt-BR', calls[0][2])
        self.assertIn('priorize consultar as ferramentas', calls[0][2])
        self.assertIn('referências identificáveis', calls[0][2])
        self.assertIn('Seja conciso', calls[0][2])
        self.assertIn('até três frases curtas', calls[0][2])

    def test_invalid_requests_are_rejected(self):
        service = engine.AgrionEngine(generate=lambda *args: 'ok')
        for kwargs in ({'task': ''}, {'task': 'x', 'language': 'xx'}, {'task': 'x', 'history': [{'role': 'system', 'text': 'x'}]}, {'task': 'x', 'context': {'value': float('nan')}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                service.run(**kwargs)

    def test_empty_response_is_reported(self):
        with self.assertRaises(engine.EngineUnavailableError):
            engine.AgrionEngine(generate=lambda *args: '').run('teste')

    def test_vertex_tool_cycle_preserves_model_content(self):
        model_content=object()
        requests=[]
        class Models:
            def generate_content(self, **kwargs):
                requests.append(kwargs)
                if len(requests)==1:
                    return SimpleNamespace(function_calls=[SimpleNamespace(name='buscar_culturas',args={'q':'milho'})],candidates=[SimpleNamespace(content=model_content)])
                return SimpleNamespace(function_calls=[],text='Resultado com fonte')
        class Client:
            def __init__(self,**kwargs):self.models=Models()
            def __enter__(self):return self
            def __exit__(self,*args):pass
        class Part:
            @staticmethod
            def from_function_response(**kwargs):return kwargs
        class Registry:
            def declarations(self):return []
            def execute(self,name,args):return {'data':{'source':'ECOCROP'}}
        fake_types=SimpleNamespace(HttpOptions=lambda **kw:kw,GenerateContentConfig=lambda **kw:kw,AutomaticFunctionCallingConfig=lambda **kw:kw,Tool=lambda **kw:kw,Part=Part,Content=lambda **kw:kw)
        google=ModuleType('google');genai=ModuleType('google.genai');genai.Client=Client;genai.types=fake_types;google.genai=genai
        package=ModuleType('fake_engine_package');package.__path__=[]
        registry=ModuleType('fake_engine_package.tools');registry.AnalysisTools=Registry
        with patch.dict(sys.modules,{'google':google,'google.genai':genai,'fake_engine_package':package,'fake_engine_package.tools':registry}), patch.dict('os.environ',{'GOOGLE_CLOUD_PROJECT':'test','GOOGLE_CLOUD_ENGINE_LOCATION':'us'}), patch.object(engine,'__package__','fake_engine_package'):
            text,used=engine._vertex_generate('model',[], 'instruction')
        self.assertEqual((text,used),('Resultado com fonte',('buscar_culturas',)))
        self.assertIs(requests[1]['contents'][-2],model_content)


if __name__ == '__main__':
    unittest.main()
