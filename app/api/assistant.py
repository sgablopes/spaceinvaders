"""API de conversa textual, com credenciais mantidas no servidor."""
from flask import Blueprint, jsonify, request
from app.api.discovery import _origin_ok, _rate_limit
from app.services.engine import AgrionEngine, EngineConfigurationError, EngineUnavailableError
from app.services.dashboard_data import search_entries

assistant_blueprint = Blueprint('assistant', __name__)


@assistant_blueprint.post('/api/assistant/message')
def message():
    if not _origin_ok():
        return jsonify(error='origin_rejected'), 403
    if request.content_length is not None and request.content_length > 180000:
        return jsonify(error='request_too_large'), 413
    body=request.get_json(silent=True)
    if not isinstance(body,dict) or set(body)-{'message','context','history','language'}:
        return jsonify(error='invalid_request'), 400
    if not _rate_limit('ASSISTANT_MESSAGES', 60):
        return jsonify(error='rate_limited'), 429
    try:
        result=AgrionEngine().run(task=body.get('message'), context=body.get('context'), history=body.get('history'), language=body.get('language','pt-BR'))
    except ValueError:
        return jsonify(error='invalid_request'), 400
    except EngineConfigurationError:
        return jsonify(error='not_configured'), 503
    except EngineUnavailableError:
        return jsonify(error='assistant_unavailable'), 503
    response=jsonify(text=result.text, tools_used=list(result.tools_used), search_entry_points=search_entries(result.tool_evidence))
    response.headers['Cache-Control']='no-store'
    return response
