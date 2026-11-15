import importlib.util
import io
import json
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

spec=importlib.util.spec_from_file_location('climate_tools_test',Path(__file__).resolve().parents[1]/'app'/'services'/'climate_tools.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
LOCATION={'latitude':-16.5,'longitude':-49.3}


class ClimateToolsTest(unittest.TestCase):
    def test_i14_accepts_exact_faostat_selection_without_inventing_price(self):
        captured=[]
        tools=module.ClimateTools(post=lambda path,payload:(captured.append(payload) or {'status':'ok'}))
        scenario={'start_date':'2025-01-01','end_date':'2025-12-31','crop_id':'maize','area_ha':1,'expected_yield_t_per_ha':2,'cost_per_ha':100,'currency':'USD','assumptions_reference':'Custo e rendimento declarados','faostat_price':{'country_iso2':'BR','item_code':'56','year':2024,'reference':'preço histórico'}}
        self.assertTrue(tools.indicator('I14',scenario)['ok'])
        self.assertNotIn('price_per_t',captured[0]['inputs']['crop_margin'])
        with self.assertRaises(ValueError):tools.indicator('I14',{**scenario,'price_per_t':10})
        with self.assertRaises(ValueError):tools.indicator('I14',{**scenario,'currency':'BRL'})

    def test_aquacrop_returns_aggregate_and_traceability_without_large_daily_series(self):
        tools=module.ClimateTools(post=lambda path,payload:{'result':{'dry_yield_t_ha':3,'daily':[{'date':'2025-01-01'}]},'weather':[{}],'provenance':[{'provider':'NASA'}],'limitations':['cenário']})
        scenario={'scenario_id':'s1','start_date':'2025-01-01','end_date':'2025-01-02','crop':'Maize','location':{'latitude':0,'longitude':0},'weather':{},'soil':{},'initial_water':{},'co2':{},'management':{},'assumptions_reference':'declaração'}
        result=tools.aquacrop(scenario)['data']
        self.assertEqual(result['result']['dry_yield_t_ha'],3)
        self.assertNotIn('daily',result['result'])
        self.assertEqual(result['provenance'][0]['provider'],'NASA')
        with self.assertRaises(ValueError):tools.aquacrop({**scenario,'crop':'Onion'})

    def test_forecast_preserves_provider_and_fallback(self):
        calls=[]
        def post(path,body):
            calls.append((path,body))
            return {'provider_used':'Open-Meteo','fallback_used':True,'provenance':[{'provider':'Open-Meteo'}],'status':'ok'}
        start=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)+timedelta(hours=3)
        result=module.ClimateTools(post=post).forecast(LOCATION,start.isoformat(),(start+timedelta(hours=3)).isoformat(),1,['temperature'],provider='auto')
        self.assertEqual(calls[0][0],'/v1/data/weather/forecast')
        self.assertEqual(result['data']['provider_used'],'Open-Meteo')
        self.assertTrue(result['data']['fallback_used'])

    def test_new_indicators_forward_explicit_inputs_and_partial(self):
        calls=[]
        def post(path,body):
            calls.append((path,body));return {'status':'partial','result':{'indicators':{'I03':{'value':0}}},'provenance':[{'provider':'NASA POWER'}]}
        tools=module.ClimateTools(post=post)
        result=tools.indicator('I03',{'location':LOCATION,'start_date':'2025-01-01','end_date':'2025-01-03','rain_threshold_mm':1})
        self.assertEqual(calls[0][1]['include'],['I03'])
        self.assertEqual(result['data']['result']['indicators']['I03']['value'],0)
        self.assertEqual(result['data']['status'],'partial')
        with self.assertRaises(ValueError):tools.indicator('I07',{'start_date':'2025-01-01','end_date':'2025-01-02','crop_id':'x','growth_stage':'x','kc_catalog_version':'x'})
        with self.assertRaises(ValueError):tools.indicator('I99',{})

    def test_forecast_rejects_naive_or_past_times(self):
        tools=module.ClimateTools(post=lambda *_:self.fail('não deve chamar'))
        with self.assertRaises(ValueError):tools.forecast(LOCATION,'2025-01-01T00:00:00','2025-01-01T01:00:00',1,['temperature'])
        with self.assertRaises(ValueError):tools.forecast(LOCATION,'2025-01-01T00:00:00Z','2025-01-01T01:00:00Z',1,['temperature'])

    def test_remaining_indicator_routing(self):
        requests=[]
        tools=module.ClimateTools(post=lambda path,body:(requests.append((path,body)) or {'status':'ok'}))
        base={'start_date':'2025-01-01','end_date':'2025-01-01','crop_id':'test','growth_stage':'test'}
        tools.indicator('I05',{**base,'threshold_catalog_version':'v1','ecocrop_crop_id':'ECO_289','location':LOCATION})
        water={**base,'kc_catalog_version':'v1','eto_series':[{'date':'2025-01-01','eto_mm_day':4}],'eto_reference':'dado declarado','kc':1,'kc_reference':'fonte declarada'}
        tools.indicator('I07',water)
        tools.indicator('I08',{**water,'assumptions_reference':'declarado','daily_fluxes':[{'date':'2025-01-01','irrigation_mm':0,'capillary_rise_mm':0,'runoff_mm':0,'deep_percolation_mm':0}]})
        tools.indicator('I14',{'start_date':'2025-01-01','end_date':'2025-01-01','crop_id':'test','area_ha':1,'expected_yield_t_per_ha':0,'price_per_t':0,'cost_per_ha':0,'currency':'BRL','assumptions_reference':'declarado'})
        self.assertEqual([item[0] for item in requests],['/v1/analysis/climate','/v1/analysis/water','/v1/analysis/water','/v1/analysis/economics'])
    def test_nasa_preserves_partial_zero_and_provenance(self):
        seen=[]
        def post(path,payload):
            seen.append((path,payload))
            return {'status':'partial','result':{'series':[{'precip_mm_day':0},{'precip_mm_day':None}]},'provenance':{'provider':'NASA POWER'},'quality':{'missing_dates':['2025-01-02']}}
        result=module.ClimateTools(post=post).nasa_daily(LOCATION,'2025-01-01','2025-01-02',['PRECTOTCORR'])
        self.assertEqual(seen[0][0],'/v1/data/nasa-power/daily')
        self.assertEqual(result['data']['result']['series'][0]['precip_mm_day'],0)
        self.assertEqual(result['data']['status'],'partial')
        self.assertEqual(result['data']['provenance']['provider'],'NASA POWER')

    def test_indicator_requests_are_explicit(self):
        seen=[]
        tools=module.ClimateTools(post=lambda path,payload:(seen.append((path,payload)) or {'status':'ok'}))
        tools.rainfall(LOCATION,'2025-10-03','LST')
        tools.gdd(LOCATION,'milho','2025-10-01','2025-10-03',10,'referência declarada')
        self.assertEqual(seen[0][1]['include'],['I02'])
        self.assertEqual(seen[0][1]['inputs']['rainfall']['day_basis'],'LST')
        self.assertEqual(seen[1][1]['include'],['I01'])
        self.assertEqual(seen[1][1]['inputs']['gdd']['base_temperature_reference'],'referência declarada')

    def test_invalid_arguments_do_not_call_provider(self):
        tools=module.ClimateTools(post=lambda *_:self.fail('não deve chamar'))
        for call in [lambda:tools.nasa_daily(LOCATION,'2025-01-02','2025-01-01',['T2M']),lambda:tools.nasa_daily(LOCATION,'2025-01-01','2025-01-02',['T2M','T2M']),lambda:tools.gdd(LOCATION,'milho','2025-01-01','2025-01-02',None),lambda:tools.rainfall({'latitude':float('nan'),'longitude':0},'2025-01-02')]:
            with self.subTest(call=call),self.assertRaises(ValueError):call()

    def test_http_error_and_timeout_are_explicit(self):
        def error(*_):
            data=json.dumps({'error':{'code':'DATA_INCOMPLETE','retryable':False}}).encode()
            raise HTTPError('http://internal',404,'error',{},io.BytesIO(data))
        result=module.ClimateTools(post=error).rainfall(LOCATION,'2025-10-03')
        self.assertEqual(result['error']['code'],'DATA_INCOMPLETE')
        self.assertEqual(result['error']['http_status'],404)
        def timeout(*_):raise TimeoutError()
        self.assertEqual(module.ClimateTools(post=timeout).rainfall(LOCATION,'2025-10-03')['error']['code'],'ANALYSIS_UNAVAILABLE')
