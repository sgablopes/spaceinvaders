"""I01: deterministic daily GDD. No HTTP, lookups, inferred Tbase or gap filling."""
from datetime import timedelta

from src.vendor.intelligence.core.errors import ServiceError
from src.vendor.intelligence.schemas.gdd import GDDDay
from src.vendor.intelligence.schemas.indicators import GDDRequest

MAX_DAYS = 36600


def calculate_daily_gdd(payload: GDDRequest) -> list[GDDDay]:
    """Strict inclusive coverage, sorted output, unrounded float arithmetic."""
    records = payload.daily_temperatures
    if records is None:
        raise ServiceError(503, "DATA_INTEGRATION_PENDING",
                           "Consulta automática pendente: contrato com agrion-data ainda não confirmado.",
                           details={"provider": "agrion-data"})
    expected = (payload.end_date - payload.start_date).days + 1
    if expected > MAX_DAYS:
        raise ServiceError(422, "VALIDATION_ERROR", "O período excede o limite de 36600 dias.")
    seen = set()
    for record in records:
        day = record.date.isoformat()
        if not payload.start_date <= record.date <= payload.end_date:
            raise ServiceError(422, "VALIDATION_ERROR", "Data fora do intervalo solicitado.", details={"date": day})
        if record.date in seen:
            raise ServiceError(422, "VALIDATION_ERROR", "Data duplicada na série diária.", details={"date": day})
        if record.tmin_c > record.tmax_c:
            raise ServiceError(422, "VALIDATION_ERROR", "Temperatura mínima maior que a máxima.", details={"date": day})
        seen.add(record.date)
    missing = [(payload.start_date + timedelta(days=index)).isoformat()
               for index in range(expected) if payload.start_date + timedelta(days=index) not in seen]
    if missing:
        raise ServiceError(422, "VALIDATION_ERROR", "Série incompleta: há dias faltantes no intervalo.",
                           details={"missing_dates": missing, "days_expected": expected, "days_received": len(records)})
    total = 0.0
    series = []
    for record in sorted(records, key=lambda item: item.date):
        mean = (record.tmax_c + record.tmin_c) / 2
        daily = max(0.0, mean - payload.base_temperature_c)
        total += daily
        series.append(GDDDay(date=record.date, tmin_c=record.tmin_c, tmax_c=record.tmax_c,
                             tmean_c=mean, gdd_daily=daily, gdd_cumulative=total,
                             data_kind=record.data_kind, source_reference=record.source_reference))
    return series
