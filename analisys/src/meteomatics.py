"""Meteomatics HTTPS/Basic Auth: autenticação só no servidor; sem dados substitutos."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from threading import Lock
import time
from uuid import uuid4

import httpx
from pydantic import SecretStr

from .nasa_power import bounded_env
from .meteomatics_schemas import ForecastRequest, ForecastResponse, PARAMETERS, iso_timestamp

HOST = "https://api.meteomatics.com"
DOCS = "https://www.meteomatics.com/en/api/getting-started/"
RESERVED = {-999, -888, -777, -666}


class ForecastError(Exception):
    def __init__(self, status, code, message, retryable=False, details=None):
        self.status = status
        self.error = {"code": code, "message": message, "retryable": retryable,
                      "details": details or {"provider": "Meteomatics"}}


def utc(value):
    result = iso_timestamp(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timestamp sem fuso.")
    return result.astimezone(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Meteomatics:
    def __init__(self, client=None, *, username=None, password=None, ttl=None, retries=None,
                 clock=time.monotonic, now=lambda: datetime.now(timezone.utc), sleep=time.sleep):
        self._username = SecretStr(username if username is not None else os.getenv("METEOMATICS_USERNAME", ""))
        self._password = SecretStr(password if password is not None else os.getenv("METEOMATICS_PASSWORD", ""))
        self.ttl = ttl if ttl is not None else bounded_env("METEOMATICS_CACHE_TTL_SECONDS", 300, 0, 3600)
        self.capacity = bounded_env("METEOMATICS_CACHE_ENTRIES", 64, 1, 512)
        self.retries = retries if retries is not None else bounded_env("METEOMATICS_MAX_RETRIES", 1, 0, 2)
        self.max_days = bounded_env("METEOMATICS_MAX_FORECAST_DAYS", 7, 1, 16)
        timeout = bounded_env("METEOMATICS_TIMEOUT_SECONDS", 30, 1, 120)
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=5), follow_redirects=False, trust_env=False)
        self.clock, self.now, self.sleep = clock, now, sleep
        self.cache, self.lock = OrderedDict(), Lock()

    @property
    def configured(self):
        return bool(self._username.get_secret_value() and self._password.get_secret_value())

    def close(self):
        self.client.close()

    def forecast(self, payload: ForecastRequest) -> ForecastResponse:
        if not self.configured:
            raise ForecastError(503, "METEOMATICS_CREDENTIALS_MISSING", "Configure METEOMATICS_USERNAME e METEOMATICS_PASSWORD no ambiente do serviço; não envie credenciais no request.")
        now = self.now()
        has_interval = any(PARAMETERS[p][3] != "instantaneous" for p in payload.parameters)
        earliest = payload.start_time - timedelta(hours=payload.step_hours if has_interval else 0)
        if earliest < now or payload.end_time > now + timedelta(days=self.max_days):
            raise ForecastError(422, "FORECAST_PERIOD_INVALID", "Previsão exige instantes e intervalos inteiramente futuros, dentro do limite configurado do serviço.")
        key_data = payload.model_dump(mode="json", exclude={"require_complete"})
        key_data["parameters"] = sorted(payload.parameters)
        key = json.dumps(key_data, sort_keys=True, separators=(",", ":"))
        with self.lock:
            entry = self.cache.get(key)
            hit = entry is not None and entry[0] > self.clock()
            if hit:
                data = deepcopy(entry[1])
                self.cache.move_to_end(key)
            else:
                codes = [PARAMETERS[p][0].format(hours=payload.step_hours) for p in sorted(payload.parameters)]
                times = f"{stamp(payload.start_time)}--{stamp(payload.end_time)}:PT{payload.step_hours}H"
                if payload.start_time == payload.end_time:
                    times = stamp(payload.start_time)
                point = f"{payload.location.latitude},{payload.location.longitude}"
                url = f"{HOST}/{times}/{','.join(codes)}/{point}/json"
                response = self._fetch(url, payload.source)
                try:
                    data = normalize(response.json(), payload, str(response.request.url), self.now(), hashlib.sha256(response.content).hexdigest())
                    data["provenance"][0]["upstream_http_status"] = response.status_code
                    if response.status_code == 206:
                        data["status"] = "partial"
                        data["quality"]["warnings"].append("O provedor sinalizou HTTP 206: cobertura parcial, mesmo que os pontos JSON presentes sejam válidos.")
                    data["cache"] = {"hit": False, "ttl_seconds": self.ttl,
                                     "expires_at": self.now() + timedelta(seconds=self.ttl)}
                    ForecastResponse.model_validate(data)
                except ForecastError:
                    raise
                except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                    raise ForecastError(502, "UPSTREAM_INVALID_RESPONSE", "Resposta Meteomatics inválida ou incompatível; nenhum valor foi estimado como substituto.") from None
                if self.ttl:
                    self.cache[key] = (self.clock() + self.ttl, deepcopy(data))
                    self.cache.move_to_end(key)
                    while len(self.cache) > self.capacity:
                        self.cache.popitem(last=False)
        data["cache"]["hit"] = hit
        data["traceability"].update(request_id=uuid4().hex,
            input_sha256=hashlib.sha256(payload.model_dump_json().encode()).hexdigest())
        data["generated_at"] = self.now()
        if payload.require_complete and data["status"] == "partial":
            raise ForecastError(404, "DATA_INCOMPLETE", "Previsão incompleta; lacunas não foram preenchidas.",
                                details={"missing_times": data["quality"]["missing_times"]})
        return ForecastResponse.model_validate(data)

    def _fetch(self, url, source):
        auth = httpx.BasicAuth(self._username.get_secret_value(), self._password.get_secret_value())
        for attempt in range(self.retries + 1):
            try:
                response = self.client.get(url, params={"source": source}, auth=auth)
            except httpx.TimeoutException:
                error = ForecastError(504, "UPSTREAM_TIMEOUT", "Meteomatics excedeu o tempo de resposta.", True)
            except httpx.RequestError:
                error = ForecastError(503, "UPSTREAM_UNAVAILABLE", "Não foi possível acessar a Meteomatics.", True)
            else:
                status = response.status_code
                if status in {200, 206}:
                    return response
                if status == 401:
                    raise ForecastError(503, "UPSTREAM_AUTHENTICATION_FAILED", "Meteomatics recusou a autenticação do serviço. Verifique as credenciais no ambiente.")
                if status in {402, 403}:
                    raise ForecastError(503, "UPSTREAM_ACCESS_DENIED", "A conta Meteomatics não tem acesso autorizado à consulta; confirme plano, parâmetros, fonte e horizonte.")
                if status == 429:
                    raise ForecastError(429, "UPSTREAM_RATE_LIMITED", "Cota Meteomatics excedida; tente mais tarde.", True)
                if status == 404:
                    raise ForecastError(404, "DATA_UNAVAILABLE", "Previsão Meteomatics indisponível para a consulta.")
                if status == 408:
                    error = ForecastError(504, "UPSTREAM_TIMEOUT", "Meteomatics informou tempo limite excedido.", True)
                elif status >= 500:
                    error = ForecastError(502, "UPSTREAM_UNAVAILABLE", "Meteomatics apresentou falha temporária.", True)
                else:
                    raise ForecastError(502, "UPSTREAM_REJECTED", "Meteomatics recusou a consulta; verifique compatibilidade e acesso contratado.")
            if attempt == self.retries:
                raise error from None
            self.sleep(0.5 * 2 ** attempt)


def normalize(raw, payload, source_url, accessed, digest):
    if raw["status"] != "OK":
        raise ValueError("Provedor informou erro na consulta.")
    provider_time = utc(raw["dateGenerated"])
    count = int((payload.end_time - payload.start_time).total_seconds() / (payload.step_hours * 3600)) + 1
    times = [payload.start_time + timedelta(hours=i * payload.step_hours) for i in range(count)]
    codes = {PARAMETERS[p][0].format(hours=payload.step_hours): p for p in payload.parameters}
    values, metadata, missing = {}, {}, {p: [] for p in payload.parameters}
    for item in raw["data"]:
        code = item["parameter"]
        if code not in codes:
            continue
        coords = item["coordinates"]
        records = values.setdefault(code, {})
        for record in coords[0]["dates"]:
            timestamp = utc(record["date"])
            records[timestamp] = record["value"]
        values[code] = records
    for code, parameter in codes.items():
        _, field, unit, semantics = PARAMETERS[parameter]
        metadata[parameter] = {"provider_parameter": code, "field": field, "unit": unit,
            "temporal_semantics": semantics, "interval_hours": payload.step_hours if semantics != "instantaneous" else None}
    series, valid = [], 0
    ends = {p: None for p in payload.parameters}
    has_interval = any(m["interval_hours"] is not None for m in metadata.values())
    for timestamp in times:
        row = {"valid_time": timestamp, "interval_start": timestamp - timedelta(hours=payload.step_hours) if has_interval else None,
               "missing_parameters": []}
        for code, parameter in codes.items():
            value = values.get(code, {}).get(timestamp)
            if value is None or (isinstance(value, (int, float)) and value in RESERVED):
                value = None
                missing[parameter].append(stamp(timestamp))
                row["missing_parameters"].append(parameter)
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Número inválido.")
                valid += 1
                ends[parameter] = timestamp
            row[metadata[parameter]["field"]] = value
        series.append(row)
    if not valid:
        raise ForecastError(404, "DATA_UNAVAILABLE", "Nenhuma previsão disponível no intervalo solicitado.")
    # O campo 'user' e quaisquer campos adicionais do provedor nunca são repassados.
    return {"status": "partial" if any(missing.values()) else "ok",
        "result": {"location": payload.location, "start_time": payload.start_time, "end_time": payload.end_time,
            "step_hours": payload.step_hours, "points_expected": count, "points_complete": sum(not r["missing_parameters"] for r in series),
            "available_end_by_parameter": ends, "parameters": metadata, "series": series},
        "method": {"assumptions": ["UTC explícito; não há agregação diária, interpolação própria ou conversão implícita de unidades.",
            "Acumulados/extremos referem-se ao intervalo anterior encerrado em valid_time; o intervalo coincide com step_hours.",
            "Valores reservados e dados ausentes são null, sem preenchimento."]},
        "provenance": [{"source_url": source_url, "source_requested": payload.source, "api_version": raw["version"],
            "provider_generated_at": provider_time, "accessed_at": accessed,
            "spatial_resolution": "Depende da fonte/modelo contratado; ponto interpolado pelo provedor não é medição de talhão.",
            "documentation_url": DOCS}],
        "quality": {"missing_times": missing, "warnings": ["Previsão operacional sujeita a atualização e incerteza; não é histórico NASA POWER.",
            "Resposta disponibilizada sem checagem de consistência meteorológica; status indica cobertura, não validação científica.",
            "dateGenerated é geração da resposta do provedor; não foi identificado o horário de inicialização de cada modelo.",
            "Fonte mix pode combinar modelos e interpolar espaço/tempo; não há resolução fixa ou horizonte garantido por este conector."]},
        "limitations": ["A conta deve autorizar parâmetros, fonte, horizonte, volume e redistribuição; licença não foi presumida.",
            "Radiação é fluxo instantâneo em W/m², não energia diária; vento está a 10 m, sem conversão para 2 m.",
            "Precipitação acumulada por intervalo não é taxa mm/h nem previsão de 90 dias.",
            "Não há fallback para NASA histórica nem mistura com indicadores retrospectivos."],
        "traceability": {"request_id": uuid4().hex, "input_sha256": hashlib.sha256(payload.model_dump_json().encode()).hexdigest(),
                         "upstream_sha256": digest}, "generated_at": accessed}
