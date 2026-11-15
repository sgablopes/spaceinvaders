import importlib.util
import io
import json
from pathlib import Path
import unittest
from urllib.error import HTTPError

spec=importlib.util.spec_from_file_location('climate_tools_test',Path(__file__).resolve().parents[1]/'app'/'services'/'climate_tools.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
LOCATION={'latitude':-16.5,'longitude':-49.3}


class ClimateToolsTest(unittest.TestCase):
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
