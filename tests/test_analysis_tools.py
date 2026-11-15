import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('agrion_tools_test',Path(__file__).resolve().parents[1]/'app'/'services'/'tools.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ToolsTest(unittest.TestCase):
    def test_query_preserves_source_and_pagination(self):
        calls=[]
        def request(path, params):
            calls.append((path,params))
            return {'source':{'sha256':'hash'},'total':40,'items':[{'source_row':2}]}
        tools=module.AnalysisTools(base_url='http://localhost:8001',request=request)
        result=tools.execute('requisitos_cultura',{'q':'milho','limit':10,'offset':20,'filtros_json':'{"crop_id":"ECO_1"}'})
        self.assertEqual(result['data']['source']['sha256'],'hash')
        self.assertEqual(calls[0][1]['offset'],20)
        self.assertIn('crop_id',calls[0][1]['filtros'])

    def test_invalid_arguments_and_unavailable_service(self):
        def unavailable(*args):raise TimeoutError()
        tools=module.AnalysisTools(request=unavailable)
        self.assertEqual(tools.execute('ponto_gaez',{'layer':'x','latitude':91,'longitude':0})['error'],'invalid_arguments')
        self.assertEqual(tools.execute('buscar_culturas',{'limit':500})['error'],'invalid_arguments')
        self.assertEqual(tools.execute('inventada',{})['error'],'unknown_tool')
        self.assertEqual(tools.execute('buscar_culturas',{'q':'soja'})['error'],'analysis_unavailable')

    def test_gaez_point_keeps_units_and_nodata(self):
        tools=module.AnalysisTools(request=lambda path,params:{'status':'nodata','unit':None,'value':None})
        result=tools.execute('ponto_gaez',{'layer':'DATA/test.tif','latitude':-16.5,'longitude':-49.3})
        self.assertEqual(result['data']['status'],'nodata')
        self.assertIsNone(result['data']['unit'])
