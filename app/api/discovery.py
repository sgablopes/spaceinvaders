"""Vertex AI backed Agrion Discovery endpoints. No Google credential reaches the browser."""

import json
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from urllib.parse import urlsplit

import google.auth
from google.auth.transport.requests import Request as AuthRequest
from flask import Blueprint, current_app, jsonify, request
from flask_sock import Sock
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

discovery_blueprint = Blueprint("discovery", __name__)
sock = Sock()
_hits = defaultdict(deque)
_hit_lock = threading.Lock()
FIELDS = {"last_crop", "previous_crop", "last_harvest_result", "main_difficulties", "irrigation", "mechanization", "primary_goal", "fertilization", "soil_management", "cover_crops", "other_crops", "water_access", "budget_constraints", "technical_resources"}
DIFFICULTIES = {"drought", "excess_rain", "pests", "diseases", "soil", "input_costs", "labor", "machinery", "market", "other"}
GOALS = {"maximize_profit", "increase_yield", "restore_soil", "reduce_risk", "reduce_costs", "diversify", "other"}
LANGUAGES = {"pt-BR", "en-US", "es-US"}
VOICES = {"Zephyr", "Kore", "Orus", "Autonoe", "Umbriel", "Erinome", "Laomedeia", "Schedar", "Achird", "Sadachbia", "Puck", "Fenrir", "Aoede", "Enceladus", "Algieba", "Algenib", "Achernar", "Gacrux", "Zubenelgenubi", "Sadaltager", "Charon", "Leda", "Callirrhoe", "Iapetus", "Rasalgethi", "Alnilam", "Pulcherrima", "Forward", "Vindemiatrix", "Sulafat"}


def _live_text_frame(message):
    """The Vertex socket may return UTF-8 JSON in a binary WebSocket frame."""
    return message.decode("utf-8") if isinstance(message, bytes) else message


class ConfigurationError(RuntimeError):
    pass


