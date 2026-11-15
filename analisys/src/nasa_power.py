"""Conector NASA POWER sob demanda; nenhuma fórmula IND ou fallback de dados."""
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

from .nasa_schemas import DailyRequest, DailyResponse, PARAMETERS

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
DOCS = "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"


class NasaError(Exception):
    def __init__(self, status, code, message, retryable=False, details=None):
        self.status = status
        self.error = {"code": code, "message": message, "retryable": retryable, "details": details or {"provider": "NASA POWER"}}


def bounded_env(name, default, low, high):
    value = int(os.getenv(name, str(default)))
    if not low <= value <= high:
        raise ValueError(f"{name} deve estar entre {low} e {high}.")
    return value


class NasaPower:
    def __init__(self, client=None, ttl=None, capacity=None, retries=None, sleep=time.sleep, clock=time.monotonic):
        self.ttl = ttl if ttl is not None else bounded_env("NASA_POWER_CACHE_TTL_SECONDS", 300, 0, 86400)
        self.capacity = capacity if capacity is not None else bounded_env("NASA_POWER_CACHE_ENTRIES", 128, 1, 1024)
        self.retries = retries if retries is not None else bounded_env("NASA_POWER_MAX_RETRIES", 1, 0, 2)
        timeout = bounded_env("NASA_POWER_TIMEOUT_SECONDS", 40, 1, 120)
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=5), follow_redirects=False, trust_env=False)
        self.sleep, self.clock = sleep, clock
        self.cache = OrderedDict()
        self.lock = Lock()

    def close(self):
        self.client.close()

    def daily(self, payload: DailyRequest) -> DailyResponse:
        key_data = payload.model_dump(mode="json", exclude={"require_complete"})
        key_data["parameters"] = sorted(payload.parameters)
        key = json.dumps(key_data, sort_keys=True, separators=(",", ":"))
        # Serialização de chamadas evita rajadas ao provedor e duplicação concorrente da mesma consulta.
        with self.lock:
            entry = self.cache.get(key)
            hit = entry is not None and entry[0] > self.clock()
            if hit:
                data = deepcopy(entry[1])
                self.cache.move_to_end(key)
            else:
                params = {"parameters": ",".join(sorted(payload.parameters)), "community": "AG",
                          "latitude": payload.location.latitude, "longitude": payload.location.longitude,
                          "start": payload.start_date.strftime("%Y%m%d"), "end": payload.end_date.strftime("%Y%m%d"),
                          "format": "JSON", "time-standard": payload.time_standard}
                response = self._fetch(params)
                try:
                    raw = response.json()
                    data = normalize(raw, payload, str(response.request.url), hashlib.sha256(response.content).hexdigest())
                except NasaError:
                    raise
                except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
                    raise NasaError(502, "UPSTREAM_INVALID_RESPONSE", "Resposta NASA POWER inválida ou incompatível com o contrato.") from None
                data["cache"] = {"hit": False, "ttl_seconds": self.ttl,
                                 "expires_at": datetime.now(timezone.utc) + timedelta(seconds=self.ttl)}
                try:
                    DailyResponse.model_validate(data)
                except ValueError:
                    raise NasaError(502, "UPSTREAM_INVALID_RESPONSE", "Metadados NASA POWER inválidos.") from None
                if self.ttl:
                    self.cache[key] = (self.clock() + self.ttl, deepcopy(data))
                    self.cache.move_to_end(key)
                    while len(self.cache) > self.capacity:
                        self.cache.popitem(last=False)
        data["cache"]["hit"] = hit
        data["generated_at"] = datetime.now(timezone.utc)
        data["traceability"]["request_id"] = uuid4().hex
        data["traceability"]["input_sha256"] = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
        if payload.require_complete and data["status"] == "partial":
            raise NasaError(404, "DATA_INCOMPLETE", "Série NASA incompleta; não foi preenchida nem interpolada.",
                            details={"missing_dates": data["quality"]["missing_dates"]})
        return DailyResponse.model_validate(data)

    def _fetch(self, params):
        for attempt in range(self.retries + 1):
            try:
                response = self.client.get(URL, params=params)
            except httpx.TimeoutException:
                error = NasaError(504, "UPSTREAM_TIMEOUT", "NASA POWER excedeu o tempo de resposta.", True)
            except httpx.RequestError:
                error = NasaError(503, "UPSTREAM_UNAVAILABLE", "NASA POWER está inacessível.", True)
            else:
                if response.status_code == 200:
                    return response
                if response.status_code == 429:
                    # Não repetir imediatamente após indicação de cota.
                    raise NasaError(429, "UPSTREAM_RATE_LIMITED", "Cota NASA POWER excedida; tente mais tarde.", True)
                if response.status_code == 404:
                    raise NasaError(404, "DATA_UNAVAILABLE", "Dados NASA POWER indisponíveis para esta consulta.")
                if response.status_code >= 500:
                    error = NasaError(502, "UPSTREAM_UNAVAILABLE", "Falha temporária na NASA POWER.", True)
                else:
                    raise NasaError(502, "UPSTREAM_REJECTED", "NASA POWER recusou a consulta; nenhum dado foi substituído.")
            if attempt == self.retries:
                raise error from None
            self.sleep(0.5 * (2 ** attempt))


