"""Séries completas para novos indicadores; NASA histórica ou intervalos Meteomatics de 24 h."""
from datetime import datetime, time, timedelta, timezone

from pydantic import ValidationError

from .nasa_schemas import DailyRequest
from .nasa_power import NasaError
from .meteomatics import ForecastError
from .meteomatics_schemas import ForecastRequest
from .vendor.intelligence.core.errors import ServiceError


def full_series(payload, records):
    count = (payload.end_date - payload.start_date).days + 1
    if payload.timezone != "UTC" or not 1 <= count <= 36600:
        raise ServiceError(422, "VALIDATION_ERROR", "Novos indicadores exigem dias UTC e até 36600 dias no modo manual.")
    by_date = {}
    for record in records:
        if record.date in by_date or not payload.start_date <= record.date <= payload.end_date:
            raise ServiceError(422, "VALIDATION_ERROR", "Data duplicada ou fora do intervalo.")
        by_date[record.date] = record
    missing = [(payload.start_date + timedelta(days=i)).isoformat() for i in range(count) if payload.start_date + timedelta(days=i) not in by_date]
    if missing:
        raise ServiceError(422, "VALIDATION_ERROR", "Série diária incompleta; nenhum dia foi preenchido.", details={"missing_dates": missing})
    return [by_date[d] for d in sorted(by_date)]


def supplied_source(reference="daily_values"):
    return {"provider": "caller_supplied", "dataset": reference[:200], "source_url": None,
            "accessed_at": datetime.now(timezone.utc), "spatial_resolution": None,
            "temporal_resolution": "daily", "license": None, "kind": "caller_supplied"}


def weather(payload, nasa, meteomatics, *, temperature=False):
    if payload.location is None or payload.timezone != "UTC":
        raise ServiceError(422, "VALIDATION_ERROR", "Consulta automática exige localização e dias UTC.")
    try:
        if payload.data_kind == "forecast":
            query = ForecastRequest(location=payload.location.model_dump(),
                start_time=datetime.combine(payload.start_date + timedelta(days=1), time(), timezone.utc),
                end_time=datetime.combine(payload.end_date + timedelta(days=1), time(), timezone.utc), step_hours=24,
                parameters=["temperature_min", "temperature_max"] if temperature else ["precipitation"], require_complete=True)
            data = meteomatics.forecast(query)
            rows = []
            for row in data.result.series:
                if row.valid_time.hour != 0 or row.valid_time.minute != 0 or row.interval_start != row.valid_time - timedelta(days=1):
                    raise ServiceError(502, "UPSTREAM_INVALID_RESPONSE", "Forecast não corresponde a dias UTC completos.")
                date = row.interval_start.date()
                if temperature:
                    rows.append({"date": date, "tmin_c": row.temperature_min_c, "tmax_c": row.temperature_max_c})
                else:
                    rows.append({"date": date, "precipitation_mm": row.precipitation_mm})
            p = data.provenance[0]
            provenance = {"provider": p.provider, "dataset": ",".join(data.result.parameters), "source_url": p.source_url,
                "accessed_at": p.accessed_at, "spatial_resolution": p.spatial_resolution, "temporal_resolution": "daily_24h_UTC",
                "license": p.license, "kind": "operational_forecast",
                "fallback_used": getattr(data, "fallback_used", False),
                "fallback_reasons": [f.code for f in getattr(data, "provider_failures", [])],
                "forecast_basis": "daily_aggregated_hourly_values" if p.provider == "Open-Meteo" else "provider_24h_interval_product"}
        else:
            query = DailyRequest(location=payload.location.model_dump(), start_date=payload.start_date, end_date=payload.end_date,
                parameters=["T2M_MIN", "T2M_MAX"] if temperature else ["PRECTOTCORR"], time_standard="UTC", require_complete=True)
            data = nasa.daily(query)
            rows = [{"date": r.date, **({"tmin_c": r.tmin_c, "tmax_c": r.tmax_c} if temperature else {"precipitation_mm": r.precip_mm_day})}
                    for r in data.result.series]
            p = data.provenance[0]
            provenance = {"provider": "NASA POWER", "dataset": ",".join(data.result.parameters), "source_url": p.source_url,
                "accessed_at": p.accessed_at, "spatial_resolution": p.spatial_resolution, "temporal_resolution": "daily",
                "license": p.license, "kind": "modeled_estimate"}
        if any(any(v is None for k, v in row.items() if k != "date") for row in rows):
            raise ServiceError(404, "DATA_INCOMPLETE", "Variável diária ausente; não foi substituída por zero.")
        return rows, provenance, data.traceability.upstream_sha256
    except (NasaError, ForecastError) as exc:
        raise ServiceError(exc.status, exc.error["code"], exc.error["message"], exc.error["retryable"], {"provider": "automatic_forecast" if payload.data_kind == "forecast" else "NASA POWER"}) from None
    except ValidationError:
        raise ServiceError(422, "VALIDATION_ERROR", "Período ou consulta incompatível com o provedor; sem conversão implícita.") from None