class Patch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    operation: str
    value: dict | None = None
    status: str
    confidence: str | None = None
    evidence_excerpt: str
    unknown_reason: str | None = None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patches: list[Patch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _uuid(value):
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _origin_ok():
    origin = request.headers.get("Origin")
    if not origin:
        return True
    parsed = urlsplit(origin)
    public_origin = os.getenv("AGRION_PUBLIC_ORIGIN", "").rstrip("/")
    if public_origin:
        return origin == public_origin
    # TLS is terminated by Nginx; Flask can see http while the browser uses https.
    return parsed.scheme in {"http", "https"} and parsed.netloc == request.host and parsed.path == "" and not parsed.query and not parsed.fragment


def _rate_limit(kind, default):
    limit = max(1, int(os.getenv(f"AGRION_{kind}_PER_HOUR", default)))
    key = (kind, request.remote_addr)
    now = time.monotonic()
    with _hit_lock:
        queue = _hits[key]
        while queue and now - queue[0] >= 3600:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
    return True


def _config():
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip()
    if not project or not location:
        raise ConfigurationError("vertex_not_configured")
    return project, location


def _validate_value(patch):
    value = patch.value
    if patch.field not in FIELDS or patch.operation not in {"set", "merge"}:
        return False
    if patch.status not in {"confirmed", "uncertain", "unknown"} or patch.confidence not in {"high", "medium", "low", None}:
        return False
    if patch.unknown_reason not in {None, "does_not_know", "does_not_remember", "declined"}:
        return False
    if patch.status == "unknown":
        return value is None and patch.unknown_reason is not None
    if patch.unknown_reason is not None or not isinstance(value, dict):
        return False
    if patch.field in {"last_crop", "previous_crop"}:
        return set(value) <= {"crop", "period_label", "no_previous_cultivation"} and (isinstance(value.get("crop"), str) or value.get("no_previous_cultivation") is True)
    if patch.field == "last_harvest_result":
        return set(value) <= {"crop", "quantity", "unit", "bag_weight_kg", "qualitative_result", "notes"} and value.get("qualitative_result") in {None, "good", "average", "poor", "no_harvest"} and (value.get("quantity") is None or isinstance(value["quantity"], (int, float)))
    if patch.field == "main_difficulties":
        return set(value) <= {"categories", "free_text", "explicit_none"} and set(value.get("categories", [])) <= DIFFICULTIES and isinstance(value.get("free_text", []), list)
    if patch.field == "irrigation":
        return set(value) <= {"water_regime", "irrigation_method", "automated", "notes"} and value.get("water_regime", "unknown") in {"rainfed", "irrigated", "mixed", "unknown"} and value.get("irrigation_method", "unknown") in {"none", "manual", "drip", "sprinkler", "center_pivot", "furrow", "other", "unknown"} and value.get("automated") in {True, False, None}
    if patch.field == "mechanization":
        return set(value) <= {"work_mode", "equipment", "automation_level", "notes"} and value.get("work_mode", "unknown") in {"manual", "mixed", "mechanized", "automated", "unknown"} and value.get("automation_level", "unknown") in {"none", "partial", "high", "unknown"} and isinstance(value.get("equipment", []), list)
    if patch.field == "primary_goal":
        return set(value) <= {"category", "description"} and value.get("category") in GOALS
    return isinstance(value, dict)


@discovery_blueprint.post("/api/interview/extract")
def extract():
    if not _origin_ok():
        return jsonify(error="origin_rejected"), 403
    if request.content_length and request.content_length > 16000:
        return jsonify(error="invalid_request"), 422
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not _uuid(body.get("interview_id")) or not _uuid(body.get("property_id")) or not isinstance(body.get("turn_id"), str) or len(body["turn_id"]) > 100 or not isinstance(body.get("sequence"), int) or body["sequence"] < 1 or body.get("speaker") != "farmer" or not isinstance(body.get("transcript"), str) or not 1 <= len(body["transcript"]) <= 3000 or not isinstance(body.get("profile_revision"), int) or body["profile_revision"] < 0 or not isinstance(body.get("profile_snapshot"), dict):
        return jsonify(error="invalid_request"), 422
    if not _rate_limit("EXTRACTIONS", 120):
        return jsonify(error="rate_limited"), 429
    try:
        project, _ = _config()
        extraction_location = os.getenv("GOOGLE_CLOUD_EXTRACTION_LOCATION", "us").strip()
        if not extraction_location:
            raise ConfigurationError("vertex_not_configured")
        client_options = {"vertexai": True, "project": project, "location": extraction_location}
        if extraction_location in {"us", "eu"}:
            client_options["http_options"] = types.HttpOptions(
                api_version="v1",
                base_url=f"https://aiplatform.{extraction_location}.rep.googleapis.com",
            )
        client = genai.Client(**client_options)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_EXTRACTION_MODEL", "gemini-3.5-flash-lite"),
            contents=json.dumps({"transcript": body["transcript"], "profile_snapshot": body["profile_snapshot"]}, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=("Você extrai fatos agrícolas explícitos de qualquer idioma. Retorne somente patches no esquema. "
                    "IDs dos campos e categorias devem permanecer nos enums canônicos ingleses, independentemente do idioma da conversa. "
                    "Não deduza fatos, anos, unidades, produtividade, mecanização ou irrigação. Uma fala pode gerar vários patches. "
                    "A evidência deve ser trecho literal da fala. 'Não sei' é unknown; estimativa é uncertain. "
                    "Não altere geometria. Não faça recomendações."),
                response_mime_type="application/json", response_schema=Extraction,
            ),
        )
        result = Extraction.model_validate_json(response.text)
        patches = [p for p in result.patches if _validate_value(p) and p.evidence_excerpt and p.evidence_excerpt in body["transcript"]]
        return jsonify(interview_id=body["interview_id"], turn_id=body["turn_id"], sequence=body["sequence"], base_profile_revision=body["profile_revision"], patches=[p.model_dump() for p in patches], warnings=result.warnings[:5])
    except ConfigurationError:
        return jsonify(error="vertex_not_configured"), 503
    except (ValidationError, ValueError):
        return jsonify(error="invalid_provider_response"), 502
    except Exception as error:
        current_app.logger.warning("Discovery extraction failure (%s)", type(error).__name__)
        return jsonify(error="vertex_unavailable"), 503


