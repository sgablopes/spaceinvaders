"""Análise de planejamento independente da renderização da página."""
import json
from flask import Blueprint, jsonify, request
from app.api.discovery import _origin_ok, _rate_limit
from app.services.planning import analyze

planning_blueprint = Blueprint('planning', __name__)


@planning_blueprint.post('/api/planning/analyze')
def planning_analysis():
    if not _origin_ok():
        return jsonify(error='origin_rejected'), 403
    request.max_content_length = 45000
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {'context', 'inputs'}:
        return jsonify(error='invalid_request'), 400
    context, inputs = body['context'], body['inputs']
    if not isinstance(context, dict) or not isinstance(inputs, dict):
        return jsonify(error='invalid_request'), 400
    prop = context.get('property')
    if not isinstance(prop, dict) or not isinstance(prop.get('id'), str) or not 1 <= len(prop['id']) <= 100:
        return jsonify(error='invalid_request'), 400
    allowed = {'soil', 'water', 'labor', 'equipment', 'objective', 'selected_crops'}
    if set(inputs) - allowed:
        return jsonify(error='invalid_request'), 400
    for key, value in inputs.items():
        if key == 'selected_crops':
            if not isinstance(value, list) or len(value) > 8 or any(not isinstance(v, str) or len(v) > 80 for v in value):
                return jsonify(error='invalid_request'), 400
        elif not isinstance(value, str) or len(value) > 600:
            return jsonify(error='invalid_request'), 400
    merged = {**context, 'planning_inputs': inputs}
    try:
        if len(json.dumps(merged, ensure_ascii=False, allow_nan=False)) > 32000:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify(error='invalid_request'), 400
    if not _rate_limit('PLANNING', 12):
        return jsonify(error='rate_limited'), 429
    response = jsonify(property_id=prop['id'], result=analyze(merged))
    response.headers['Cache-Control'] = 'no-store'
    return response
