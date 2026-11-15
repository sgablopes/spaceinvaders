"""Converte respostas de fontes reais em seções da dashboard."""
import json
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .climate_tools import ClimateTools
from .engine import AgrionEngine, EngineError


def location_from(context):
    point=context.get('property',{}).get('center_point') or {}
    coordinates=point.get('coordinates') if isinstance(point,dict) else None
    if not isinstance(coordinates,list) or len(coordinates)!=2:return None
    lon,lat=coordinates
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (lat,lon)) or abs(lat)>90 or abs(lon)>180:return None
    return {'latitude':lat,'longitude':lon}


def forecast_section(context, tools=None, now=None):
    location=location_from(context)
    if location is None:return {'status':'unavailable','metrics':[],'note':'Localização indisponível.'}
    now=now or datetime.now(timezone.utc)
    start=now.replace(minute=0,second=0,microsecond=0)+timedelta(hours=2)
    end=start+timedelta(hours=23)
    try:
        result=(tools or ClimateTools()).forecast(location,start.isoformat(),end.isoformat(),1,['temperature','precipitation','relative_humidity','wind_speed'],provider='auto',require_complete=False)
    except (ValueError,TypeError):return {'status':'error','metrics':[],'note':'Não foi possível solicitar a previsão.'}
    if not result.get('ok'):return {'status':'unavailable','metrics':[],'note':'Previsão indisponível no momento.'}
    data=result.get('data') or {};payload=data.get('result') or {};rows=payload.get('series') or [];provenance=data.get('provenance') or []
    if not isinstance(rows,list) or not rows or not isinstance(provenance,list) or not provenance:return {'status':'unavailable','metrics':[],'note':'Previsão sem fonte ou horários disponíveis.'}
    source=provenance[0];name=source.get('provider') if isinstance(source,dict) else None
    if name not in {'Meteomatics','Open-Meteo'}:return {'status':'unavailable','metrics':[],'note':'Fonte de previsão não reconhecida.'}
    metrics=[]
    for parameter,key,label in [('temperature','temperature_c','Temperatura'),('precipitation','precipitation_mm','Chuva prevista'),('relative_humidity','relative_humidity_pct','Umidade do ar'),('wind_speed','wind_speed_10m_m_s','Vento')]:
        definition=(payload.get('parameters') or {}).get(parameter) or {}
        row=next((x for x in rows if isinstance(x,dict) and isinstance(x.get(key),(int,float)) and not isinstance(x[key],bool) and math.isfinite(x[key]) and x.get('valid_time')),None)
        if not row or not definition.get('unit'):continue
        metrics.append({'key':parameter,'label':label,'value':row[key],'unit':definition['unit'],'available':True,'value_kind':'forecast','source':name,'forecast_for':row['valid_time'],'interval_start':row.get('interval_start'),'generated_at':data.get('generated_at')})
    note='Previsão horária, não medição no terreno.'
    if name=='Open-Meteo':note+=' Open-Meteo: API gratuita para uso não comercial; atribuição obrigatória.'
    return {'status':'ready' if metrics else 'unavailable','metrics':metrics,'source':name,'source_url':source.get('documentation_url') or source.get('source_url'),'source_accessed_at':source.get('accessed_at'),'generated_at':data.get('generated_at'),'note':note}


def rainfall_section(context, tools=None, today=None):
    location=location_from(context)
    if location is None:return {'status':'unavailable','metrics':[],'note':'Localização indisponível.'}
    reference=(today or datetime.now(timezone.utc).date())-timedelta(days=2)
    try:result=(tools or ClimateTools()).rainfall(location,reference.isoformat())
    except (ValueError,TypeError):return {'status':'error','metrics':[],'note':'Não foi possível solicitar o histórico.'}
    if not result.get('ok'):return {'status':'unavailable','metrics':[],'note':'Chuva histórica indisponível no momento.'}
    data=result.get('data') or {};indicator=((data.get('result') or {}).get('indicators') or {}).get('I02') or {}
    provenance=indicator.get('provenance') or [];source=next((x for x in provenance if isinstance(x,dict) and x.get('provider')=='NASA POWER'),None)
    if not source:return {'status':'unavailable','metrics':[],'note':'Chuva histórica sem fonte identificada.'}
    metrics=[]
    for window in indicator.get('windows') or []:
        if not isinstance(window,dict):continue
        days=window.get('window_days');total=window.get('total_mm')
        if days not in (7,15,30,90) or isinstance(total,bool) or not isinstance(total,(int,float)) or not math.isfinite(total):continue
        metrics.append({'key':f'rain_{days}d','label':f'Chuva acumulada em {days} dias','value':total,'unit':'mm','available':True,'value_kind':'derived','source':'NASA POWER','period_start':window.get('start_date'),'period_end':window.get('end_date'),'generated_at':data.get('generated_at')})
    return {'status':'ready' if metrics else 'unavailable','metrics':metrics,'source':'NASA POWER','source_url':source.get('source_url'),'source_accessed_at':source.get('accessed_at'),'generated_at':data.get('generated_at'),'note':'Estimativa regional histórica; não é medição no terreno.'}


