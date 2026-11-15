"""Ferramentas de leitura aprovadas para a API interna de análises."""
import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen


_QUERY = {'q': {'type': 'string', 'description': 'Texto a buscar.'}, 'filtros_json': {'type': 'string', 'description': 'Objeto JSON de filtros exatos usando nomes de colunas da fonte.'}, 'limit': {'type': 'integer', 'description': 'Quantidade entre 1 e 30.'}, 'offset': {'type': 'integer', 'description': 'Posição inicial para paginação.'}}
_SOURCES = {
    'buscar_culturas': ('/api/v1/ecocrop/nomes_sinonimos', 'Busca nomes e sinônimos de culturas no ECOCROP.'),
    'requisitos_cultura': ('/api/v1/ecocrop/requisitos', 'Consulta requisitos ambientais ECOCROP por texto ou identificador.'),
    'parametros_fao56': ('/api/v1/fao56/indice_atomico', 'Consulta parâmetros FAO-56; confira auditorias e limitações antes de interpretar.'),
    'auditoria_fao56': ('/api/v1/fao56/alertas_revisao', 'Consulta alertas e limitações de dados FAO-56.'),
    'evidencias_agricolas': ('/api/v1/conhecimento/evidencias', 'Busca evidências e seu status de validação agronômica.'),
    'fontes_agricolas': ('/api/v1/conhecimento/fontes', 'Busca informações sobre fontes da biblioteca de conhecimento.'),
    'rotacoes_agricolas': ('/api/v1/conhecimento/rotacoes', 'Consulta rotações documentadas; verifique evidências e fontes associadas.'),
    'dicionario_aquacrop': ('/api/v1/aquacrop/dicionario', 'Consulta campos de entrada AquaCrop; não executa simulação.'),
}


