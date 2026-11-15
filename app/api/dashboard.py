"""Preparação inicial da dashboard, sem cálculos agronômicos novos."""
import json
import math
from datetime import datetime, timezone
from typing import Literal

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.api.discovery import _origin_ok, _rate_limit
from app.services.engine import AgrionEngine, EngineError
from app.services.dashboard_data import forecast_section, rainfall_section, stage_section, daily_section, market_section, news_section
from app.services.tools import AnalysisTools

dashboard_blueprint = Blueprint('dashboard', __name__)
HIGHLIGHTS = Literal['current_crop', 'current_season_stage', 'planting_date', 'primary_goal', 'next_crop_preference']


class DashboardSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    highlight_fields: list[HIGHLIGHTS] = Field(max_length=3)


@dashboard_blueprint.post('/api/dashboard/bootstrap')
def bootstrap():
    if not _origin_ok():return jsonify(error='origin_rejected'),403
    if request.content_length is not None and request.content_length>50000:return jsonify(error='request_too_large'),413
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'context'} or not isinstance(body['context'],dict):return jsonify(error='invalid_request'),400
    context=body['context'];property_data=context.get('property');profile=context.get('agricultural_profile')
    if not isinstance(property_data,dict) or not isinstance(property_data.get('id'),str) or not isinstance(profile,dict) or not isinstance(profile.get('fields'),dict):return jsonify(error='invalid_request'),400
    if not _rate_limit('DASHBOARD',30):return jsonify(error='rate_limited'),429
    try:
        result=AgrionEngine().run(task='Selecione informações já declaradas para destacar na visão inicial.',context=context,mode='dashboard')
        selection=DashboardSelection.model_validate_json(result.text)
        fields=profile['fields'];selected=[]
        for key in selection.highlight_fields:
            field=fields.get(key)
            if key not in selected and isinstance(field,dict) and field.get('status')=='confirmed' and isinstance(field.get('value'),dict) and field['value']:
                selected.append(key)
        payload={'schema_version':'1.0','property_id':property_data['id'],'generated_at':datetime.now(timezone.utc).isoformat(),'highlight_fields':selected,'sections':{key:{'status':'unavailable','metrics':[]} for key in ('conditions','development','recommendations','market','news','measurements','history')},'alerts':[]}
        return jsonify(payload)
    except (EngineError,ValueError,ValidationError,json.JSONDecodeError):
        return jsonify(error='dashboard_unavailable'),503


@dashboard_blueprint.post('/api/dashboard/<section>')
def section(section):
    operations={'forecast':forecast_section,'rainfall':rainfall_section,'stage':stage_section,'daily':daily_section,'market-analysis':market_section,'news':news_section}
    if section not in operations:return jsonify(error='not_found'),404
    if not _origin_ok():return jsonify(error='origin_rejected'),403
    if request.content_length is not None and request.content_length>50000:return jsonify(error='request_too_large'),413
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'context'} or not isinstance(body['context'],dict):return jsonify(error='invalid_request'),400
    context=body['context'];property_data=context.get('property');profile=context.get('agricultural_profile')
    if not isinstance(property_data,dict) or not isinstance(property_data.get('id'),str) or not isinstance(profile,dict) or not isinstance(profile.get('fields'),dict):return jsonify(error='invalid_request'),400
    if not _rate_limit('DASHBOARD_'+section.upper(),30):return jsonify(error='rate_limited'),429
    result=operations[section](context)
    return jsonify(schema_version='1.0',property_id=property_data['id'],section=section,result=result)


@dashboard_blueprint.post('/api/dashboard/market')
def market():
    if not _origin_ok():return jsonify(error='origin_rejected'),403
    if request.content_length is not None and request.content_length>12000:return jsonify(error='request_too_large'),413
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)!={'property_id','action','inputs'} or not isinstance(body['property_id'],str) or not 1<=len(body['property_id'])<=100 or not isinstance(body['inputs'],dict):return jsonify(error='invalid_request'),400
    if not _rate_limit('DASHBOARD_MARKET',120):return jsonify(error='rate_limited'),429
    action=body['action'];inputs=body['inputs']
    if action not in {'countries','products','prices','scenario'}:return jsonify(error='invalid_request'),400
    tool={'countries':'faostat_paises','products':'faostat_produtos','prices':'faostat_precos','scenario':'margem_cenario'}[action]
    if action=='scenario':
        if set(inputs)!={'area_code','item_code','year','area_ha','yield_t_ha','cost_per_ha'}:return jsonify(error='invalid_request'),400
        year=inputs.get('year')
        if type(year) is not int or not 1900<=year<=2100:return jsonify(error='invalid_request'),400
        for key in ('area_code','item_code'):
            value=inputs.get(key)
            if not isinstance(value,str) or not value.isascii() or not value.isdigit() or len(value)>10:return jsonify(error='invalid_request'),400
        for key in ('area_ha','yield_t_ha','cost_per_ha'):
            value=inputs.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0 or value>1000000000 or key=='area_ha' and value==0:return jsonify(error='invalid_request'),400
        scenario_year=datetime.now(timezone.utc).year
        values={'start_date':f'{scenario_year}-01-01','end_date':f'{scenario_year}-12-31','crop_id':inputs['item_code'],'area_ha':inputs['area_ha'],'expected_yield_t_per_ha':inputs['yield_t_ha'],'cost_per_ha':inputs['cost_per_ha'],'currency':'USD','assumptions_reference':'Área, produtividade e custos declarados no cenário; preço histórico FAOSTAT selecionado.','faostat_price':{'area_code':inputs['area_code'],'item_code':inputs['item_code'],'year':year,'reference':'Observação histórica nacional selecionada pelo usuário; não é preço previsto.'}}
        inputs={'inputs_json':json.dumps(values,allow_nan=False)}
    result=AnalysisTools().execute(tool,inputs)
    if result.get('error')=='invalid_arguments':return jsonify(error='invalid_request'),400
    if result.get('error') or result.get('ok') is False:return jsonify(error='market_unavailable'),503
    return jsonify(schema_version='1.0',property_id=body['property_id'],result=result.get('data'))
