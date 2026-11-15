import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('agrion_tools_test',Path(__file__).resolve().parents[1]/'app'/'services'/'tools.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ToolsTest(unittest.TestCase):
    def test_climate_tools_registered_and_forward_results(self):
        class Climate:
            def nasa_daily(self, **args):return {'ok':True,'data':{'status':'partial','provenance':{'provider':'NASA POWER'},'args':args}}
            def rainfall(self, **args):return {'ok':True,'data':{'result':{'total_mm':0}}}
            def gdd(self, **args):return {'ok':False,'error':{'code':'DATA_INCOMPLETE'}}
        tools=module.AnalysisTools(climate=Climate())
        names={entry['name'] for entry in tools.declarations()}
        self.assertTrue({'nasa_clima_diario','chuva_acumulada','graus_dia_acumulados'}<=names)
        self.assertFalse(any('meteomatics' in name for name in names))
        location={'latitude':-16.5,'longitude':-49.3}
        nasa=tools.execute('nasa_clima_diario',{'location':location,'start_date':'2025-01-01','end_date':'2025-01-02','parameters':['T2M']})
        self.assertEqual(nasa['data']['status'],'partial')
        self.assertEqual(nasa['data']['provenance']['provider'],'NASA POWER')
        self.assertEqual(tools.execute('chuva_acumulada',{'location':location,'reference_date':'2025-01-02'})['data']['result']['total_mm'],0)
        self.assertEqual(tools.execute('graus_dia_acumulados',{})['error']['code'],'DATA_INCOMPLETE')

    def test_climate_bad_parameters_are_reported(self):
        class Climate:
            def nasa_daily(self, **kwargs):raise ValueError('inválido')
            def rainfall(self, **kwargs):return {}
            def gdd(self, **kwargs):return {}
        self.assertEqual(module.AnalysisTools(climate=Climate()).execute('nasa_clima_diario',{})['error'],'invalid_arguments')
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
