"""Converte respostas de fontes reais em seções da dashboard."""
import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .climate_tools import ClimateTools
from .engine import AgrionEngine, EngineError

logger=logging.getLogger(__name__)

_URL_RE=re.compile(r'https?://[^\s<>]+',re.I)
_FAILED_QUERY_RE=re.compile(r'(?:consulta|busca|api|ferramenta|serviço|fonte externa|nasa power|meteomatics).{0,100}(?:falh|indispon|não foi possível)|(?:falh|indispon|não foi possível).{0,100}(?:consulta|busca|api|ferramenta|serviço|fonte externa|nasa power|meteomatics)',re.I)


def public_text(value):
    """Remove links e relatos de erro de integração do texto exibido ao agricultor."""
    if not isinstance(value,str):return ''
    value=re.sub(r'\[([^\]]*)\]\(https?://[^)]+\)',r'\1',value)
    value=_URL_RE.sub('',value)
    sentences=re.split(r'(?<=[.!?])\s+|\n+',value)
    return ' '.join(part.strip() for part in sentences if part.strip() and not _FAILED_QUERY_RE.search(part) and not re.fullmatch(r'(?:veja|acesse|fonte|link|saiba mais)\s*[:.]*',part.strip(),re.I)).strip()


def search_entries(evidence):
    return [entry['result']['search_entry_point'] for entry in evidence if isinstance(entry,dict) and entry.get('tool')=='pesquisar_internet' and isinstance(entry.get('result'),dict) and isinstance(entry['result'].get('search_entry_point'),str)]


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
    if crop.get('status')!='confirmed' or not isinstance(crop_value,dict) or not crop_value.get('crop'):
        return {'status':'unavailable','note':'Informe a cultura atual para uma estimativa.'}
    date_text=date_value.get('date') if planted.get('status')=='confirmed' and isinstance(date_value,dict) else None
    if date_text is not None:
        try:
            if not isinstance(date_text,str) or len(date_text)!=10 or datetime.strptime(date_text,'%Y-%m-%d').date()>datetime.now(timezone.utc).date():raise ValueError()
        except ValueError:return {'status':'unavailable','note':'É necessária uma data exata de plantio já ocorrida.'}
    declared=fields.get('current_season_stage') or {}
    if not date_text and (not isinstance(declared,dict) or declared.get('status')!='confirmed' or not isinstance(declared.get('value'),dict) or not declared['value'].get('stage')):
        return {'status':'unavailable','note':'Informe a data de plantio ou a fase atual para uma estimativa.'}
    gdd=None
    try:
        result=(engine or AgrionEngine()).run(task='Investigue fontes e estime a fase da cultura atual e janela de colheita, se houver dados suficientes.',context=context,mode='dashboard_stage')
        text=result.text.strip()
        if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
        gdd=_grounded_gdd(result.tool_evidence,context,date_text) if date_text else None
        data=json.loads(text)
        evidence_items=list(result.tool_evidence)
        if isinstance(data,dict) and not data.get('harvest_window') and date_text:
            try:
                follow=(engine or AgrionEngine()).run(task='A fase já foi estimada. Estime especificamente uma janela aproximada de colheita para a cultura e data de plantio informadas, usando referências de duração do ciclo. Devolva todos os campos do JSON; use intervalo e confiança menor se a referência for geral.',context=context,mode='dashboard_stage')
                follow_text=follow.text.strip()
                if follow_text.startswith('```') and follow_text.endswith('```'):follow_text=follow_text.split('\n',1)[1].rsplit('```',1)[0]
                second=json.loads(follow_text)
                candidate=second.get('harvest_window') if isinstance(second,dict) else None
                second_urls=second.get('source_urls') if isinstance(second,dict) else None
                second_evidence=json.dumps(follow.tool_evidence,ensure_ascii=False)
                if isinstance(candidate,str) and candidate.strip() and isinstance(second_urls,list) and second_urls and all(isinstance(url,str) and url in second_evidence for url in second_urls):
                    data['harvest_window']=candidate
                    data['source_urls']=list(dict.fromkeys((data.get('source_urls') or [])+second_urls))[:5]
                    data['harvest_confidence']=second.get('harvest_confidence')
                    data['harvest_confidence_reason']=second.get('harvest_confidence_reason')
                    evidence_items.extend(follow.tool_evidence)
            except (EngineError,ValueError,TypeError,KeyError,json.JSONDecodeError):
                pass
        required={'phase','reason','harvest_window','source_urls'};optional={'phase_confidence','phase_confidence_reason','harvest_confidence','harvest_confidence_reason'}
        if not isinstance(data,dict) or not required.issubset(data) or set(data)-required-optional:raise ValueError()
        phase,reason,window,urls=data['phase'],public_text(data['reason']),data['harvest_window'],data['source_urls']
        if (phase is not None and (not isinstance(phase,str) or not phase.strip() or len(phase)>240)) or not isinstance(reason,str) or not reason.strip() or len(reason)>240 or (window is not None and (not isinstance(window,str) or not window.strip() or len(window)>240)) or not (phase or window) or not isinstance(urls,list) or not 1<=len(urls)<=5:raise ValueError()
        evidence=json.dumps(evidence_items,ensure_ascii=False)
        for url in urls:
            if not isinstance(url,str) or len(url)>1000 or urlsplit(url).scheme not in {'http','https'} or not urlsplit(url).hostname or url not in evidence:raise ValueError()
        def confidence(prefix):
            amount=data.get(prefix+'_confidence');why=data.get(prefix+'_confidence_reason')
            if type(amount) is not int or not 0<=amount<=100 or not isinstance(why,str) or not 1<=len(why.split())<=5 or len(why)>100:return None
            return {'value':amount,'reason':why.strip()}
        return {'status':'ready','phase':phase.strip() if phase else None,'reason':reason.strip(),'harvest_window':window,'phase_confidence':confidence('phase') if phase else None,'harvest_confidence':confidence('harvest') if window else None,'source_urls':urls,'search_entry_points':search_entries(evidence_items),'gdd':gdd,'value_kind':'estimate','generated_at':datetime.now(timezone.utc).isoformat()}
    except (EngineError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        logger.warning('Dashboard stage unavailable (%s)',type(exc).__name__)
        return {'status':'unavailable','gdd':gdd,'note':'Não foi possível concluir a estimativa de fase e colheita nesta consulta.','reason_code':'engine_unavailable' if isinstance(exc,EngineError) else 'invalid_result'}


def news_section(context,engine=None):
    try:
        result=(engine or AgrionEngine()).run(task='Pesquise notícias recentes pertinentes à cultura e à região da propriedade.',context=context,mode='dashboard_news')
        text=result.text.strip()
        if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
        data=json.loads(text)
        if not isinstance(data,dict) or set(data)!={'items'} or not isinstance(data['items'],list) or len(data['items'])>3:raise ValueError()
        urls=set();search_text=[]
        for entry in result.tool_evidence:
            if isinstance(entry,dict) and entry.get('tool')=='pesquisar_internet':
                if isinstance((entry.get('result') or {}).get('text'),str):search_text.append(entry['result']['text'])
                for source in (entry.get('result') or {}).get('sources',[]):
                    if isinstance(source,dict) and isinstance(source.get('url'),str):urls.add(source['url'])
        items=[]
        for item in data['items']:
            if not isinstance(item,dict) or set(item)!={'title','summary','date','url'}:continue
            title,summary,day,url=(item[k] for k in ('title','summary','date','url'))
            title,summary=public_text(title),public_text(summary)
            if not isinstance(title,str) or not 1<=len(title)<=180 or not isinstance(summary,str) or not 1<=len(summary)<=300 or not isinstance(url,str) or url not in urls:continue
            if day is not None:
                if not isinstance(day,str) or len(day)!=10:continue
                try:parsed_day=datetime.strptime(day,'%Y-%m-%d')
                except ValueError:continue
                if not any(day in text or parsed_day.strftime('%d/%m/%Y') in text for text in search_text):day=None
            items.append({'title':title,'summary':summary,'date':day,'url':url})
        entries=search_entries(result.tool_evidence)
        if not items:raise ValueError()
        return {'status':'ready','items':items,'search_entry_points':entries,'generated_at':datetime.now(timezone.utc).isoformat()}
    except (EngineError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        logger.warning('Dashboard news unavailable (%s)',type(exc).__name__)
        return {'status':'unavailable','note':'Não foi possível obter notícias verificáveis nesta consulta.','reason_code':'engine_unavailable' if isinstance(exc,EngineError) else 'invalid_result'}


def daily_section(context, engine=None):
    """Aceita análise parcial baseada no contexto ou em fontes recuperadas."""
    try:
        result=(engine or AgrionEngine()).run(task='Analise a propriedade para o resumo diário e recomendações práticas com fontes.',context=context,mode='dashboard_daily')
        text=result.text.strip()
        if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
        data=json.loads(text)
        if not isinstance(data,dict) or not {'summary','observations','recommendations'}<=set(data) or set(data)-{'headline','summary','observations','recommendations'}:raise ValueError()
        if not isinstance(data['observations'],list) or len(data['observations'])>4 or not isinstance(data['recommendations'],list) or len(data['recommendations'])>3:raise ValueError()
        evidence=json.dumps(result.tool_evidence,ensure_ascii=False)
        fields=(context.get('agricultural_profile') or {}).get('fields') or {}
        has_context=any(isinstance(v,dict) and v.get('status')=='confirmed' and isinstance(v.get('value'),dict) and bool(v['value']) for v in fields.values()) if isinstance(fields,dict) else False
        def validate(item, allow_context=False):
            if not isinstance(item,dict) or not {'text','source_urls'}<=set(item) or set(item)-{'headline','text','source_urls'}:return None
            value=public_text(item['text']);urls=item['source_urls']
            if not isinstance(value,str) or not value.strip() or len(value)>300 or not isinstance(urls,list) or len(urls)>5 or not urls and not (allow_context and has_context):return None
            for url in urls:
                if not isinstance(url,str) or len(url)>1000 or urlsplit(url).scheme not in {'http','https'} or not urlsplit(url).hostname or url not in evidence:return None
            headline=public_text(item.get('headline'))
            if not headline:headline=value.split('.')[0].strip()[:85]
            return {'headline':headline[:85],'text':value.strip(),'source_urls':urls,'source_kind':'external' if urls else 'farmer_context'}
        summary=validate(data['summary'],True) if data['summary'] is not None else None
        observations=[value for item in data['observations'] if (value:=validate(item,True))]
        recommendations=[value for item in data['recommendations'] if (value:=validate(item,True))]
        if not summary and not observations and not recommendations:raise ValueError()
        headline=public_text(data.get('headline'))
        if not headline:headline=(summary or (observations+recommendations)[0])['headline']
        return {'status':'ready','generated_at':datetime.now(timezone.utc).isoformat(),'headline':headline[:85],'summary':summary,'observations':observations,'recommendations':recommendations,'search_entry_points':search_entries(result.tool_evidence)}
    except (EngineError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        logger.warning('Dashboard daily unavailable (%s)',type(exc).__name__)
        return {'status':'unavailable','note':'Não foi possível concluir a análise diária nesta consulta.','reason_code':'engine_unavailable' if isinstance(exc,EngineError) else 'invalid_result'}


def market_section(context, engine=None):
    """Parecer da IA; preços são extraídos da resposta real da ferramenta."""
    try:
        result=(engine or AgrionEngine()).run(task='Analise a produção e o mercado da cultura e procure o último preço histórico disponível.',context=context,mode='dashboard_market')
        text=result.text.strip()
        if text.startswith('```') and text.endswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
        data=json.loads(text)
        optional={'estimated_price','currency','unit','confidence','confidence_reason','source_urls'}
        if not isinstance(data,dict) or not {'summary','item_code'}<=set(data) or set(data)-{'summary','item_code'}-optional:raise ValueError()
        summary=public_text(data['summary']);code=data['item_code']
        if not isinstance(summary,str) or not summary.strip() or len(summary)>500 or (code is not None and (not isinstance(code,str) or not code.isascii() or not code.isdigit())):raise ValueError()
        price=None
        candidates=set()
        for entry in result.tool_evidence:
            if not isinstance(entry,dict) or entry.get('tool')!='faostat_candidatos':continue
            output=entry.get('result') or {};response=output.get('data') or {}
            if isinstance(response,dict):
                for candidate in (response.get('candidates') or [])+(response.get('additional_partial_candidates') or []):
                    if isinstance(candidate,dict) and isinstance(candidate.get('item_code'),str):candidates.add(candidate['item_code'])
        for entry in result.tool_evidence:
            if not isinstance(entry,dict) or entry.get('tool')!='faostat_ultimo_preco':continue
            args=entry.get('arguments') or {};output=entry.get('result') or {};response=output.get('data') or {}
            if code not in candidates or args.get('item_code')!=code or not isinstance(response,dict) or response.get('selection_status')!='found':continue
            items=response.get('items') or []
            if len(items)!=1 or not isinstance(items[0],dict):continue
            item=items[0];number=item.get('value')
            if item.get('item_code')!=code or item.get('value_kind') not in {'usd_per_tonne','local_currency_per_tonne','standard_local_currency_per_tonne'} or isinstance(number,bool) or not isinstance(number,(int,float)) or not math.isfinite(number):continue
            price={'value':number,'unit':item.get('unit'),'value_kind':item.get('value_kind'),'year':item.get('year'),'country':item.get('area'),'product':item.get('item'),'flag':item.get('flag'),'frequency':response.get('frequency'),'source_url':'https://www.fao.org/faostat/en/#data/PP'}
        estimate=None
        amount=data.get('estimated_price');score=data.get('confidence');why=data.get('confidence_reason')
        if (price is not None and isinstance(amount,(int,float)) and not isinstance(amount,bool) and math.isfinite(amount) and amount>0
                and type(score) is int and 0<=score<=100 and isinstance(why,str) and 1<=len(why.split())<=5):
            evidence=json.dumps(result.tool_evidence,ensure_ascii=False)
            urls=data.get('source_urls') or []
            if isinstance(urls,list) and len(urls)<=5 and all(isinstance(url,str) and urlsplit(url).scheme in {'http','https'} and urlsplit(url).hostname and url in evidence for url in urls):
                unit=price.get('unit')
                estimate={'value':amount,'unit':unit if isinstance(unit,str) and unit.endswith('/t') else f'{unit}/t' if unit else None,'confidence':{'value':score,'reason':why.strip()},'source_urls':urls,'basis_year':price['year'],'value_kind':'estimate'}
        return {'status':'ready','summary':summary.strip(),'price':price,'estimate':estimate,'search_entry_points':search_entries(result.tool_evidence),'generated_at':datetime.now(timezone.utc).isoformat()}
    except (EngineError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        logger.warning('Dashboard market unavailable (%s)',type(exc).__name__)
        return {'status':'unavailable','note':'Não foi possível preparar a análise de produção e mercado.','reason_code':'engine_unavailable' if isinstance(exc,EngineError) else 'invalid_result'}
