import unittest
from unittest.mock import patch
from app import create_app
from app.services.engine import EngineResult, EngineUnavailableError


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.client=create_app({'TESTING':True}).test_client()
        self.context={'property':{'id':'p'},'agricultural_profile':{'fields':{'current_crop':{'status':'confirmed','value':{'crop':'milho'}},'planting_date':{'status':'unknown','value':None}}}}

    @patch('app.api.dashboard.AgrionEngine')
    def test_only_confirmed_fields_are_selected(self,engine):
        engine.return_value.run.return_value=EngineResult('{"highlight_fields":["current_crop","planting_date"]}','test')
        response=self.client.post('/api/dashboard/bootstrap',json={'context':self.context})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['highlight_fields'],['current_crop'])
        self.assertEqual(response.json['sections']['conditions']['status'],'unavailable')
        self.assertEqual(engine.return_value.run.call_args.kwargs['mode'],'dashboard')

    @patch('app.api.dashboard.AgrionEngine')
    def test_invalid_or_failed_analysis_returns_error(self,engine):
        for result in [EngineResult('{"highlight_fields":["imaginary"]}','test'),EngineUnavailableError('offline')]:
            engine.return_value.run.side_effect=result if isinstance(result,Exception) else None
            engine.return_value.run.return_value=result
            self.assertEqual(self.client.post('/api/dashboard/bootstrap',json={'context':self.context}).status_code,503)

    @patch('app.api.dashboard.forecast_section')
    def test_forecast_section_propagates_status_without_fabricating_values(self, forecast):
        forecast.return_value={'status':'unavailable','metrics':[],'note':'Fonte indisponível.'}
        response=self.client.post('/api/dashboard/forecast',json={'context':self.context})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['result']['metrics'],[])
        self.assertEqual(response.json['property_id'],'p')

    @patch('app.api.dashboard.AnalysisTools')
    def test_market_scenario_requires_explicit_inputs_and_uses_historical_selection(self, tools):
        tools.return_value.execute.return_value={'ok':True,'data':{'result':{'indicators':{'I14':{'revenue':0}}}}}
        inputs={'area_code':'21','item_code':'56','year':2024,'area_ha':2,'yield_t_ha':0,'cost_per_ha':0}
        body={'property_id':'p','action':'scenario','inputs':inputs}
        response=self.client.post('/api/dashboard/market',json=body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['result']['result']['indicators']['I14']['revenue'],0)
        import json
        sent=json.loads(tools.return_value.execute.call_args.args[1]['inputs_json'])
        self.assertEqual(sent['faostat_price']['year'],2024)
        self.assertEqual(sent['currency'],'USD')
        self.assertNotIn('price_per_t',sent)
        self.assertEqual(self.client.post('/api/dashboard/market',json={**body,'inputs':{**inputs,'area_ha':0}}).status_code,400)
        self.assertEqual(self.client.post('/api/dashboard/market',json={**body,'inputs':{k:v for k,v in inputs.items() if k!='cost_per_ha'}}).status_code,400)

    @patch('app.api.dashboard.AnalysisTools')
    def test_market_tool_errors_are_explicit(self,tools):
        tools.return_value.execute.return_value={'error':'analysis_unavailable'}
        response=self.client.post('/api/dashboard/market',json={'property_id':'p','action':'prices','inputs':{}})
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json['error'],'market_unavailable')
