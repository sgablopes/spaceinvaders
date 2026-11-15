import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec=importlib.util.spec_from_file_location('search_test',Path(__file__).resolve().parents[1]/'app'/'services'/'web_search.py')
search=importlib.util.module_from_spec(spec);spec.loader.exec_module(search)


class SearchTest(unittest.TestCase):
    def test_returns_grounding_sources_and_suggestions(self):
        meta=SimpleNamespace(search_entry_point=SimpleNamespace(rendered_content='<div>Google</div>'),grounding_chunks=[SimpleNamespace(web=SimpleNamespace(uri='https://example.org/a',title='Fonte'))])
        response=SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=meta)],text='Resultado com fonte')
        client=SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs:response))
        types=SimpleNamespace(Tool=lambda **kwargs:kwargs,GoogleSearch=lambda:object(),GenerateContentConfig=lambda **kwargs:kwargs)
        result=search.search(client,'model','pesquisa agrícola',types)
        self.assertEqual(result['sources'][0]['url'],'https://example.org/a')
        self.assertIn('Google',result['search_entry_point'])
        response.candidates[0].grounding_metadata.search_entry_point=None
        self.assertEqual(search.search(client,'model','pesquisa agrícola',types)['error'],'search_unavailable')
