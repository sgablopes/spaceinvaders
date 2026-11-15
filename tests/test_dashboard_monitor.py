import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]/'app'/'services'
package=ModuleType('monitor_test_services');package.__path__=[str(ROOT)];sys.modules[package.__name__]=package
def load(name):
    spec=importlib.util.spec_from_file_location(package.__name__+'.'+name,ROOT/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod);return mod
load('engine');monitor=load('dashboard_monitor')


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.sample={'id':'sample_1','kind':'simulation','observed_at':self.now.isoformat(),'readings':[{'key':'wind_speed','value':20,'unit':'m/s'}]}
        self.alert={'event_key':'wind_risk','decision':'active','severity':'high','title':'Vento','summary':'Vento simulado','triggering_metric_keys':['wind_speed'],'recommended_action':'Avaliar condições','source_urls':['https://example.org/wind']}
    def engine(self,alert,evidence=True):
        result={'profile':{'variables':['wind_speed'],'notes':'Avaliação de teste'},'alerts':[alert]}
        return SimpleNamespace(run=lambda **kwargs:SimpleNamespace(text=json.dumps(result),tool_evidence=({'result':{'url':'https://example.org/wind'}},) if evidence else ()))
    def test_accepts_simulated_alert_with_retrieved_reference(self):
        result=monitor.evaluate({},self.sample,[],self.engine(self.alert),self.now)
        self.assertEqual(result['kind'],'simulation')
        self.assertEqual(result['alerts'][0]['event_key'],'wind_risk')
    def test_does_not_accept_invented_source_or_unsupported_resolution(self):
        self.assertEqual(monitor.evaluate({},self.sample,[],self.engine(self.alert,False),self.now)['alerts'],[])
        resolved={**self.alert,'decision':'resolved'}
        self.assertEqual(monitor.evaluate({},self.sample,[],self.engine(resolved),self.now)['alerts'],[])
        previous=[{'event_key':'wind_risk','triggering_metric_keys':['wind_speed','precipitation']}]
        self.assertEqual(monitor.evaluate({},self.sample,previous,self.engine(resolved),self.now)['alerts'],[])
    def test_rejects_non_simulated_or_nonfinite_inputs(self):
        with self.assertRaises(ValueError):monitor.evaluate({},dict(self.sample,kind='sensor'),[],self.engine(self.alert),self.now)
        with self.assertRaises(ValueError):monitor.evaluate({},dict(self.sample,readings=[{'key':'wind_speed','value':float('nan'),'unit':'m/s'}]),[],self.engine(self.alert),self.now)