def register_socket(app):
    sock.init_app(app)

    @sock.route("/api/interview/live-session")
    def live(ws):
        if not _origin_ok():
            app.logger.warning("Discovery Live origin rejected")
            ws.send(json.dumps({"error": "origin_rejected"}))
            return
        if not _rate_limit("LIVE_SESSIONS", 8):
            app.logger.warning("Discovery Live rate limit reached")
            ws.send(json.dumps({"error": "live_rate_limited"}))
            return
        phase = "configuration"
        try:
            project, location = _config()
            phase = "client_setup"
            first_raw = ws.receive()
            if not first_raw or len(first_raw) > 4096:
                ws.send(json.dumps({"error": "invalid_request"}))
                return
            first = json.loads(first_raw)
            if not isinstance(first, dict):
                ws.send(json.dumps({"error": "invalid_request"}))
                return
            language = first.get("language", "pt-BR")
            voice = first.get("voice", "")
            if language not in LANGUAGES or voice not in VOICES | {""} or not _uuid(first.get("interview_id")) or not _uuid(first.get("property_id")):
                ws.send(json.dumps({"error": "invalid_request"}))
                return
            name = str(first.get("person_name", ""))[:100]
            property_name = str(first.get("property_name", ""))[:120]
            phase = "vm_credentials"
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            credentials.refresh(AuthRequest())
            phase = "vertex_connect"
            url = f"wss://{location}-aiplatform.googleapis.com/ws/google.cloud.aiplatform.v1.LlmBidiService/BidiGenerateContent"
            with connect(url, additional_headers={"Authorization": f"Bearer {credentials.token}"}, max_size=2**22) as upstream:
                phase = "vertex_setup"
                instruction = (f"Você é Agrion. Converse em {language}, em linguagem simples e acolhedora, uma pergunta por vez. "
                    f"Pessoa: {name}. Propriedade: {property_name}. Comece perguntando a última cultura nesta área. "
                    "Conheça última cultura, cultura imediatamente anterior, resultado da colheita, dificuldades, irrigação, mecanização e objetivo. "
                    "Não invente dados nem recomendações. Respeite não sei. Seja breve. Se receber CLOSE_REQUESTED, agradeça e despeça-se sem nova pergunta. "
                    "Quando tiver concluído, chame complete_initial_interview. Nunca cite JSON, ferramentas ou estados internos.")
                speech_config = {"languageCode": language}
                if voice:
                    speech_config["voiceConfig"] = {"prebuiltVoiceConfig": {"voiceName": voice}}
                upstream.send(json.dumps({"setup": {"model": f"projects/{project}/locations/{location}/publishers/google/models/{os.getenv('GEMINI_LIVE_MODEL', 'gemini-3.8-live')}", "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech_config}, "systemInstruction": {"parts": [{"text": instruction}]}, "inputAudioTranscription": {}, "outputAudioTranscription": {}, "tools": [{"functionDeclarations": [{"name": "complete_initial_interview", "description": "Request interview completion when essential facts are resolved or farmer asks to stop", "parameters": {"type": "OBJECT", "properties": {"reason": {"type": "STRING"}}}}]}]}}))
                stop = threading.Event()

                def browser_to_vertex():
                    try:
                        while not stop.is_set():
                            message = ws.receive()
                            if message is None:
                                break
                            obj = json.loads(message)
                            if set(obj) <= {"realtimeInput", "clientContent", "toolResponse"} and len(message) <= 100000:
                                upstream.send(message)
                    except Exception:
                        pass
                    finally:
                        stop.set()

                threading.Thread(target=browser_to_vertex, daemon=True).start()
                for message in upstream:
                    if stop.is_set():
                        break
                    message = _live_text_frame(message)
                    if phase == "vertex_setup" and "setupComplete" in json.loads(message):
                        phase = "relay"
                    ws.send(message)
        except ConnectionClosed as error:
            close = error.rcvd or error.sent
            app.logger.warning("Discovery Live closed in %s (code=%s)", phase, close.code if close else "none")
            try:
                ws.send(json.dumps({"error": "vertex_connection_closed", "stage": phase, "code": close.code if close else None}))
            except Exception:
                pass
        except ConfigurationError:
            app.logger.warning("Discovery Live configuration failure in %s", phase)
            try:
                ws.send(json.dumps({"error": "vertex_not_configured"}))
            except Exception:
                pass
        except Exception as error:
            app.logger.warning("Discovery Live failure in %s (%s)", phase, type(error).__name__)
            try:
                ws.send(json.dumps({"error": "vertex_unavailable", "stage": phase}))
            except Exception:
                pass