def _grounded_gdd(evidence, context, planting_date):
    location=location_from(context)
    if not location:return None
    for entry in evidence:
        if not isinstance(entry,dict) or entry.get('tool')!='graus_dia_acumulados':continue
        arguments=entry.get('arguments') or {};output=entry.get('result') or {}
        if not isinstance(arguments,dict) or not isinstance(output,dict) or not output.get('ok'):continue
        if arguments.get('location')!=location or arguments.get('start_date')!=planting_date:continue
        data=output.get('data') or {};indicator=((data.get('result') or {}).get('indicators') or {}).get('I01') or {}
        if not isinstance(indicator,dict):continue
        result=indicator.get('value');base=indicator.get('base_temperature_c');reference=indicator.get('base_temperature_reference')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (result,base)):continue
        if not isinstance(reference,str) or not reference.strip():continue
        other=json.dumps([x.get('result') for x in evidence if isinstance(x,dict) and x is not entry],ensure_ascii=False)
        if reference not in other:continue
        source=next((x for x in indicator.get('provenance') or [] if isinstance(x,dict) and x.get('provider')=='NASA POWER'),None)
        if not source:continue
        return {'value':result,'unit':indicator.get('unit'),'base_temperature_c':base,'base_temperature_reference':reference,'source':'NASA POWER','source_url':source.get('source_url'),'period':indicator.get('period')}
    return None


def stage_section(context, engine=None):
    fields=(context.get('agricultural_profile') or {}).get('fields') or {}
    crop=fields.get('current_crop') or {};planted=fields.get('planting_date') or {}
    if not isinstance(crop,dict) or not isinstance(planted,dict):return {'status':'unavailable','note':'Dados da cultura indisponíveis.'}
    crop_value=crop.get('value') or {};date_value=planted.get('value') or {}
    if crop.get('status')!='confirmed' or not isinstance(crop_value,dict) or not crop_value.get('crop') or planted.get('status')!='confirmed' or not isinstance(date_value,dict):
        return {'status':'unavailable','note':'Informe a cultura atual e a data exata de plantio para uma estimativa.'}
    date_text=date_value.get('date')
    try:
        if not isinstance(date_text,str) or len(date_text)!=10 or datetime.strptime(date_text,'%Y-%m-%d').date()>datetime.now(timezone.utc).date():raise ValueError()
    except ValueError:return {'status':'unavailable','note':'É necessária uma data exata de plantio já ocorrida.'}
    gdd=None
    try:
        result=(engine or AgrionEngine()).run(task='Investigue fontes e estime a fase da cultura atual e janela de colheita, se houver dados suficientes.',context=context,mode='dashboard_stage')
        text=result.text.strip()
        if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
        gdd=_grounded_gdd(result.tool_evidence,context,date_text)
        data=json.loads(text)
        if not isinstance(data,dict) or set(data)!={'phase','reason','harvest_window','source_urls'}:raise ValueError()
        phase,reason,window,urls=data['phase'],data['reason'],data['harvest_window'],data['source_urls']
        if not isinstance(phase,str) or not phase.strip() or len(phase)>240 or not isinstance(reason,str) or not reason.strip() or len(reason)>240 or (window is not None and (not isinstance(window,str) or len(window)>240)) or not isinstance(urls,list) or not 1<=len(urls)<=5:raise ValueError()
        evidence=json.dumps(result.tool_evidence,ensure_ascii=False)
        for url in urls:
            if not isinstance(url,str) or len(url)>1000 or urlsplit(url).scheme not in {'http','https'} or not urlsplit(url).hostname or url not in evidence:raise ValueError()
        return {'status':'ready','phase':phase.strip(),'reason':reason.strip(),'harvest_window':window,'source_urls':urls,'gdd':gdd,'value_kind':'estimate','generated_at':datetime.now(timezone.utc).isoformat()}
    except (EngineError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        return {'status':'unavailable','gdd':gdd,'note':'Ainda não há evidência suficiente para estimar a fase com segurança.'}


def daily_section(context, engine=None):
    """Retorna apenas trechos que citam URLs recuperadas por ferramentas."""
    try:
        result=(engine or AgrionEngine()).run(task='Analise a propriedade para o resumo diário e recomendações práticas com fontes.',context=context,mode='dashboard_daily')
        text=result.text.strip()
        if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
        data=json.loads(text)
        if not isinstance(data,dict) or set(data)!={'summary','observations','recommendations'}:raise ValueError()
        if not isinstance(data['observations'],list) or len(data['observations'])>4 or not isinstance(data['recommendations'],list) or len(data['recommendations'])>3:raise ValueError()
        evidence=json.dumps(result.tool_evidence,ensure_ascii=False)
        def validate(item):
            if not isinstance(item,dict) or set(item)!={'text','source_urls'}:return None
            value=item['text'];urls=item['source_urls']
            if not isinstance(value,str) or not value.strip() or len(value)>300 or not isinstance(urls,list) or not 1<=len(urls)<=5:return None
            for url in urls:
                if not isinstance(url,str) or len(url)>1000 or urlsplit(url).scheme not in {'http','https'} or not urlsplit(url).hostname or url not in evidence:return None
            return {'text':value.strip(),'source_urls':urls}
        summary=validate(data['summary']) if data['summary'] is not None else None
        observations=[value for item in data['observations'] if (value:=validate(item))]
        recommendations=[value for item in data['recommendations'] if (value:=validate(item))]
        if not summary and not observations and not recommendations:raise ValueError()
        return {'status':'ready','generated_at':datetime.now(timezone.utc).isoformat(),'summary':summary,'observations':observations,'recommendations':recommendations}
    except (EngineError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        return {'status':'unavailable','note':'Não há fontes suficientes para a análise diária neste momento.'}