class AnalysisTools:
    def __init__(self, base_url=None, request=None, climate=None):
        self.base_url=(base_url or os.getenv('AGRION_ANALYSIS_URL', 'http://agrion-data:8000')).rstrip('/')
        parsed=urlsplit(self.base_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}:
            raise ValueError('URL da API de análises inválida.')
        self._request=request or self._http_get
        self._climate=climate

    def declarations(self):
        result=[{'name': name, 'description': description, 'parameters': {'type': 'OBJECT', 'properties': _QUERY}} for name, (_, description) in _SOURCES.items()]
        result.extend([
            {'name':'faostat_candidatos','description':'Busca candidatos de culturas FAOSTAT pelo nome em português ou inglês. Compare as evidências e selecione o candidato mais adequado; correspondências não são revisadas.','parameters':{'type':'OBJECT','properties':{'q':{'type':'STRING'},'country_iso2':{'type':'STRING'},'area_code':{'type':'STRING'}},'required':['q']}},
            {'name':'faostat_ultimo_preco','description':'Último preço histórico nacional disponível no snapshot para país e produto escolhidos. Não é cotação atual.','parameters':{'type':'OBJECT','properties':{'item_code':{'type':'STRING'},'country_iso2':{'type':'STRING'},'area_code':{'type':'STRING'},'element_code':{'type':'STRING'},'frequency':{'type':'STRING','enum':['annual','monthly']}},'required':['item_code']}},
            {'name':'camadas_gaez','description':'Lista camadas GAEZ v5; use paginação e escolha a camada exata antes de consultar um ponto.','parameters':{'type':'OBJECT','properties':{'variable':{'type':'string'},'filename_prefix':{'type':'string'},'page_token':{'type':'string'}}}},
            {'name':'ponto_gaez','description':'Consulta uma camada GAEZ por coordenada WGS84. Não infira unidades ou classes ausentes.','parameters':{'type':'OBJECT','properties':{'layer':{'type':'string'},'latitude':{'type':'number'},'longitude':{'type':'number'}},'required':['layer','latitude','longitude']}}
        ])
        location={'type':'OBJECT','properties':{'latitude':{'type':'NUMBER'},'longitude':{'type':'NUMBER'}},'required':['latitude','longitude']}
        day={'type':'STRING','description':'Data civil exata AAAA-MM-DD; não invente datas ausentes.'}
        result.extend([
            {'name':'nasa_clima_diario','description':'Dados históricos diários NASA POWER, estimativas regionais, não previsão ou medição de campo. Até 366 dias.','parameters':{'type':'OBJECT','properties':{'location':location,'start_date':day,'end_date':day,'parameters':{'type':'ARRAY','items':{'type':'STRING','enum':['T2M','T2M_MAX','T2M_MIN','PRECTOTCORR','RH2M','ALLSKY_SFC_SW_DWN']}},'time_standard':{'type':'STRING','enum':['UTC','LST']},'require_complete':{'type':'BOOLEAN'}},'required':['location','start_date','end_date','parameters']}},
            {'name':'chuva_acumulada','description':'Calcula chuva histórica em janelas retrospectivas 7, 15, 30 e 90 dias, com NASA POWER.','parameters':{'type':'OBJECT','properties':{'location':location,'reference_date':day,'day_basis':{'type':'STRING','enum':['UTC','LST']}},'required':['location','reference_date']}},
            {'name':'graus_dia_acumulados','description':'Calcula graus-dia históricos NASA POWER; exige cultura, período exato e temperatura-base explícita. Não calcula estágio fenológico observado.','parameters':{'type':'OBJECT','properties':{'location':location,'crop_id':{'type':'STRING'},'start_date':day,'end_date':day,'base_temperature_c':{'type':'NUMBER'},'base_temperature_reference':{'type':'STRING','description':'Origem explícita da temperatura-base, quando disponível.'}},'required':['location','crop_id','start_date','end_date','base_temperature_c']}}
        ])
        result.append({'name':'previsao_tempo','description':'Previsão para coordenada WGS84: Meteomatics ou alternativa Open-Meteo. Informe provedor, licença e limitações; não é observação local.', 'parameters':{'type':'OBJECT','properties':{'location':location,'start_time':{'type':'STRING'},'end_time':{'type':'STRING'},'step_hours':{'type':'INTEGER','description':'Intervalo em horas: 1, 3, 6 ou 24.'},'parameters':{'type':'ARRAY','items':{'type':'STRING','enum':['temperature','temperature_mean','temperature_min','temperature_max','precipitation','relative_humidity','wind_speed','solar_radiation']}},'require_complete':{'type':'BOOLEAN'}},'required':['location','start_time','end_time','step_hours','parameters']}})
        result.extend([
            {'name':'faostat_paises','description':'Busca países e códigos FAOSTAT; não escolha automaticamente uma correspondência ambígua.','parameters':{'type':'OBJECT','properties':{'q':{'type':'STRING'}}}},
            {'name':'faostat_produtos','description':'Busca produtos e códigos FAOSTAT; nomes da fonte são em inglês, confirme a correspondência.','parameters':{'type':'OBJECT','properties':{'q':{'type':'STRING'},'country_iso2':{'type':'STRING'},'area_code':{'type':'STRING'}}}},
            {'name':'faostat_precos','description':'Preços históricos nacionais ao produtor ou índices, não cotações atuais; preserve ano, unidade, país, flag e fonte.','parameters':{'type':'OBJECT','properties':{'item_code':{'type':'STRING'},'country_iso2':{'type':'STRING'},'area_code':{'type':'STRING'},'start_year':{'type':'INTEGER'},'end_year':{'type':'INTEGER'},'frequency':{'type':'STRING','enum':['annual','monthly','all']},'month':{'type':'INTEGER'},'element_code':{'type':'STRING'},'limit':{'type':'INTEGER'},'offset':{'type':'INTEGER'}},'required':['item_code']}},
            {'name':'simular_aquacrop','description':'Simulação AquaCrop-OSPy de milho de sequeiro, não resultado observado nem previsão garantida. Use somente cenário, solo, água, CO2, manejo, clima e referências explicitamente fornecidos; não invente hipóteses. Pode demorar.','parameters':{'type':'OBJECT','properties':{'inputs_json':{'type':'STRING','description':'JSON completo do contrato /v1/simulations/aquacrop; requer scenario_id, start_date, end_date, crop Maize, location, weather, soil, initial_water, co2, management e assumptions_reference.'}},'required':['inputs_json']}}
        ])
        indicators={
            'sequencia_seca':('I03','Máxima sequência de dias secos. Exige start_date, end_date, location ou daily_precipitation e rain_threshold_mm explícito.'),
            'exposicao_termica':('I05','Conta dias acima/abaixo de limites; não estima danos. Exige start_date, end_date, crop_id, growth_stage, threshold_catalog_version, localização ou série e ecocrop_crop_id ou limites com threshold_reference.'),
            'evapotranspiracao_cultura':('I07','ETc padrão, não evapotranspiração real. Exige datas, crop_id, growth_stage, kc_catalog_version, eto_series com eto_reference e kc com kc_reference ou kc_selection.'),
            'variacao_hidrica':('I08','Variação hídrica contábil, não irrigação recomendada nem estoque do solo. Exige entradas I07, assumptions_reference e daily_fluxes completos.'),
            'margem_cenario':('I14','Margem do cenário declarado, não lucro líquido. Exige datas, crop_id, area_ha, expected_yield_t_per_ha, cost_per_ha, currency e assumptions_reference; price_per_t ou faostat_price explícito USD/t e custos em USD.')}
        for name,(_,description) in indicators.items():
            result.append({'name':name,'description':description+' Informe dados reais ou hipóteses explicitamente declaradas; nunca invente entradas.','parameters':{'type':'OBJECT','properties':{'inputs_json':{'type':'STRING','description':'Objeto JSON de entradas com nomes e unidades exatas do contrato; datas AAAA-MM-DD e timezone UTC.'}},'required':['inputs_json']}})
        return result

    def execute(self, name, args):
        if not isinstance(args, dict):
            return {'error':'invalid_arguments'}
        try:
            indicator_names={'sequencia_seca':'I03','exposicao_termica':'I05','evapotranspiracao_cultura':'I07','variacao_hidrica':'I08','margem_cenario':'I14'}
            if name in {'previsao_tempo','simular_aquacrop'} or name in indicator_names:
                if self._climate is None:
                    from .climate_tools import ClimateTools
                    self._climate=ClimateTools(base_url=self.base_url)
                if name=='previsao_tempo':
                    if set(args)-{'location','start_time','end_time','step_hours','parameters','require_complete'}:raise ValueError()
                    output=self._climate.forecast(**args,provider='auto')
                else:
                    if set(args)!={'inputs_json'} or not isinstance(args['inputs_json'],str) or len(args['inputs_json'])>100000:raise ValueError()
                    parsed=json.loads(args['inputs_json'])
                    output=self._climate.aquacrop(parsed) if name=='simular_aquacrop' else self._climate.indicator(indicator_names[name],parsed)
                if not isinstance(output,dict):return {'error':'invalid_response'}
                if len(json.dumps(output,ensure_ascii=False,allow_nan=False))>120000:return {'error':'response_too_large','message':'Solicite um período menor.'}
                return output
            if name in {'nasa_clima_diario','chuva_acumulada','graus_dia_acumulados'}:
                if self._climate is None:
                    from .climate_tools import ClimateTools
                    self._climate=ClimateTools(base_url=self.base_url)
                method={'nasa_clima_diario':self._climate.nasa_daily,'chuva_acumulada':self._climate.rainfall,'graus_dia_acumulados':self._climate.gdd}[name]
                output=method(**args)
                if not isinstance(output,dict):return {'error':'invalid_response'}
                if len(json.dumps(output,ensure_ascii=False,allow_nan=False))>120000:return {'error':'response_too_large','message':'Solicite um período menor.'}
                return output
            if name in {'faostat_paises','faostat_produtos','faostat_precos','faostat_candidatos','faostat_ultimo_preco'}:
                allowed={'faostat_paises':{'q'},'faostat_produtos':{'q','area_code','country_iso2'},'faostat_candidatos':{'q','area_code','country_iso2'},'faostat_ultimo_preco':{'item_code','area_code','country_iso2','element_code','frequency'},'faostat_precos':{'item_code','area_code','country_iso2','start_year','end_year','frequency','month','element_code','limit','offset','order'}}[name]
                if set(args)-allowed:raise ValueError()
                params=dict(args)
                if 'q' in args and (not isinstance(args['q'],str) or not 1<=len(args['q'])<=200):raise ValueError()
                for key in ('area_code','item_code','element_code'):
                    if key in args and (not isinstance(args[key],str) or not re.fullmatch(r'[0-9]{1,10}',args[key])):raise ValueError()
                if 'country_iso2' in args and (not isinstance(args['country_iso2'],str) or not re.fullmatch(r'[A-Z]{2}',args['country_iso2'])):raise ValueError()
                if 'area_code' in args and 'country_iso2' in args:raise ValueError()
                if name=='faostat_candidatos' and (not isinstance(args.get('q'),str) or len(args['q'].strip())<2):raise ValueError()
                if name=='faostat_ultimo_preco' and ('item_code' not in args or not ({'area_code','country_iso2'} & set(args)) or args.get('frequency','annual') not in {'annual','monthly'}):raise ValueError()
                if name=='faostat_precos':
                    if 'item_code' not in args or not ({'area_code','country_iso2'} & set(args)):raise ValueError()
                    for key,low,high in [('start_year',1900,2100),('end_year',1900,2100),('month',1,12),('limit',1,30),('offset',0,100000)]:
                        if key in args and (type(args[key]) is not int or not low<=args[key]<=high):raise ValueError()
                    if args.get('start_year',1900)>args.get('end_year',2100) or args.get('frequency','annual') not in {'annual','monthly','all'} or 'month' in args and args.get('frequency')!='monthly':raise ValueError()
                    params.setdefault('limit',10)
                    if args.get('order','asc') not in {'asc','desc'}:raise ValueError()
                path='/v1/data/faostat/'+{'faostat_paises':'countries','faostat_produtos':'items','faostat_precos':'prices','faostat_candidatos':'items/candidates','faostat_ultimo_preco':'prices/latest'}[name]
            elif name in _SOURCES:
                if set(args)-{'q','filtros_json','limit','offset'}: raise ValueError()
                q=args.get('q');limit=args.get('limit',10);offset=args.get('offset',0)
                if q is not None and (not isinstance(q,str) or not 1<=len(q)<=200): raise ValueError()
                if type(limit) is not int or not 1<=limit<=30 or type(offset) is not int or not 0<=offset<=100000: raise ValueError()
                params={'limit':limit,'offset':offset}
                if q is not None:params['q']=q
                if 'filtros_json' in args:
                    raw=args['filtros_json']
                    if not isinstance(raw,str) or len(raw)>4000:raise ValueError()
                    filters=json.loads(raw)
                    if not isinstance(filters,dict) or any(not isinstance(k,str) or isinstance(v,(dict,list)) for k,v in filters.items()):raise ValueError()
                    params['filtros']=json.dumps(filters,ensure_ascii=False,allow_nan=False)
                path=_SOURCES[name][0]
            elif name=='camadas_gaez':
                if set(args)-{'variable','filename_prefix','page_token'}: raise ValueError()
                params=dict(args);params['limit']=30
                if any(not isinstance(v,str) or len(v)>4000 for v in args.values()): raise ValueError()
                if 'variable' in args and not re.fullmatch(r'[A-Z0-9-]{1,40}',args['variable']): raise ValueError()
                if 'filename_prefix' in args and ('variable' not in args or not re.fullmatch(r'GAEZ-V5\.[A-Za-z0-9_.-]{0,180}',args['filename_prefix'])): raise ValueError()
                path='/api/v1/gaez/layers'
            elif name=='ponto_gaez':
                if set(args)!={'layer','latitude','longitude'} or not isinstance(args['layer'],str) or not 1<=len(args['layer'])<=300: raise ValueError()
                for key,limit in [('latitude',90),('longitude',180)]:
                    value=args[key]
                    if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or abs(value)>limit: raise ValueError()
                path='/api/v1/gaez/point';params=args
            else:return {'error':'unknown_tool'}
            result=self._request(path,params)
            if not isinstance(result,(dict,list)):return {'error':'invalid_response'}
            if len(json.dumps(result,ensure_ascii=False))>120000:return {'error':'response_too_large'}
            return {'data':result}
        except (ValueError,TypeError):return {'error':'invalid_arguments'}
        except (HTTPError,URLError,TimeoutError,OSError,json.JSONDecodeError):return {'error':'analysis_unavailable'}

    def _http_get(self,path,params):
        with urlopen(self.base_url+path+'?'+urlencode(params),timeout=20) as response:
            data=response.read(500001)
            if len(data)>500000:raise ValueError('Resposta excede o limite.')
            return json.loads(data)
