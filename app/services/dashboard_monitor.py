"""Avaliação de amostras simuladas pelo Core, sem regras agronômicas fixas."""
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .engine import AgrionEngine, EngineError


def evaluate(context, sample, active_alerts, engine=None, now=None):
    if not isinstance(sample,dict) or set(sample)!={'id','kind','observed_at','readings'} or sample.get('kind')!='simulation':raise ValueError('Amostra inválida.')
    if not isinstance(sample['id'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',sample['id']):raise ValueError('Identificador inválido.')
    try:
        observed=datetime.fromisoformat(sample['observed_at'].replace('Z','+00:00'))
        if observed.tzinfo is None or abs((observed.astimezone(timezone.utc)-(now or datetime.now(timezone.utc))).total_seconds())>300:raise ValueError()
    except (AttributeError,ValueError,TypeError):raise ValueError('Horário inválido.')
    readings=sample['readings']
    if not isinstance(readings,list) or not 1<=len(readings)<=20:raise ValueError('Leituras inválidas.')
    keys=[]
    for item in readings:
        if not isinstance(item,dict) or set(item)!={'key','value','unit'} or not isinstance(item['key'],str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',item['key']) or item['key'] in keys:raise ValueError('Leitura inválida.')
        if isinstance(item['value'],bool) or not isinstance(item['value'],(int,float)) or not math.isfinite(item['value']) or not isinstance(item['unit'],str) or not 1<=len(item['unit'])<=20:raise ValueError('Valor inválido.')
        keys.append(item['key'])
    if not isinstance(active_alerts,list) or len(active_alerts)>30:raise ValueError('Alertas inválidos.')
    previous={}
    for item in active_alerts:
        if not isinstance(item,dict) or not isinstance(item.get('event_key'),str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',item['event_key']) or not isinstance(item.get('triggering_metric_keys'),list) or not all(isinstance(k,str) for k in item['triggering_metric_keys']):raise ValueError('Alerta anterior inválido.')
        previous[item['event_key']]=item
    request_context={'property_context':context,'sample':sample,'active_alerts':active_alerts}
    try:
        result=(engine or AgrionEngine()).run(task='Avalie a amostra simulada e os alertas ativos com base em referências.',context=request_context,mode='dashboard_monitor')
        raw=result.text.strip()
        if raw.startswith('```') and raw.endswith('```'):raw=raw.split('\n',1)[1].rsplit('```',1)[0]
        data=json.loads(raw)
        if not isinstance(data,dict) or set(data)!={'profile','alerts'} or not isinstance(data['profile'],dict) or not isinstance(data['alerts'],list) or len(data['alerts'])>5:raise ValueError()
        profile=data['profile'];variables=profile.get('variables');notes=profile.get('notes')
        if set(profile)!={'variables','notes'} or not isinstance(variables,list) or len(variables)>20 or not all(isinstance(x,str) and x in keys for x in variables) or not isinstance(notes,str) or len(notes)>240:raise ValueError()
        evidence=json.dumps(result.tool_evidence,ensure_ascii=False);accepted=[]
        for item in data['alerts']:
            expected={'event_key','decision','severity','title','summary','triggering_metric_keys','recommended_action','source_urls'}
            if not isinstance(item,dict) or set(item)!=expected:continue
            event=item['event_key'];metrics=item['triggering_metric_keys'];urls=item['source_urls']
            if not isinstance(event,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}',event) or item['decision'] not in {'active','resolved'} or item['severity'] not in {'info','moderate','high','critical'}:continue
            if not isinstance(metrics,list) or not metrics or len(metrics)>20 or not all(isinstance(x,str) and x in keys for x in metrics):continue
            if item['decision']=='resolved' and (event not in previous or not set(previous[event]['triggering_metric_keys']).issubset(keys)):continue
            if any(not isinstance(item[k],str) or not item[k].strip() or len(item[k])>240 for k in ('title','summary','recommended_action')):continue
            if not isinstance(urls,list) or not 1<=len(urls)<=5:continue
            if any(not isinstance(url,str) or len(url)>1000 or urlsplit(url).scheme not in {'http','https'} or not urlsplit(url).hostname or url not in evidence for url in urls):continue
            accepted.append(item)
        return {'status':'ready','sample_id':sample['id'],'observed_at':sample['observed_at'],'kind':'simulation','profile':profile,'alerts':accepted,'generated_at':datetime.now(timezone.utc).isoformat()}
    except (EngineError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        return {'status':'unavailable','kind':'simulation','note':'Não foi possível avaliar a amostra com fontes suficientes.'}
