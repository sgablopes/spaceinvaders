import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from datetime import date, datetime, timezone

ROOT=Path(__file__).resolve().parents[1]/'app'/'services'
package=ModuleType('dashboard_test_services');package.__path__=[str(ROOT)];sys.modules[package.__name__]=package
def load(name):
    spec=importlib.util.spec_from_file_location('dashboard_test_services.'+name,ROOT/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod);return mod
load('climate_tools');load('engine');dashboard=load('dashboard_data')


class DashboardDataTest(unittest.TestCase):
    def test_market_uses_real_tool_price_and_keeps_zero(self):
        import json
        class Engine:
            def run(self,**kwargs):
                return SimpleNamespace(text=json.dumps({'summary':'Referência histórica para milho.','item_code':'56'}),tool_evidence=({'tool':'faostat_candidatos','result':{'data':{'candidates':[{'item_code':'56'}]}}},{'tool':'faostat_ultimo_preco','arguments':{'item_code':'56'},'result':{'data':{'selection_status':'found','frequency':'annual','items':[{'item_code':'56','value':0,'value_kind':'usd_per_tonne','unit':'USD','year':2024,'area':'Brazil','item':'Maize'}]}}}))
        result=dashboard.market_section(self.context,Engine())
        self.assertEqual(result['price']['value'],0)
        self.assertEqual(result['price']['year'],2024)

    def test_market_keeps_qualitative_summary_when_price_is_ambiguous(self):
        class Engine:
            def run(self,**kwargs):return SimpleNamespace(text='{"summary":"Considere as informações disponíveis.","item_code":"56"}',tool_evidence=({'tool':'faostat_ultimo_preco','arguments':{'item_code':'56'},'result':{'data':{'selection_status':'ambiguous','items':[]}}},))
        result=dashboard.market_section(self.context,Engine())
        self.assertEqual(result['status'],'ready')
        self.assertIsNone(result['price'])
    def setUp(self):
        self.context={'property':{'center_point':{'coordinates':[-49.3,-16.5]}},'agricultural_profile':{'fields':{'current_crop':{'status':'confirmed','value':{'crop':'milho'}},'planting_date':{'status':'confirmed','value':{'date':'2025-01-01'}}}}}

    def test_forecast_uses_future_intervals_and_preserves_zero(self):
        class Tools:
            def forecast(self,location,start,end,step,parameters,**options):
                self.request=(location,start,end,options)
                return {'ok':True,'data':{'generated_at':'2025-01-01T00:00:00Z','provenance':[{'provider':'Meteomatics'}],'result':{'parameters':{'precipitation':{'unit':'mm'}},'series':[{'valid_time':'2025-01-01T03:00:00Z','interval_start':'2025-01-01T02:00:00Z','precipitation_mm':0}]}}}
        tools=Tools();result=dashboard.forecast_section(self.context,tools,datetime(2025,1,1,tzinfo=timezone.utc))
        self.assertEqual(result['metrics'][0]['value'],0)
        self.assertEqual(result['metrics'][0]['value_kind'],'forecast')
        self.assertEqual(tools.request[0],{'latitude':-16.5,'longitude':-49.3})
        self.assertEqual(tools.request[3]['provider'],'auto')

    def test_open_meteo_fallback_is_attributed(self):
        class Tools:
            def forecast(self,*args,**kwargs):
                return {'ok':True,'data':{'provenance':[{'provider':'Open-Meteo','documentation_url':'https://open-meteo.com/'}],'result':{'parameters':{'temperature':{'unit':'°C'}},'series':[{'valid_time':'2025-01-01T03:00:00Z','temperature_c':25}]}}}
        result=dashboard.forecast_section(self.context,Tools(),datetime(2025,1,1,tzinfo=timezone.utc))
        self.assertEqual(result['source'],'Open-Meteo')
        self.assertIn('não comercial',result['note'])

    def test_rainfall_requires_source_and_preserves_zero(self):
        class Tools:
            def rainfall(self,location,reference):return {'ok':True,'data':{'result':{'indicators':{'I02':{'provenance':[{'provider':'NASA POWER'}],'windows':[{'window_days':7,'total_mm':0,'start_date':'2024-12-23','end_date':'2024-12-29'}]}}}}}
        result=dashboard.rainfall_section(self.context,Tools(),date(2024,12,31))
        self.assertEqual(result['metrics'][0]['value'],0)
        self.assertEqual(result['metrics'][0]['source'],'NASA POWER')

    def test_stage_requires_actual_tool_source_and_exact_date(self):
        url='https://example.org/source'
        class Engine:
            def run(self,**kwargs):return SimpleNamespace(text='{"phase":"Crescimento","reason":"Referência para milho","harvest_window":null,"source_urls":["https://example.org/source"]}',tool_evidence=({'result':{'data':{'source_url':url}}},))
        self.assertEqual(dashboard.stage_section(self.context,Engine())['status'],'ready')
        class InvalidEngine:
            def run(self,**kwargs):return SimpleNamespace(text='{"phase":"Crescimento","reason":"Referência","harvest_window":null,"source_urls":["https://inventada.org"]}',tool_evidence=())
        self.assertEqual(dashboard.stage_section(self.context,InvalidEngine())['status'],'unavailable')
        self.context['agricultural_profile']['fields']['planting_date']['value']['date']='2025-01'
        self.assertEqual(dashboard.stage_section(self.context,Engine())['status'],'unavailable')

    def test_confidence_is_separate_and_rejects_invalid_values(self):
        import json
        class Engine:
            def run(self,**kwargs):return SimpleNamespace(text=json.dumps({'phase':'Crescimento','reason':'Referência','harvest_window':'Dezembro','source_urls':['https://example.org/a'],'phase_confidence':75,'phase_confidence_reason':'Data conhecida','harvest_confidence':120,'harvest_confidence_reason':'Estimativa geral'}),tool_evidence=({'result':{'url':'https://example.org/a'}},))
        result=dashboard.stage_section(self.context,Engine())
        self.assertEqual(result['phase_confidence']['value'],75)
        self.assertIsNone(result['harvest_confidence'])

    def test_news_needs_search_url_date_and_suggestions(self):
        class Engine:
            def run(self,**kwargs):return SimpleNamespace(text='{"items":[{"title":"Notícia","summary":"Resumo","date":"2026-11-01","url":"https://example.org/a"}]}',tool_evidence=({'tool':'pesquisar_internet','result':{'text':'Publicado em 2026-11-01','sources':[{'url':'https://example.org/a'}],'search_entry_point':'<div>Busca</div>'}},))
        result=dashboard.news_section(self.context,Engine())
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['items'][0]['date'],'2026-11-01')

    def test_gdd_requires_reference_from_another_tool_and_correct_location(self):
        reference='https://example.org/base'
        evidence=[{'tool':'fontes_agricolas','result':{'data':{'reference':reference}}},{'tool':'graus_dia_acumulados','arguments':{'location':{'latitude':-16.5,'longitude':-49.3},'start_date':'2025-01-01'},'result':{'ok':True,'data':{'result':{'indicators':{'I01':{'value':0,'unit':'degree_day_c','base_temperature_c':10,'base_temperature_reference':reference,'provenance':[{'provider':'NASA POWER'}]}}}}}}]
        self.assertEqual(dashboard._grounded_gdd(evidence,self.context,'2025-01-01')['value'],0)
        self.assertIsNone(dashboard._grounded_gdd(evidence[1:],self.context,'2025-01-01'))
        self.assertIsNone(dashboard._grounded_gdd(evidence,self.context,'2025-01-02'))

    def test_daily_keeps_only_items_with_sources_from_tools(self):
        class Engine:
            def run(self,**kwargs):
                return SimpleNamespace(text='{"summary":{"text":"Resumo","source_urls":["https://example.org/source"]},"observations":[],"recommendations":[{"text":"Ação","source_urls":["https://inventada.org"]}]}',tool_evidence=({'result':{'data':{'source_url':'https://example.org/source'}}},))
        result=dashboard.daily_section(self.context,Engine())
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['summary']['text'],'Resumo')
        self.assertEqual(result['recommendations'],[])

    def test_daily_without_verified_sources_is_unavailable(self):
        class Engine:
            def run(self,**kwargs):return SimpleNamespace(text='{"summary":{"text":"X","source_urls":["https://inventada.org"]},"observations":[],"recommendations":[]}',tool_evidence=())
        self.assertEqual(dashboard.daily_section(self.context,Engine())['status'],'unavailable')

    def test_daily_accepts_partial_farmer_context_and_contextual_suggestion(self):
        class Engine:
            def run(self,**kwargs):return SimpleNamespace(text='{"summary":{"text":"Milho informado pelo agricultor.","source_urls":[]},"observations":[],"recommendations":[{"text":"Acompanhe o desenvolvimento da cultura.","source_urls":[]}]}',tool_evidence=())
        result=dashboard.daily_section(self.context,Engine())
        self.assertEqual(result['status'],'ready')
        self.assertEqual(result['summary']['source_kind'],'farmer_context')
        self.assertEqual(result['recommendations'][0]['source_kind'],'farmer_context')
