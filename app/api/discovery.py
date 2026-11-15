"""Vertex AI backed Agrion Discovery endpoints. No Google credential reaches the browser."""

import json
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Literal
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


class GenerationPatch(Patch):
    field: Literal["last_crop", "previous_crop", "last_harvest_result", "main_difficulties", "irrigation", "mechanization", "primary_goal", "fertilization", "soil_management", "cover_crops", "other_crops", "water_access", "budget_constraints", "technical_resources"] = Field(
        description="Agrion field ID. last_crop is the most recent crop; previous_crop is the crop immediately before it; last_harvest_result is the last harvest outcome; main_difficulties are farming problems; primary_goal is the next-season goal."
    )
    operation: Literal["set", "merge"] = Field(description="Use set for a new or corrected fact; merge only to add details to an existing fact.")
    value: dict | None = Field(description=(
        "Canonical object for the selected field; unknown answers use null. "
        "last_crop and previous_crop use crop as a string. "
        "last_harvest_result uses qualitative_result (good, average, poor, no_harvest), or explicit quantity and unit. "
        "main_difficulties uses categories (drought, excess_rain, pests, diseases, soil, input_costs, labor, machinery, market, other) and free_text as a list. "
        "irrigation uses water_regime (rainfed, irrigated, mixed, unknown), irrigation_method (none, manual, drip, sprinkler, center_pivot, furrow, other, unknown), and automated (true, false, null). "
        "mechanization uses work_mode (manual, mixed, mechanized, automated, unknown), equipment as a list, and automation_level (none, partial, high, unknown). "
        "primary_goal uses category (maximize_profit, increase_yield, restore_soil, reduce_risk, reduce_costs, diversify, other) and optional description."
    ))
    status: Literal["confirmed", "uncertain", "unknown"] = Field(description="confirmed for an explicit report, uncertain for an estimate or ambiguity, unknown only when the farmer explicitly does not know, remember, or answer.")
    confidence: Literal["high", "medium", "low"] | None = None
    evidence_excerpt: str = Field(description="Copy a short exact substring from the farmer's transcript, preserving spelling and accents.")
    unknown_reason: Literal["does_not_know", "does_not_remember", "declined"] | None = Field(default=None, description="Required when status is unknown; otherwise null.")


