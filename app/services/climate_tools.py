"""Adaptadores explícitos NASA POWER e indicadores, ainda fora do catálogo da IA."""
import json
import math
import os
from datetime import date, datetime, timezone, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


PARAMETERS = {'T2M', 'T2M_MAX', 'T2M_MIN', 'PRECTOTCORR', 'RH2M', 'ALLSKY_SFC_SW_DWN'}
FORECAST_PARAMETERS = {'temperature','temperature_mean','temperature_min','temperature_max','precipitation','relative_humidity','wind_speed','solar_radiation'}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _day(value):
    if not isinstance(value, str) or len(value)!=10:
        raise ValueError('Data deve usar AAAA-MM-DD.')
    parsed=date.fromisoformat(value)
    if parsed.isoformat()!=value:raise ValueError('Data inválida.')
    return parsed


def _location(location):
    if not isinstance(location,dict) or set(location)!={'latitude','longitude'}:raise ValueError('Localização inválida.')
    for key,limit in [('latitude',90),('longitude',180)]:
        value=location[key]
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or abs(value)>limit:raise ValueError('Coordenada inválida.')
    return dict(location)


def _period(start,end):
    first,last=_day(start),_day(end)
    if first<date(1981,1,1) or last<first or (last-first).days>=366 or last>datetime.now(timezone.utc).date():raise ValueError('Período histórico inválido.')


