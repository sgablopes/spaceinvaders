import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('agrion_tools_test',Path(__file__).resolve().parents[1]/'app'/'services'/'tools.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ToolsTest(unittest.TestCase):
    def test_faostat_catalog_and_prices_reject_ambiguous_or_unbounded_queries(self):
        calls=[]
        tools=module.AnalysisTools(request=lambda path,params:(calls.append((path,params)) or {'items':[],'source':{'provider':'FAOSTAT'}}))
        self.assertEqual(tools.execute('faostat_paises',{'q':'Brasil'})['data']['source']['provider'],'FAOSTAT')
        self.assertEqual(tools.execute('faostat_produtos',{'q':'Maize','country_iso2':'BR'})['data']['items'],[])
        self.assertEqual(tools.execute('faostat_precos',{'country_iso2':'BR','item_code':'56','start_year':2024,'end_year':2024})['data']['items'],[])
        self.assertEqual(calls[-1][0],'/v1/data/faostat/prices')
        self.assertEqual(calls[-1][1]['limit'],10)
        self.assertEqual(tools.execute('faostat_precos',{'country_iso2':'BR','area_code':'21','item_code':'56'})['error'],'invalid_arguments')
        self.assertEqual(tools.execute('faostat_precos',{'country_iso2':'BR','item_code':'56','limit':500})['error'],'invalid_arguments')

    def test_aquacrop_dispatches_declared_scenario_and_preserves_response(self):
        class Climate:
            def aquacrop(self,inputs):return {'ok':True,'data':{'scenario_id':inputs['scenario_id'],'limitations':['simulação']}}
        tools=module.AnalysisTools(climate=Climate())
        result=tools.execute('simular_aquacrop',{'inputs_json':'{"scenario_id":"teste"}'})
        self.assertEqual(result['data']['limitations'],['simulação'])
        self.assertEqual(tools.execute('simular_aquacrop',{'inputs_json':'x'})['error'],'invalid_arguments')

    def test_forecast_and_indicators_use_reviewed_adapters(self):
        calls=[]
        class Climate:
            def forecast(self,**args):calls.append(('forecast',args));return {'ok':True,'data':{'provider_used':'Meteomatics'}}
            def indicator(self,indicator_id,inputs):calls.append((indicator_id,inputs));return {'ok':True,'data':{'status':'partial','provenance':[{'provider':'NASA POWER'}]}}
        tools=module.AnalysisTools(climate=Climate())
        names={item['name'] for item in tools.declarations()}
        self.assertTrue({'previsao_tempo','sequencia_seca','exposicao_termica','evapotranspiracao_cultura','variacao_hidrica','margem_cenario'}<=names)
        response=tools.execute('previsao_tempo',{'location':{'latitude':0,'longitude':0},'start_time':'2030-01-01T00:00:00Z','end_time':'2030-01-01T01:00:00Z','step_hours':1,'parameters':['temperature']})
        self.assertEqual(response['data']['provider_used'],'Meteomatics')
        self.assertEqual(calls[0][1]['provider'],'auto')
        self.assertEqual(tools.execute('previsao_tempo',{'provider':'auto'})['error'],'invalid_arguments')
        self.assertEqual(tools.execute('sequencia_seca',{'inputs_json':'{"rain_threshold_mm":1}'})['data']['status'],'partial')
        self.assertEqual(calls[1][0],'I03')
        self.assertEqual(tools.execute('margem_cenario',{'inputs_json':'not json'})['error'],'invalid_arguments')

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
