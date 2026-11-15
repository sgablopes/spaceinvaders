"""Vertex AI backed Agrion Discovery endpoints. No Google credential reaches the browser."""

import json
import re
from datetime import date
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
FIELDS = {"last_crop", "previous_crop", "last_harvest_result", "main_difficulties", "irrigation", "mechanization", "primary_goal", "next_crop_preference", "current_season_stage", "fertilization", "soil_management", "cover_crops", "other_crops", "water_access", "budget_constraints", "technical_resources"}
FIELDS.update({"current_crop", "planting_date"})
DIFFICULTIES = {"drought", "excess_rain", "pests", "diseases", "soil", "input_costs", "labor", "machinery", "market", "other"}
GOALS = {"maximize_profit", "increase_yield", "restore_soil", "reduce_risk", "reduce_costs", "diversify", "other"}
LANGUAGES = {"pt-BR", "en-US", "es-US"}
ESSENTIAL_FIELDS = ("last_crop", "previous_crop", "last_harvest_result", "main_difficulties", "irrigation", "mechanization", "primary_goal", "next_crop_preference", "current_crop", "planting_date", "current_season_stage")


def _live_state_instruction(base, state):
    """Build a bounded system update from canonical browser profile statuses."""
    if not isinstance(state, dict) or not isinstance(state.get("fields"), dict):
        return None
    fields = state["fields"]
    if any(fields.get(field) not in {"pending", "confirmed", "uncertain", "unknown"} for field in ESSENTIAL_FIELDS):
        return None
    pending = [field for field in ESSENTIAL_FIELDS if fields[field] == "pending"]
    uncertain = [field for field in ESSENTIAL_FIELDS if fields[field] == "uncertain"]
    resolved = [field for field in ESSENTIAL_FIELDS if fields[field] in {"confirmed", "unknown"}]
    closing = state.get("closing") is True
    clarify = state.get("clarify") is True
    confirmation_attempted = state.get("confirmation_attempted") is True
    intro_stage = state.get("intro_stage", 0)
    harvest_estimate_pending = state.get("harvest_estimate_pending") is True
    first_cultivation = state.get("first_cultivation") is True
    if closing:
        guidance = "Encerramento solicitado. Agradeça, explique que as informações foram salvas e despeça-se agora sem outra pergunta."
    elif intro_stage == 0:
        guidance = "Diga brevemente que é o Agrion e pergunte se a pessoa está bem. Aguarde a resposta antes de explicar a entrevista."
    elif intro_stage == 1:
        guidance = "Explique brevemente que conhecerá a área para ajudar no planejamento. Convide a pessoa a contar livremente o último plantio, a colheita e dificuldades; depois pergunte só o que faltar."
    elif clarify:
        guidance = "A última resposta não resolveu a pergunta: reformule-a uma vez, com simplicidade; depois avance se continuar sem resposta. Não repita campo unknown. Nunca anuncie conclusão antes da autorização da ferramenta."
    elif harvest_estimate_pending:
        guidance = "O resultado qualitativo da colheita já foi salvo. Peça uma estimativa em sacas, toneladas ou valor financeiro, conforme a pessoa souber. Não invente unidade ou valor; se ela não souber, registre isso e avance."
    elif uncertain and not pending and not confirmation_attempted:
        guidance = "Confirme brevemente uma informação incerta antes de concluir; não repita a confirmação."
    elif first_cultivation and pending:
        guidance = "Esta área terá o primeiro cultivo. Não pergunte sobre uma colheita passada. Se faltar o registro de ausência de cultivo anterior, confirme isso brevemente. Pergunte sobre preferência de plantio, fase atual, recursos, objetivo e dificuldades para começar conforme as lacunas."
    else:
        guidance = "Pergunte sobre um pendente por vez. Não repita campo unknown. Nunca anuncie conclusão antes da autorização da ferramenta."
    return (base + "\nEstado atual do aplicativo: "
        f"resolvidos={','.join(resolved) or 'nenhum'}; pendentes={','.join(pending) or 'nenhum'}; incertos={','.join(uncertain) or 'nenhum'}. "
        + guidance)


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
    evidence_turn_id: str | None = None
    unknown_reason: str | None = None


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patches: list[Patch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GenerationPatch(Patch):
    field: Literal["last_crop", "previous_crop", "last_harvest_result", "main_difficulties", "irrigation", "mechanization", "primary_goal", "next_crop_preference", "current_crop", "planting_date", "current_season_stage", "fertilization", "soil_management", "cover_crops", "other_crops", "water_access", "budget_constraints", "technical_resources"] = Field(
        description="Agrion field ID. last_crop is the most recent crop; previous_crop is immediately before it; last_harvest_result is the last harvest outcome; main_difficulties are farming problems; primary_goal is the next-season goal; next_crop_preference is the farmer's preferred next crop; current_season_stage is the current season stage."
    )
    operation: Literal["set", "merge"] = Field(description="Use set for a new or corrected fact; merge only to add details to an existing fact.")
    value: dict | None = Field(description=(
        "Canonical object for the selected field; unknown answers use null. "
        "last_crop and previous_crop use crop as a string; if the area was never cultivated, last_crop uses never_cultivated=true and previous_crop uses no_previous_cultivation=true, both with crop=null. "
        "last_harvest_result uses qualitative_result (good, average, poor, no_harvest, not_applicable), explicit quantity and unit, or financial_amount and currency. not_applicable means the farmer never cultivated the area. financial_kind identifies revenue or profit only if explicit. estimate_unavailable is true only if the farmer explicitly cannot give an estimate. "
        "main_difficulties uses categories (drought, excess_rain, pests, diseases, soil, input_costs, labor, machinery, market, other) and free_text as a list. "
        "irrigation uses water_regime (rainfed, irrigated, mixed, unknown), irrigation_method (none, manual, drip, sprinkler, center_pivot, furrow, other, unknown), and automated (true, false, null). "
        "mechanization uses work_mode (manual, mixed, mechanized, automated, unknown), equipment as a list, and automation_level (none, partial, high, unknown). "
        "primary_goal uses category (maximize_profit, increase_yield, restore_soil, reduce_risk, reduce_costs, diversify, other) and optional description. "
        "next_crop_preference uses crop and no_preference; explicit no preference has crop=null and no_preference=true. "
        "current_crop uses crop as a string. planting_date uses date as YYYY, YYYY-MM or YYYY-MM-DD, or not_planted=true when explicitly not yet planted. Never invent missing date components. "
        "current_season_stage uses stage (not_started, planning, soil_preparation, planting, growing, flowering, fruiting, harvesting, post_harvest, fallow, other) and optional notes."
    ))
    status: Literal["confirmed", "uncertain", "unknown"] = Field(description="confirmed for an explicit report, uncertain for an estimate or ambiguity, unknown only when the farmer explicitly does not know, remember, or answer.")
    confidence: Literal["high", "medium", "low"] | None = None
    evidence_excerpt: str = Field(description="Copy a short exact substring from the farmer's transcript, preserving spelling and accents.")
    evidence_turn_id: str | None = Field(default=None, description="Turn ID of the farmer statement containing this evidence. Use the current turn ID for the current transcript.")
    unknown_reason: Literal["does_not_know", "does_not_remember", "declined"] | None = Field(default=None, description="Required when status is unknown; otherwise null.")


class GenerationExtraction(BaseModel):
    patches: list[GenerationPatch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CropValue(BaseModel):
    crop: str | None
    period_label: str | None = None
    no_previous_cultivation: bool | None = None
    never_cultivated: bool | None = None


class HarvestValue(BaseModel):
    qualitative_result: Literal["good", "average", "poor", "no_harvest", "not_applicable"] | None = None
    quantity: float | None = None
    unit: str | None = None
    crop: str | None = None
    bag_weight_kg: float | None = None
    notes: str | None = None
    financial_amount: float | None = None
    currency: Literal["BRL", "USD", "EUR"] | None = None
    financial_kind: Literal["revenue", "profit", "unknown"] | None = None
    estimate_unavailable: bool | None = None
    basis: Literal["total", "per_hectare", "unknown"] | None = None


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


class CropPreferenceValue(BaseModel):
    crop: str | None = None
    no_preference: bool = False


class SeasonStageValue(BaseModel):
    stage: Literal["not_started", "planning", "soil_preparation", "planting", "growing", "flowering", "fruiting", "harvesting", "post_harvest", "fallow", "other"]
    notes: str | None = None


class PlantingDateValue(BaseModel):
    date: str | None = None
    not_planted: bool | None = None


class UnknownReason(BaseModel):
    reason: Literal["does_not_know", "does_not_remember", "declined", "none"]


RECOVERY_SCHEMAS = {"last_crop": CropValue, "previous_crop": CropValue, "last_harvest_result": HarvestValue, "main_difficulties": DifficultiesValue, "irrigation": IrrigationValue, "mechanization": MechanizationValue, "primary_goal": GoalValue, "next_crop_preference": CropPreferenceValue, "current_season_stage": SeasonStageValue}
RECOVERY_SCHEMAS.update({"current_crop": CropValue, "planting_date": PlantingDateValue})


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
    if patch.field == "current_crop":
        return set(value) == {"crop"} and isinstance(value["crop"], str) and bool(value["crop"].strip())
    if patch.field == "planting_date":
        if not set(value) <= {"date", "not_planted"}:
            return False
        if value.get("not_planted") is True:
            return value.get("date") is None
        raw = value.get("date")
        if not isinstance(raw, str) or not re.fullmatch(r"\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?", raw):
            return False
        try:
            parts = [int(part) for part in raw.split('-')]
            date(parts[0], parts[1] if len(parts)>1 else 1, parts[2] if len(parts)>2 else 1)
            return True
        except ValueError:
            return False
    if patch.field in {"last_crop", "previous_crop"}:
        if not set(value) <= {"crop", "period_label", "no_previous_cultivation", "never_cultivated"}:
            return False
        crop = value.get("crop")
        if isinstance(crop, str) and crop.strip():
            return value.get("never_cultivated") is not True and value.get("no_previous_cultivation") is not True
        return crop is None and (patch.field == "last_crop" and value.get("never_cultivated") is True
            or patch.field == "previous_crop" and value.get("no_previous_cultivation") is True)
    if patch.field == "last_harvest_result":
        return (set(value) <= {"crop", "quantity", "unit", "bag_weight_kg", "qualitative_result", "notes", "financial_amount", "currency", "financial_kind", "estimate_unavailable", "basis"}
            and value.get("qualitative_result") in {None, "good", "average", "poor", "no_harvest", "not_applicable"}
            and (value.get("qualitative_result") != "not_applicable" or value.get("quantity") is None and value.get("financial_amount") is None)
            and (value.get("quantity") is None or isinstance(value["quantity"], (int, float)) and isinstance(value.get("unit"), str) and bool(value["unit"].strip()))
            and (value.get("financial_amount") is None or isinstance(value["financial_amount"], (int, float)) and value.get("currency") in {"BRL", "USD", "EUR"})
            and value.get("financial_kind") in {None, "revenue", "profit", "unknown"}
            and value.get("basis") in {None, "total", "per_hectare", "unknown"}
            and value.get("estimate_unavailable") in {None, True, False}
            and (value.get("qualitative_result") is not None or value.get("quantity") is not None or value.get("financial_amount") is not None or value.get("estimate_unavailable") is True))
    if patch.field == "main_difficulties":
        categories=value.get("categories", []);free_text=value.get("free_text", [])
        return set(value) <= {"categories", "free_text", "explicit_none"} and isinstance(categories, list) and set(categories) <= DIFFICULTIES and isinstance(free_text, list) and bool(categories or free_text or value.get("explicit_none") is True)
    if patch.field == "irrigation":
        return set(value) <= {"water_regime", "irrigation_method", "automated", "notes"} and value.get("water_regime", "unknown") in {"rainfed", "irrigated", "mixed", "unknown"} and value.get("irrigation_method", "unknown") in {"none", "manual", "drip", "sprinkler", "center_pivot", "furrow", "other", "unknown"} and value.get("automated") in {True, False, None} and (value.get("water_regime") not in {None, "unknown"} or value.get("irrigation_method") not in {None, "unknown"})
    if patch.field == "mechanization":
        return set(value) <= {"work_mode", "equipment", "automation_level", "notes"} and value.get("work_mode", "unknown") in {"manual", "mixed", "mechanized", "automated", "unknown"} and value.get("automation_level", "unknown") in {"none", "partial", "high", "unknown"} and isinstance(value.get("equipment", []), list) and (value.get("work_mode") not in {None, "unknown"} or bool(value.get("equipment")))
    if patch.field == "primary_goal":
        return set(value) <= {"category", "description"} and value.get("category") in GOALS
    if patch.field == "next_crop_preference":
        return set(value) <= {"crop", "no_preference"} and (isinstance(value.get("crop"), str) and bool(value["crop"].strip()) and value.get("no_preference") is not True
            or value.get("crop") is None and value.get("no_preference") is True)
    if patch.field == "current_season_stage":
        return set(value) <= {"stage", "notes"} and value.get("stage") in {"not_started", "planning", "soil_preparation", "planting", "growing", "flowering", "fruiting", "harvesting", "post_harvest", "fallow", "other"}
    return bool(value)


@discovery_blueprint.post("/api/interview/extract")
def extract():
    if not _origin_ok():
        return jsonify(error="origin_rejected"), 403
    if request.content_length and request.content_length > 32000:
        return jsonify(error="invalid_request"), 422
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not _uuid(body.get("interview_id")) or not _uuid(body.get("property_id")) or not isinstance(body.get("turn_id"), str) or len(body["turn_id"]) > 100 or not isinstance(body.get("sequence"), int) or body["sequence"] < 1 or body.get("speaker") != "farmer" or not isinstance(body.get("transcript"), str) or not 1 <= len(body["transcript"]) <= 3000 or not isinstance(body.get("assistant_context", ""), str) or len(body.get("assistant_context", "")) > 1000 or not isinstance(body.get("profile_revision"), int) or body["profile_revision"] < 0 or not isinstance(body.get("profile_snapshot"), dict):
        return jsonify(error="invalid_request"), 422
    history = body.get("history", [])
    if (not isinstance(history, list) or len(history) > 40 or any(not isinstance(turn, dict) or set(turn) != {"turn_id", "speaker", "text"} or not isinstance(turn["turn_id"], str) or len(turn["turn_id"]) > 100 or turn["speaker"] not in {"farmer", "agrion"} or not isinstance(turn["text"], str) or len(turn["text"]) > 500 for turn in history)):
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
        contents = json.dumps({"current_turn_id": body["turn_id"], "farmer_transcript": body["transcript"], "previous_assistant_question": context, "ordered_history": history, "profile_snapshot": body["profile_snapshot"]}, ensure_ascii=False)
        instruction = ("Extraia somente fatos agrícolas explicitamente relatados pelo agricultor, em qualquer idioma. "
            "A pergunta anterior e o histórico ordenado esclarecem respostas curtas. Reexamine falas anteriores do agricultor quando um campo ainda está pendente. "
            "Cada patch deve trazer evidence_turn_id da fala do agricultor que contém a evidência; falas do Agrion nunca são evidência. "
            "Se o agricultor disser que nunca cultivou esta área, registre last_crop.never_cultivated=true, previous_crop.no_previous_cultivation=true e last_harvest_result.qualitative_result=not_applicable, todos confirmados com evidência literal da fala. Não invente resultado nem dificuldades de safra passada. "
            "Se a pessoa disser que vai começar agora, registre current_season_stage=not_started ou planning conforme o que foi dito; não presuma uma cultura. "
            "Registre current_crop apenas para a cultura que está plantada atualmente. Registre planting_date na precisão explicitamente informada (ano, mês ou dia); não invente componentes nem converta referência relativa sem data de referência. Se ainda não plantou, registre planting_date.not_planted=true e current_crop unknown com motivo does_not_know, usando a declaração como evidência. "
            "Registre next_crop_preference somente quando houver cultura preferida ou declaração explícita de nenhuma preferência. "
            "Não repita fatos já confirmados, exceto correção explícita. Para colheita, registre resultado qualitativo e também quantidade/unidade ou valor monetário/moeda quando ditos. "
            "Se a pessoa explicitamente não souber estimar depois de informar um resultado qualitativo, use estimate_unavailable=true preservando o resultado. "
            "IDs e categorias permanecem canônicos em inglês. Uma fala pode gerar vários patches. "
            "Copie a evidência literalmente da fala do agricultor. Não invente fatos, datas, medidas ou equipamentos. "
            "Não sei é unknown; estimativa é uncertain. Não altere geometria nem faça recomendações.")
        config = types.GenerateContentConfig(system_instruction=instruction, response_mime_type="application/json", response_schema=GenerationExtraction)
        response = client.models.generate_content(model=model, contents=contents, config=config)
        result = Extraction.model_validate_json(response.text)
        if not result.patches and context and len(body["transcript"]) < 150:
            retry_config = types.GenerateContentConfig(system_instruction=instruction + " A resposta curta do agricultor responde à pergunta anterior. Identifique o campo perguntado e extraia o valor explícito, se houver.", response_mime_type="application/json", response_schema=GenerationExtraction)
            result = Extraction.model_validate_json(client.models.generate_content(model=model, contents=contents, config=retry_config).text)
        evidence = {turn["turn_id"]: turn["text"] for turn in history if turn["speaker"] == "farmer"}
        evidence[body["turn_id"]] = body["transcript"]
        def validated(candidates):
            patches = []
            for patch in candidates:
                if patch.evidence_excerpt and not patch.evidence_turn_id and patch.evidence_excerpt not in body["transcript"]:
                    matches = [turn_id for turn_id, spoken in evidence.items() if patch.evidence_excerpt in spoken]
                    if len(matches) == 1:
                        patch = patch.model_copy(update={"evidence_turn_id": matches[0]})
                if not patch.evidence_excerpt or patch.evidence_excerpt not in evidence.get(patch.evidence_turn_id or body["turn_id"], ""):
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
                    repair_contents = json.dumps({"farmer_transcript": evidence[patch.evidence_turn_id or body["turn_id"]], "previous_assistant_question": context, "field": patch.field}, ensure_ascii=False)
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
            return patches

        patches = validated(result.patches)
        snapshot_fields = body["profile_snapshot"].get("fields", {})
        if not isinstance(snapshot_fields, dict):
            snapshot_fields = {}
        covered = {patch.field for patch in patches if patch.status in {"confirmed", "unknown"}}
        targets = [field for field in ESSENTIAL_FIELDS if isinstance(snapshot_fields.get(field), dict)
            and snapshot_fields[field].get("status") in {"pending", "uncertain"} and field not in covered]
        harvest = next((patch.value for patch in reversed(patches) if patch.field == "last_harvest_result" and patch.value),
            snapshot_fields.get("last_harvest_result", {}).get("value") if isinstance(snapshot_fields.get("last_harvest_result"), dict) else None)
        if ("last_harvest_result" in snapshot_fields and isinstance(harvest, dict)
            and harvest.get("qualitative_result") not in {None, "no_harvest"}
            and harvest.get("quantity") is None and harvest.get("financial_amount") is None
            and harvest.get("estimate_unavailable") is not True and "last_harvest_result" not in targets):
            targets.append("last_harvest_result")
        if targets:
            try:
                audit_config = types.GenerateContentConfig(
                    system_instruction=instruction + " Confira especificamente os campos ainda sem resposta: " + ", ".join(targets) + ". "
                        "Retorne patches somente para fatos explícitos presentes nas falas do agricultor, inclusive falas anteriores. "
                        "Uma fala pode resolver vários campos. Não copie informações do Agrion nem repita um valor já registrado.",
                    response_mime_type="application/json", response_schema=GenerationExtraction,
                )
                audit = Extraction.model_validate_json(client.models.generate_content(
                    model=model, contents=contents, config=audit_config).text)
                patches.extend(patch for patch in validated(audit.patches) if patch.field in targets)
            except Exception as error:
                current_app.logger.warning("Discovery extraction audit failure (%s)", type(error).__name__)
        first_cultivation = next((patch for patch in patches if patch.field == "last_crop"
            and patch.status == "confirmed" and isinstance(patch.value, dict)
            and patch.value.get("never_cultivated") is True), None)
        if first_cultivation:
            patches = [patch for patch in patches if patch.field not in {"previous_crop", "last_harvest_result"}]
            for field, value in (("previous_crop", {"crop": None, "no_previous_cultivation": True}),
                                 ("last_harvest_result", {"qualitative_result": "not_applicable"})):
                patches.append(Patch(field=field, operation="set", value=value, status="confirmed",
                    confidence=first_cultivation.confidence, evidence_excerpt=first_cultivation.evidence_excerpt,
                    evidence_turn_id=first_cultivation.evidence_turn_id))
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
            voice = "Orus"
            if language not in LANGUAGES or not _uuid(first.get("interview_id")) or not _uuid(first.get("property_id")):
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
                    f"Pessoa: {name}. Propriedade: {property_name}. Comece com uma frase curta: apresente-se e pergunte se a pessoa está bem. "
                    "Depois da resposta, explique brevemente o objetivo e convide um relato livre sobre plantio, colheita e dificuldades. Acolha informações agrícolas oferecidas espontaneamente. "
                    "Converse naturalmente, sem roteiro rígido. Conheça última cultura, cultura imediatamente anterior, resultado da colheita, dificuldades, irrigação, mecanização, objetivo, preferência de plantio para a próxima safra e fase da safra atual. "
                    "Pergunte qual é a cultura plantada atualmente e, logo depois, quando foi plantada, caso ainda não tenha sido informado. Se não houver plantio atual, aceite isso e não peça uma data de plantio. "
                    "Se a pessoa nunca cultivou essa área, aceite isso como resposta válida sobre culturas e colheita anteriores; pergunte sobre dificuldades para começar, recursos, preferência e estágio do planejamento. Não invente uma safra passada. "
                    "Use o estado do aplicativo para escolher lacunas; se uma resposta não resolver a pergunta, reformule uma vez, sem insistir. "
                    "Não repita campo marcado unknown. Não invente dados nem recomendações. Seja breve. "
                    "Antes de dizer que a entrevista terminou, chame complete_initial_interview e aguarde autorização. Se recusada, pergunte sobre um campo pendente. "
                    "Se receber CLOSE_REQUESTED, agradeça e despeça-se sem nova pergunta. Nunca cite JSON, ferramentas ou estados internos. "
                    "Após uma resposta de ferramenta recusada, faça uma pergunta ao agricultor antes de chamar outra ferramenta. "
                    "Não faça mais de duas chamadas consecutivas de ferramentas sem falar com o agricultor.")
                speech_config = {"languageCode": language}
                if voice:
                    speech_config["voiceConfig"] = {"prebuiltVoiceConfig": {"voiceName": voice}}
                upstream.send(json.dumps({"setup": {"model": f"projects/{project}/locations/{location}/publishers/google/models/{os.getenv('GEMINI_LIVE_MODEL', 'gemini-3.8-live')}", "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech_config}, "systemInstruction": {"parts": [{"text": instruction}]}, "inputAudioTranscription": {}, "outputAudioTranscription": {}, "tools": [{"functionDeclarations": [{"name": "complete_initial_interview", "description": "Request interview completion when essential facts are resolved or farmer asks to stop", "parameters": {"type": "OBJECT", "properties": {"reason": {"type": "STRING"}}}}, {"name": "get_interview_state", "description": "Read the current validated agricultural checklist before choosing the next question", "parameters": {"type": "OBJECT", "properties": {}}}]}]}}))
                stop = threading.Event()

                def browser_to_vertex():
                    try:
                        while not stop.is_set():
                            message = ws.receive()
                            if message is None:
                                break
                            obj = json.loads(message)
                            if set(obj) == {"interviewState"} and len(message) <= 4096 and os.getenv('GEMINI_LIVE_MODEL', 'gemini-3.8-live') == 'gemini-3.8-live':
                                updated = _live_state_instruction(instruction, obj["interviewState"])
                                if updated:
                                    upstream.send(json.dumps({"contextUpdate": {"systemInstruction": {"parts": [{"text": updated}]}}}))
                            elif set(obj) <= {"realtimeInput", "clientContent", "toolResponse"} and len(message) <= 100000:
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