def normalize(raw, payload, source_url, upstream_hash):
    header = raw["header"]
    if header["time_standard"] != payload.time_standard:
        raise ValueError("Base temporal incompatível.")
    if str(header["start"]) != payload.start_date.strftime("%Y%m%d") or str(header["end"]) != payload.end_date.strftime("%Y%m%d"):
        raise ValueError("Período incompatível.")
    geometry = raw["geometry"]
    coordinates = geometry["coordinates"]
    if geometry["type"] != "Point" or not math.isclose(coordinates[0], payload.location.longitude, abs_tol=1e-6) or not math.isclose(coordinates[1], payload.location.latitude, abs_tol=1e-6):
        raise ValueError("Localização incompatível.")
    fill = header["fill_value"]
    if isinstance(fill, bool) or not isinstance(fill, (int, float)) or not math.isfinite(fill) or fill >= 0:
        raise ValueError("Sentinel da fonte inválido.")
    parameters = raw["properties"]["parameter"]
    count = (payload.end_date - payload.start_date).days + 1
    dates = [payload.start_date + timedelta(days=i) for i in range(count)]
    expected_keys = {d.strftime("%Y%m%d") for d in dates}
    metadata, missing = {}, {p: [] for p in payload.parameters}
    for parameter in payload.parameters:
        field, unit = PARAMETERS[parameter]
        original = raw["parameters"][parameter]
        if original["units"] != unit:
            raise ValueError("Unidade incompatível.")
        if not isinstance(parameters[parameter], dict) or not set(parameters[parameter]).issubset(expected_keys):
            raise ValueError("Datas incompatíveis.")
        metadata[parameter] = {"field": field, "unit": unit, "source_unit": original["units"], "long_name": original["longname"]}
    series, valid_values = [], 0
    for day in dates:
        row = {"date": day, "missing_parameters": []}
        for parameter in payload.parameters:
            field, _ = PARAMETERS[parameter]
            value = parameters[parameter].get(day.strftime("%Y%m%d"))
            if value is None or value == fill or value == -999:
                value = None
                missing[parameter].append(day.isoformat())
                row["missing_parameters"].append(parameter)
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Número inválido.")
                if (parameter.startswith("T2M") and not -100 <= value <= 100) or (parameter == "RH2M" and not 0 <= value <= 100) or (parameter in {"PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "WS2M"} and value < 0) or (parameter == "PS" and not 0 < value <= 120):
                    raise ValueError("Valor fora dos limites de sanidade.")
                valid_values += 1
            row[field] = value
        if row.get("tmin_c") is not None and row.get("tmax_c") is not None and row["tmin_c"] > row["tmax_c"]:
            raise ValueError("Tmin maior que Tmax.")
        series.append(row)
    if not valid_values:
        raise NasaError(404, "DATA_UNAVAILABLE", "NASA POWER não retornou valores disponíveis no intervalo.")
    accessed = datetime.now(timezone.utc)
    return {"status": "partial" if any(missing.values()) else "ok",
            "result": {"location": payload.location, "period": {"start": payload.start_date, "end": payload.end_date,
                       "time_standard": payload.time_standard, "timezone": "UTC" if payload.time_standard == "UTC" else None},
                       "parameters": metadata, "days_expected": count,
                       "days_complete": sum(not r["missing_parameters"] for r in series), "series": series},
            "method": {"assumptions": ["Leitura diária comunidade AG, sem interpolação ou conversão entre UTC/LST.",
                                       "Unidades validadas contra o contrato; sem cálculo de ETo ou indicadores.",
                                       "Sentinel da fonte, -999, null ou dia ausente são representados como null."]},
            "provenance": [{"dataset": header["sources"], "source_url": source_url, "accessed_at": accessed,
                            "api_version": header.get("api", {}).get("version"), "source_geometry": geometry,
                            "spatial_resolution": "Resolução nativa por produto NASA POWER; ponto consultado não é medição de talhão.",
                            "documentation_url": DOCS}],
            "quality": {"missing_dates": missing, "warnings": ["Estimativa regional; não observação medida no talhão.",
                        "Disponibilidade recente varia por parâmetro; histórico/quase tempo real não é forecast.",
                        "Campos de parâmetros não selecionados ficam null; consulte result.parameters para distingui-los de lacunas."]},
            "limitations": ["Sem previsão meteorológica, ETo calculada ou recomendação agronômica.",
                             "LST não é um fuso IANA e não foi convertido para UTC.",
                             "Licença não foi inferida; confira as condições de uso NASA POWER antes de redistribuição."],
            "traceability": {"upstream_sha256": upstream_hash, "request_id": uuid4().hex,
                             "input_sha256": hashlib.sha256(payload.model_dump_json().encode()).hexdigest()},
            "generated_at": accessed}
