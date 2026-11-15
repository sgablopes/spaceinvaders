"""Liga NASA aos serviços anteriores. Nenhuma fórmula agronômica duplicada."""
from datetime import timedelta
from functools import partial
import hashlib

from pydantic import ValidationError

from .nasa_power import NasaError
from .nasa_schemas import DailyRequest
from .analysis_schemas import (
    ClimateResponse, IntegratedGDDResponse, IntegratedRainfallResponse, GDDIndicator, RainfallIndicator,
    WaterResponse, EconomicsResponse,
)
from . import indicators as new_indicators
from .faostat_margin import calculate as faostat_margin
from .indicator_schemas import DrySpellIndicator, ThermalIndicator, ETcIndicator, WaterBalanceIndicator, MarginIndicator
from .vendor.intelligence.core.errors import ServiceError
from .vendor.intelligence.indicators.analysis import analyze, BINDINGS
from .vendor.intelligence.indicators.gdd_service import build_gdd_response
from .vendor.intelligence.indicators.rainfall_service import build_rainfall_response
from .vendor.intelligence.schemas.indicators import GDDRequest
from .vendor.intelligence.schemas.rainfall import RainfallRequest


def query(payload, parameters, *, rain=False):
    if rain:
        if payload.reference_date is None:
            raise ServiceError(503, "LEGACY_AUTOMATIC_PENDING", "Formato legado ambíguo; use reference_date, day_basis e location para consultar NASA.")
        if payload.location is None:
            raise ServiceError(422, "VALIDATION_ERROR", "Location é obrigatório quando daily_precipitation é omitida.")
        start, end, basis = payload.reference_date - timedelta(days=89), payload.reference_date, payload.day_basis
    else:
        if payload.data_kind != "historical":
            raise ServiceError(503, "FORECAST_UNAVAILABLE", "NASA POWER não fornece forecast operacional neste conector.")
        if payload.timezone != "UTC":
            raise ServiceError(422, "VALIDATION_ERROR", "GDD automático requer timezone UTC; não há conversão de LST ou fuso civil.")
        start, end, basis = payload.start_date, payload.end_date, "UTC"
    try:
        return DailyRequest(location=payload.location.model_dump(), start_date=start, end_date=end,
                            parameters=parameters, time_standard=basis, require_complete=True)
    except (ValidationError, AttributeError):
        raise ServiceError(422, "VALIDATION_ERROR", "Consulta automática exige localização válida, histórico disponível e no máximo 366 dias.") from None


def fetch(nasa, request):
    try:
        return nasa.daily(request)
    except NasaError as exc:
        details = exc.error["details"]
        if isinstance(details.get("missing_dates"), dict):
            missing = details["missing_dates"]
            details = {"provider": "NASA POWER", "missing_dates": sorted({day for days in missing.values() for day in days}),
                       "missing_parameters": [parameter for parameter, days in missing.items() if days]}
        raise ServiceError(exc.status, exc.error["code"], exc.error["message"],
                           exc.error["retryable"], details) from None


def source_metadata(computed, original, weather, *, rain=False):
    result = computed.model_dump(mode="json")
    source = weather.provenance[0]
    result["provenance"] = [{"provider": "NASA POWER", "dataset": ",".join(weather.result.parameters),
        "source_url": source.source_url, "accessed_at": source.accessed_at,
        "spatial_resolution": source.spatial_resolution, "temporal_resolution": "daily",
        "license": source.license, "kind": "modeled_estimate"}]
    result["quality"]["kind"] = "derived_estimate"
    result["quality"]["warnings"] = ["Entradas obtidas automaticamente na NASA POWER; estimativas regionais, não medições no talhão.",
        "Procedência e data de acesso referem-se à consulta NASA, inclusive quando a série veio do cache."]
    result["limitations"] = [text for text in result["limitations"] if not text.startswith(("accessed_at", "Origem e referência declaradas"))]
    result["limitations"].append("A disponibilidade é histórica/quase tempo real; não foi produzido forecast.")
    result["result"]["geography"]["scope"] = "regional_grid_estimate_at_requested_location"
    result["traceability"]["input_references"].extend([
        "request-sha256:" + hashlib.sha256(original.model_dump_json().encode()).hexdigest(),
        "nasa-response-sha256:" + weather.traceability.upstream_sha256,
        "nasa-query-sha256:" + weather.traceability.input_sha256,
    ])
    if rain:
        result["result"].update(source_type="nasa_power", source_kind="modeled_estimate")
        result["method"]["assumptions"].append("POWER PRECTOTCORR em mm/day, em passos de um dia: lâmina diária = valor × 1 dia, em mm.")
        return IntegratedRainfallResponse.model_validate(result)
    for day in result["result"]["series"]:
        day["data_kind"] = "modeled_estimate"
    return IntegratedGDDResponse.model_validate(result)


def gdd(nasa, payload, request_id):
    if payload.daily_temperatures is not None:
        return build_gdd_response(payload, request_id)
    weather = fetch(nasa, query(payload, ["T2M_MIN", "T2M_MAX"]))
    manual = payload.model_dump(mode="json")
    manual["daily_temperatures"] = [{"date": r.date.isoformat(), "tmin_c": r.tmin_c, "tmax_c": r.tmax_c,
        "source_reference": "NASA POWER; sha256:" + weather.traceability.upstream_sha256} for r in weather.result.series]
    computed = build_gdd_response(GDDRequest.model_validate(manual), request_id)
    return source_metadata(computed, payload, weather)


def rainfall(nasa, payload, request_id):
    if payload.daily_precipitation is not None:
        return build_rainfall_response(payload, request_id)
    weather = fetch(nasa, query(payload, ["PRECTOTCORR"], rain=True))
    manual = payload.model_dump(mode="json")
    manual["daily_precipitation"] = [{"date": r.date.isoformat(), "precipitation_mm": r.precip_mm_day} for r in weather.result.series]
    manual["source_reference"] = "NASA POWER; sha256:" + weather.traceability.upstream_sha256
    computed = build_rainfall_response(RainfallRequest.model_validate(manual), request_id)
    return source_metadata(computed, payload, weather, rain=True)


def run(group, payload, request_id, nasa, store=None, meteomatics=None, faostat=None):
    # Valida as consultas selecionadas antes de qualquer chamada externa.
    if "I01" in payload.include and payload.inputs.gdd is not None and payload.inputs.gdd.daily_temperatures is None:
        query(payload.inputs.gdd, ["T2M_MIN", "T2M_MAX"])
    if "I02" in payload.include and payload.inputs.rainfall is not None and payload.inputs.rainfall.daily_precipitation is None:
        query(payload.inputs.rainfall, ["PRECTOTCORR"], rain=True)
    bindings = {**BINDINGS, "I01": ("gdd", partial(gdd, nasa), GDDIndicator),
                "I02": ("rainfall", partial(rainfall, nasa), RainfallIndicator),
                "I03": ("dry_spell", partial(new_indicators.dry_spell, nasa, meteomatics), DrySpellIndicator),
                "I05": ("thermal_stress", partial(new_indicators.thermal, nasa, meteomatics, store), ThermalIndicator),
                "I07": ("crop_evapotranspiration", partial(new_indicators.etc, store), ETcIndicator),
                "I08": ("water_balance", partial(new_indicators.balance, nasa, meteomatics, store), WaterBalanceIndicator),
                "I14": ("crop_margin", partial(faostat_margin, faostat), MarginIndicator)}
    models = {"climate": ClimateResponse, "water": WaterResponse, "economics": EconomicsResponse}
    return analyze(group, payload, request_id, bindings=bindings, response_model=models.get(group))