class ClimateTools:
    """Consulta fontes apenas por POSTs fixos, com resposta e procedência intactas."""
    def __init__(self, base_url=None, post=None, timeout=120):
        self.base_url=(base_url or os.getenv('AGRION_ANALYSIS_URL','http://agrion-data:8000')).rstrip('/')
        url=urlsplit(self.base_url)
        if url.scheme not in {'http','https'} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {'','/'}:raise ValueError('URL de análises inválida.')
        if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not 1<=timeout<=180:raise ValueError('Timeout inválido.')
        self.timeout=timeout
        self._post=post or self._http_post

    def nasa_daily(self, location, start_date, end_date, parameters, time_standard='UTC', require_complete=False):
        loc=_location(location);_period(start_date,end_date)
        if not isinstance(parameters,list) or not parameters or len(parameters)>6 or any(not isinstance(p,str) or p not in PARAMETERS for p in parameters) or len(set(parameters))!=len(parameters):raise ValueError('Parâmetros NASA inválidos.')
        if time_standard not in {'UTC','LST'} or type(require_complete) is not bool:raise ValueError('Opções NASA inválidas.')
        return self._call('/v1/data/nasa-power/daily',{'location':loc,'start_date':start_date,'end_date':end_date,'parameters':parameters,'time_standard':time_standard,'require_complete':require_complete})

    def rainfall(self, location, reference_date, day_basis='UTC'):
        loc=_location(location);day=_day(reference_date)
        if day<date(1981,3,31) or day>datetime.now(timezone.utc).date() or day_basis not in {'UTC','LST'}:raise ValueError('Data ou base temporal inválida.')
        return self._call('/v1/analysis/climate',{'include':['I02'],'inputs':{'rainfall':{'location':loc,'reference_date':reference_date,'day_basis':day_basis}}})

    def gdd(self, location, crop_id, start_date, end_date, base_temperature_c, base_temperature_reference=None):
        loc=_location(location);_period(start_date,end_date)
        if not isinstance(crop_id,str) or not crop_id.strip() or len(crop_id)>200:raise ValueError('Cultura inválida.')
        if isinstance(base_temperature_c,bool) or not isinstance(base_temperature_c,(int,float)) or not math.isfinite(base_temperature_c) or not -100<=base_temperature_c<=100:raise ValueError('Temperatura-base explícita é obrigatória.')
        if base_temperature_reference is not None and (not isinstance(base_temperature_reference,str) or not base_temperature_reference.strip() or len(base_temperature_reference)>500):raise ValueError('Referência de temperatura-base inválida.')
        payload={'location':loc,'crop_id':crop_id.strip(),'start_date':start_date,'end_date':end_date,'base_temperature_c':base_temperature_c,'timezone':'UTC','data_kind':'historical'}
        if base_temperature_reference is not None:payload['base_temperature_reference']=base_temperature_reference.strip()
        return self._call('/v1/analysis/climate',{'include':['I01'],'inputs':{'gdd':payload}})

    def forecast(self, location, start_time, end_time, step_hours, parameters, provider='meteomatics', require_complete=True):
        loc=_location(location)
        if type(step_hours) is not int or step_hours not in {1,3,6,24}:raise ValueError('Intervalo inválido.')
        if not isinstance(parameters,list) or not parameters or any(not isinstance(p,str) or p not in FORECAST_PARAMETERS for p in parameters) or len(parameters)!=len(set(parameters)):raise ValueError('Parâmetros de previsão inválidos.')
        if provider not in {'meteomatics','open_meteo','auto'} or type(require_complete) is not bool:raise ValueError('Provedor inválido.')
        def timestamp(value):
            if not isinstance(value,str) or 'T' not in value:raise ValueError('Horário deve ter fuso explícito.')
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            if parsed.tzinfo is None or parsed.utcoffset() is None:raise ValueError('Horário deve ter fuso explícito.')
            return parsed.astimezone(timezone.utc)
        start,end=timestamp(start_time),timestamp(end_time)
        if start.minute or start.second or start.microsecond or end.minute or end.second or end.microsecond or end<start or end-start>timedelta(days=16) or (end-start).total_seconds()%(step_hours*3600):raise ValueError('Intervalo de previsão inválido.')
        now=datetime.now(timezone.utc)
        if start<=now or (set(parameters)&{'precipitation','temperature_mean','temperature_min','temperature_max'} and start-timedelta(hours=step_hours)<=now):raise ValueError('A previsão e seus intervalos devem estar no futuro.')
        return self._call('/v1/data/weather/forecast',{'location':loc,'start_time':start_time,'end_time':end_time,'step_hours':step_hours,'parameters':parameters,'provider':provider,'source':'mix','require_complete':require_complete})

    def indicator(self, indicator_id, inputs):
        """Executa apenas indicadores novos; entradas explícitas são validadas novamente pelo serviço."""
        catalog={'I03':('climate','dry_spell'),'I05':('climate','thermal_stress'),'I07':('water','crop_evapotranspiration'),'I08':('water','water_balance'),'I14':('economics','crop_margin')}
        if indicator_id not in catalog or not isinstance(inputs,dict):raise ValueError('Indicador ou entradas inválidas.')
        if len(json.dumps(inputs,allow_nan=False,ensure_ascii=False))>100000:raise ValueError('Entradas muito grandes.')
        group,field=catalog[indicator_id]
        required={'I03':{'start_date','end_date','rain_threshold_mm'},'I05':{'start_date','end_date','crop_id','growth_stage','threshold_catalog_version'},'I07':{'start_date','end_date','crop_id','growth_stage','kc_catalog_version'},'I08':{'start_date','end_date','crop_id','growth_stage','kc_catalog_version','assumptions_reference'},'I14':{'start_date','end_date','crop_id','area_ha','expected_yield_t_per_ha','price_per_t','cost_per_ha','currency','assumptions_reference'}}[indicator_id]
        if not required.issubset(inputs):raise ValueError('Faltam entradas explícitas do indicador.')
        start,end=_day(inputs['start_date']),_day(inputs['end_date'])
        if end<start:raise ValueError('Período invertido.')
        if 'location' in inputs:_location(inputs['location'])
        if inputs.get('timezone','UTC')!='UTC':raise ValueError('Indicador exige UTC.')
        if indicator_id=='I03' and 'location' not in inputs and 'daily_precipitation' not in inputs:raise ValueError('Informe localização ou série de chuva.')
        if indicator_id=='I05' and not (inputs.get('ecocrop_crop_id') or (inputs.get('threshold_reference') and (inputs.get('lower_threshold_c') is not None or inputs.get('upper_threshold_c') is not None))):raise ValueError('Informe limites com referência ou ID ECOCROP.')
        if indicator_id in {'I07','I08'}:
            if not inputs.get('eto_series') or not inputs.get('eto_reference'):raise ValueError('Informe série e referência de ETo.')
            if not inputs.get('kc_selection') and (inputs.get('kc') is None or not inputs.get('kc_reference')):raise ValueError('Informe Kc com referência ou seleção FAO.')
        if indicator_id=='I08' and not inputs.get('daily_fluxes'):raise ValueError('Informe os fluxos diários.')
        if indicator_id=='I14':
            for key in ('area_ha','expected_yield_t_per_ha','price_per_t','cost_per_ha'):
                number=inputs[key]
                if isinstance(number,bool) or not isinstance(number,(int,float)) or not math.isfinite(number) or number<0 or key=='area_ha' and number==0:raise ValueError('Valor econômico inválido.')
        return self._call('/v1/analysis/'+group,{'include':[indicator_id],'inputs':{field:inputs}})

    def _call(self,path,payload):
        try:
            result=self._post(path,payload)
            if not isinstance(result,dict):return {'ok':False,'error':{'code':'INVALID_RESPONSE','retryable':False}}
            return {'ok':True,'data':result}
        except HTTPError as error:
            try:
                body=json.loads(error.read(65537))
                detail=body.get('error',{}) if isinstance(body,dict) else {}
                if not isinstance(detail,dict):detail={}
                code=detail.get('code')
                if not isinstance(code,str) or not code.replace('_','').isalnum() or len(code)>80:code='ANALYSIS_HTTP_ERROR'
                return {'ok':False,'error':{'code':code,'http_status':error.code,'retryable':detail.get('retryable') is True}}
            except (ValueError,OSError):return {'ok':False,'error':{'code':'ANALYSIS_HTTP_ERROR','http_status':error.code,'retryable':False}}
        except (URLError,TimeoutError,OSError):return {'ok':False,'error':{'code':'ANALYSIS_UNAVAILABLE','retryable':True}}
        except (ValueError,UnicodeError):return {'ok':False,'error':{'code':'INVALID_RESPONSE','retryable':False}}

    def _http_post(self,path,payload):
        request=Request(self.base_url+path,data=json.dumps(payload,allow_nan=False).encode('utf-8'),headers={'Content-Type':'application/json','Accept':'application/json'},method='POST')
        with build_opener(_NoRedirect()).open(request,timeout=self.timeout) as response:
            data=response.read(2000001)
            if len(data)>2000000:raise ValueError('Resposta excede o limite.')
            return json.loads(data)
