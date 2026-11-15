"""Open-Meteo pontual; sem extrema horária inferida, preenchimento ou segredo externo."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from threading import Lock
import time
from uuid import uuid4

import httpx

from .meteomatics import ForecastError, stamp
from .meteomatics_schemas import PARAMETERS
from .nasa_power import bounded_env
from .weather_schemas import WeatherResponse

HOST = "https://api.open-meteo.com/v1/forecast"
DOCS = "https://open-meteo.com/en/docs"
HOURLY = {"temperature": ("temperature_2m", "°C"),
    "precipitation": ("precipitation", "mm"),
    "relative_humidity": ("relative_humidity_2m", "%"),
    "wind_speed": ("wind_speed_10m", "m/s"),
    "solar_radiation": ("shortwave_radiation_instant", "W/m²")}
DAILY = {"temperature_mean": "temperature_2m_mean", "temperature_min": "temperature_2m_min",
         "temperature_max": "temperature_2m_max"}


def validate_query(payload, now, max_days):
    has_interval = any(PARAMETERS[p][3] != "instantaneous" for p in payload.parameters)
    earliest = payload.start_time - timedelta(hours=payload.step_hours if has_interval else 0)
    if earliest < now or payload.end_time > now + timedelta(days=max_days):
        raise ForecastError(422, "FORECAST_PERIOD_INVALID", "Previsão exige intervalos futuros dentro do horizonte configurado.")
    if payload.source != "mix":
        raise ForecastError(503, "OPEN_METEO_SOURCE_UNSUPPORTED", "Open-Meteo aceita somente seleção automática mix neste conector; fonte explícita não foi substituída.")
    if any(p in DAILY for p in payload.parameters) and (payload.step_hours != 24 or payload.start_time.hour or payload.end_time.hour):
        raise ForecastError(503, "OPEN_METEO_PARAMETER_UNSUPPORTED", "Média/mínima/máxima térmicas Open-Meteo exigem dias completos UTC, step_hours=24 e validade à meia-noite.")


class OpenMeteo:
    def __init__(self, client=None, *, now=lambda: datetime.now(timezone.utc), clock=time.monotonic):
        self.now, self.clock = now, clock
        self.max_days = bounded_env("OPEN_METEO_MAX_FORECAST_DAYS", 7, 1, 16)
        self.ttl = bounded_env("OPEN_METEO_CACHE_TTL_SECONDS", 300, 0, 3600)
        self.capacity = bounded_env("OPEN_METEO_CACHE_ENTRIES", 64, 1, 512)
        self.client = client or httpx.Client(timeout=httpx.Timeout(bounded_env("OPEN_METEO_TIMEOUT_SECONDS", 30, 1, 120), connect=5),
            follow_redirects=False, trust_env=False)
        self.cache, self.lock = OrderedDict(), Lock()

    def close(self):
        self.client.close()

    def forecast(self, payload):
        validate_query(payload, self.now(), self.max_days)
        key = payload.model_dump(mode="json", exclude={"require_complete"})
        key["parameters"] = sorted(payload.parameters)
        key = json.dumps(key, sort_keys=True)
        with self.lock:
            entry = self.cache.get(key)
            hit = entry is not None and entry[0] > self.clock()
            if hit:
                data = deepcopy(entry[1])
                self.cache.move_to_end(key)
            else:
                params = query_parameters(payload)
                try:
                    upstream = self.client.get(HOST, params=params)
                except httpx.TimeoutException:
                    raise ForecastError(504, "UPSTREAM_TIMEOUT", "Open-Meteo excedeu o tempo de resposta.", True) from None
                except httpx.RequestError:
                    raise ForecastError(503, "UPSTREAM_UNAVAILABLE", "Não foi possível acessar Open-Meteo.", True) from None
                if upstream.status_code != 200:
                    code = "UPSTREAM_RATE_LIMITED" if upstream.status_code == 429 else "UPSTREAM_UNAVAILABLE" if upstream.status_code >= 500 else "UPSTREAM_REJECTED"
                    raise ForecastError(429 if upstream.status_code == 429 else 502, code, "Open-Meteo não disponibilizou a consulta.", upstream.status_code >= 500 or upstream.status_code == 429)
                try:
                    data = normalize(upstream.json(), payload, str(upstream.request.url), self.now(), hashlib.sha256(upstream.content).hexdigest())
                    data["cache"] = {"hit": False, "ttl_seconds": self.ttl, "expires_at": self.now() + timedelta(seconds=self.ttl)}
                    WeatherResponse.model_validate(data)
                except ForecastError:
                    raise
                except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                    raise ForecastError(502, "UPSTREAM_INVALID_RESPONSE", "Resposta Open-Meteo incompatível; nenhum valor foi substituído.") from None
                if self.ttl:
                    self.cache[key] = (self.clock() + self.ttl, deepcopy(data))
                    self.cache.move_to_end(key)
                    while len(self.cache) > self.capacity:
                        self.cache.popitem(last=False)
        data["cache"]["hit"] = hit
        data["generated_at"] = self.now()
        data["traceability"].update(request_id=uuid4().hex, input_sha256=hashlib.sha256(payload.model_dump_json().encode()).hexdigest())
        if payload.require_complete and data["status"] == "partial":
            raise ForecastError(404, "DATA_INCOMPLETE", "Previsão Open-Meteo incompleta; nenhum intervalo foi preenchido.")
        return WeatherResponse.model_validate(data)


def query_parameters(payload):
    params = {"latitude": payload.location.latitude, "longitude": payload.location.longitude,
        "timezone": "GMT", "timeformat": "unixtime", "temperature_unit": "celsius",
        "wind_speed_unit": "ms", "precipitation_unit": "mm", "cell_selection": "nearest"}
    hourly = [HOURLY[p][0] for p in payload.parameters if p in HOURLY]
    daily = [DAILY[p] for p in payload.parameters if p in DAILY]
    if hourly:
        first = payload.start_time - timedelta(hours=payload.step_hours - 1) if "precipitation" in payload.parameters else payload.start_time
        params.update(hourly=",".join(hourly), start_hour=first.strftime("%Y-%m-%dT%H:%M"), end_hour=payload.end_time.strftime("%Y-%m-%dT%H:%M"))
    if daily:
        params.update(daily=",".join(daily), start_date=(payload.start_time - timedelta(days=1)).date().isoformat(),
                      end_date=(payload.end_time - timedelta(days=1)).date().isoformat())
    return params


def records(raw, key, variables):
    if not variables:
        return {}
    block = raw[key]
    times = block["time"]
    dates = [datetime.fromtimestamp(t, timezone.utc) for t in times]
    result = {}
    for parameter, variable, unit in variables:
        result[parameter] = {}
        for index, d in enumerate(dates):
            value = block[variable][index] if index < len(block[variable]) else None
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Valor numérico incompatível.")
            result[parameter][d] = value
    return result


def normalize(raw, payload, url, accessed, digest):
    if raw.get("error"):
        raise ValueError("Provedor informou erro na consulta.")
    grid = [raw["latitude"], raw["longitude"], raw["elevation"]]
    hourly = records(raw, "hourly", [(p, *HOURLY[p]) for p in payload.parameters if p in HOURLY])
    daily = records(raw, "daily", [(p, DAILY[p], "°C") for p in payload.parameters if p in DAILY])
    count = int((payload.end_time - payload.start_time).total_seconds() / (3600 * payload.step_hours)) + 1
    missing, ends, metadata = {p: [] for p in payload.parameters}, {p: None for p in payload.parameters}, {}
    for p in payload.parameters:
        _, field, unit, semantics = PARAMETERS[p]
        block = "daily" if p in DAILY else "hourly"
        variable = DAILY[p] if p in DAILY else HOURLY[p][0]
        source_unit = raw[block + "_units"][variable]
        unit = {"°C": "C"}.get(source_unit, source_unit)
        metadata[p] = {"provider_parameter": DAILY[p] if p in DAILY else HOURLY[p][0], "field": field, "unit": unit,
            "temporal_semantics": semantics, "interval_hours": payload.step_hours if semantics != "instantaneous" else None}
    series, valid = [], 0
    for i in range(count):
        t = payload.start_time + timedelta(hours=i * payload.step_hours)
        row = {"valid_time": t, "interval_start": t - timedelta(hours=payload.step_hours) if any(m["interval_hours"] for m in metadata.values()) else None, "missing_parameters": []}
        for p in payload.parameters:
            if p in DAILY:
                value = daily[p].get(t - timedelta(days=1))
            elif p == "precipitation":
                values = [hourly[p].get(t - timedelta(hours=j)) for j in range(payload.step_hours)]
                value = math.fsum(values) if all(v is not None for v in values) else None
            else:
                value = hourly[p].get(t)
            if value is None:
                row["missing_parameters"].append(p)
                missing[p].append(stamp(t))
            else:
                valid += 1
                ends[p] = t
            row[metadata[p]["field"]] = value
        series.append(row)
    if not valid:
        raise ForecastError(404, "DATA_UNAVAILABLE", "Open-Meteo sem valores no intervalo solicitado.")
    return {"operation": "get_weather_forecast", "provider_used": "Open-Meteo", "provider_requested": "open_meteo",
        "status": "partial" if any(missing.values()) else "ok",
        "result": {"location": payload.location, "start_time": payload.start_time, "end_time": payload.end_time,
            "step_hours": payload.step_hours, "points_expected": count, "points_complete": sum(not r["missing_parameters"] for r in series),
            "parameters": metadata, "available_end_by_parameter": ends, "series": series},
        "method": {"name": "open_meteo_forecast_normalization", "assumptions": [
            "Instantâneos horários preservados; radiação usa shortwave_radiation_instant, não média horária.",
            "Precipitação soma todas as horas anteriores do intervalo; uma hora ausente invalida o acumulado.",
            "Extremos/média térmicos são produtos diários UTC do provedor, associados ao encerramento D+1 00:00."]},
        "provenance": [{"provider": "Open-Meteo", "source_url": url, "source_requested": "best_match",
            "api_version": "v1", "accessed_at": accessed, "spatial_resolution": "Célula nearest do conjunto best_match; resolução depende do modelo, com ajuste de altitude pelo provedor.",
            "documentation_url": DOCS, "license": "CC BY 4.0; atribuir Open-Meteo e provedores. API gratuita somente para uso não comercial.",
            "grid_latitude": grid[0], "grid_longitude": grid[1], "elevation_m": grid[2],
            "source_timezone": raw.get("timezone"), "source_utc_offset_seconds": raw.get("utc_offset_seconds")}],
        "quality": {"missing_times": missing, "warnings": [
            "Resposta disponibilizada sem checagem de consistência meteorológica; status indica cobertura, não validação científica.",
            "Previsão operacional, não observação de talhão. Modelo/ciclo exatos não são identificados por best_match.",
            "Extremos diários Open-Meteo agregam valores horários; não garantem equivalência aos extremos Meteomatics.",
            "generationtime_ms é duração de processamento, não instante de emissão da previsão."]},
        "limitations": ["Disponibilidade, horizonte e cota não são garantidos; fallback também pode falhar.",
            "API pública não comercial: limites 10000/dia, 5000/hora, 600/minuto; uso comercial requer contratação própria.",
            "Não calcula ETo nem converte vento 10 m para 2 m; radiação instantânea não é energia diária.",
            "Não combina valores entre provedores nem usa NASA histórica para substituir previsão."],
        "traceability": {"request_id": uuid4().hex, "input_sha256": hashlib.sha256(payload.model_dump_json().encode()).hexdigest(), "upstream_sha256": digest},
        "generated_at": accessed}