class GenerationExtraction(BaseModel):
    patches: list[GenerationPatch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CropValue(BaseModel):
    crop: str | None
    period_label: str | None = None
    no_previous_cultivation: bool | None = None


class HarvestValue(BaseModel):
    qualitative_result: Literal["good", "average", "poor", "no_harvest"] | None
    quantity: float | None = None
    unit: str | None = None
    crop: str | None = None
    bag_weight_kg: float | None = None
    notes: str | None = None


class DifficultiesValue(BaseModel):
    categories: list[Literal["drought", "excess_rain", "pests", "diseases", "soil", "input_costs", "labor", "machinery", "market", "other"]]
    free_text: list[str] = Field(default_factory=list)
    explicit_none: bool = False


class IrrigationValue(BaseModel):
    water_regime: Literal["rainfed", "irrigated", "mixed", "unknown"]
    irrigation_method: Literal["none", "manual", "drip", "sprinkler", "center_pivot", "furrow", "other", "unknown"] | None = None
    automated: bool | None = None
    notes: str | None = None


class MechanizationValue(BaseModel):
    work_mode: Literal["manual", "mixed", "mechanized", "automated", "unknown"]
    equipment: list[str] = Field(default_factory=list)
    automation_level: Literal["none", "partial", "high", "unknown"] | None = None
    notes: str | None = None


class GoalValue(BaseModel):
    category: Literal["maximize_profit", "increase_yield", "restore_soil", "reduce_risk", "reduce_costs", "diversify", "other"]
    description: str | None = None


class UnknownReason(BaseModel):
    reason: Literal["does_not_know", "does_not_remember", "declined", "none"]


RECOVERY_SCHEMAS = {"last_crop": CropValue, "previous_crop": CropValue, "last_harvest_result": HarvestValue, "main_difficulties": DifficultiesValue, "irrigation": IrrigationValue, "mechanization": MechanizationValue, "primary_goal": GoalValue}


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
    if patch.status == "uncertain" and value is None and patch.unknown_reason is None:
        return True
    if patch.unknown_reason is not None or not isinstance(value, dict):
        return False
    if patch.field in {"last_crop", "previous_crop"}:
        return set(value) <= {"crop", "period_label", "no_previous_cultivation"} and (isinstance(value.get("crop"), str) and bool(value["crop"].strip()) or patch.field == "previous_crop" and value.get("no_previous_cultivation") is True)
    if patch.field == "last_harvest_result":
        return set(value) <= {"crop", "quantity", "unit", "bag_weight_kg", "qualitative_result", "notes"} and value.get("qualitative_result") in {None, "good", "average", "poor", "no_harvest"} and (value.get("quantity") is None or isinstance(value["quantity"], (int, float))) and (value.get("qualitative_result") is not None or value.get("quantity") is not None)
    if patch.field == "main_difficulties":
        categories=value.get("categories", []);free_text=value.get("free_text", [])
        return set(value) <= {"categories", "free_text", "explicit_none"} and isinstance(categories, list) and set(categories) <= DIFFICULTIES and isinstance(free_text, list) and bool(categories or free_text or value.get("explicit_none") is True)
    if patch.field == "irrigation":
        return set(value) <= {"water_regime", "irrigation_method", "automated", "notes"} and value.get("water_regime", "unknown") in {"rainfed", "irrigated", "mixed", "unknown"} and value.get("irrigation_method", "unknown") in {"none", "manual", "drip", "sprinkler", "center_pivot", "furrow", "other", "unknown"} and value.get("automated") in {True, False, None} and (value.get("water_regime") not in {None, "unknown"} or value.get("irrigation_method") not in {None, "unknown"})
    if patch.field == "mechanization":
        return set(value) <= {"work_mode", "equipment", "automation_level", "notes"} and value.get("work_mode", "unknown") in {"manual", "mixed", "mechanized", "automated", "unknown"} and value.get("automation_level", "unknown") in {"none", "partial", "high", "unknown"} and isinstance(value.get("equipment", []), list) and (value.get("work_mode") not in {None, "unknown"} or bool(value.get("equipment")))
    if patch.field == "primary_goal":
        return set(value) <= {"category", "description"} and value.get("category") in GOALS
    return bool(value)


@discovery_blueprint.post("/api/interview/extract")
def extract():
    if not _origin_ok():
        return jsonify(error="origin_rejected"), 403
    if request.content_length and request.content_length > 16000:
        return jsonify(error="invalid_request"), 422
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not _uuid(body.get("interview_id")) or not _uuid(body.get("property_id")) or not isinstance(body.get("turn_id"), str) or len(body["turn_id"]) > 100 or not isinstance(body.get("sequence"), int) or body["sequence"] < 1 or body.get("speaker") != "farmer" or not isinstance(body.get("transcript"), str) or not 1 <= len(body["transcript"]) <= 3000 or not isinstance(body.get("assistant_context", ""), str) or len(body.get("assistant_context", "")) > 1000 or not isinstance(body.get("profile_revision"), int) or body["profile_revision"] < 0 or not isinstance(body.get("profile_snapshot"), dict):
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
        model = os.getenv("GEMINI_EXTRACTION_MODEL", "gemini-3.5-flash-lite")
        context = body.get("assistant_context", "")
        contents = json.dumps({"farmer_transcript": body["transcript"], "previous_assistant_question": context, "profile_snapshot": body["profile_snapshot"]}, ensure_ascii=False)
        instruction = ("Extraia somente fatos agrícolas explicitamente relatados pelo agricultor, em qualquer idioma. "
            "A pergunta anterior esclarece a que campo uma resposta curta se refere, mas nunca serve como evidência. "
            "IDs e categorias permanecem canônicos em inglês. Uma fala pode gerar vários patches. "
            "Copie a evidência literalmente da fala do agricultor. Não invente fatos, datas, medidas ou equipamentos. "
            "Não sei é unknown; estimativa é uncertain. Não altere geometria nem faça recomendações.")
        config = types.GenerateContentConfig(system_instruction=instruction, response_mime_type="application/json", response_schema=GenerationExtraction)
        response = client.models.generate_content(model=model, contents=contents, config=config)
        result = Extraction.model_validate_json(response.text)
        if not result.patches and context and len(body["transcript"]) < 150:
            retry_config = types.GenerateContentConfig(system_instruction=instruction + " A resposta curta do agricultor responde à pergunta anterior. Identifique o campo perguntado e extraia o valor explícito, se houver.", response_mime_type="application/json", response_schema=GenerationExtraction)
            result = Extraction.model_validate_json(client.models.generate_content(model=model, contents=contents, config=retry_config).text)
        patches = []
        for patch in result.patches:
            if not patch.evidence_excerpt or patch.evidence_excerpt not in body["transcript"]:
                continue
            if _validate_value(patch):
                patches.append(patch)
                continue
            if patch.status == "unknown" and patch.field in RECOVERY_SCHEMAS:
                try:
                    reason_response = client.models.generate_content(model=model, contents=patch.evidence_excerpt, config=types.GenerateContentConfig(
                        system_instruction="Classifique apenas uma recusa ou desconhecimento explicitamente dito pelo agricultor. Se a fala não indicar isso, retorne none.",
                        response_mime_type="application/json", response_schema=UnknownReason,
                    ))
                    reason = UnknownReason.model_validate_json(reason_response.text).reason
                    repaired = patch.model_copy(update={"value": None, "unknown_reason": reason})
                    if reason != "none" and _validate_value(repaired):
                        patches.append(repaired)
                except Exception as error:
                    current_app.logger.warning("Discovery unknown-answer recovery failure (%s, %s)", patch.field, type(error).__name__)
                continue
            schema = RECOVERY_SCHEMAS.get(patch.field)
            if not schema or patch.status not in {"confirmed", "uncertain"}:
                continue
            try:
                repair_contents = json.dumps({"farmer_transcript": body["transcript"], "previous_assistant_question": context, "field": patch.field}, ensure_ascii=False)
                repaired_response = client.models.generate_content(model=model, contents=repair_contents, config=types.GenerateContentConfig(
                    system_instruction="Preencha apenas o valor do campo indicado com fatos explícitos da fala do agricultor. A pergunta anterior esclarece o campo, mas não é evidência. Não invente dados; respeite o formato exigido pelo esquema.",
                    response_mime_type="application/json", response_schema=schema,
                ))
                value = schema.model_validate_json(repaired_response.text).model_dump(exclude_none=True)
                repaired = patch.model_copy(update={"value": value})
                if _validate_value(repaired):
                    patches.append(repaired)
            except Exception as error:
                current_app.logger.warning("Discovery field recovery failure (%s, %s)", patch.field, type(error).__name__)
        if result.patches and not patches:
            current_app.logger.warning("Discovery extraction rejected all %d generated patches", len(result.patches))
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
