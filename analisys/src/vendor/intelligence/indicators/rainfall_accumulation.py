"""Strict retrospective I02 sums; no HTTP, interpolation, forecast or fabricated input."""
import math
from datetime import timedelta

from src.vendor.intelligence.core.errors import ServiceError
from src.vendor.intelligence.schemas.rainfall import RainfallRequest, RainfallWindow

WINDOWS = (7, 15, 30, 90)


def calculate_rainfall_windows(payload: RainfallRequest) -> list[RainfallWindow]:
    if payload.daily_precipitation is None:
        raise ServiceError(503, "DATA_INTEGRATION_PENDING",
                           "Consulta automática pendente: contrato real com agrion-data ainda não validado.",
                           details={"provider": "agrion-data"})
    reference = payload.reference_date
    start = reference - timedelta(days=89)
    by_date = {}
    for record in payload.daily_precipitation:
        if record.date > reference:
            raise ServiceError(422, "VALIDATION_ERROR", "Data posterior à referência retrospectiva.",
                               details={"date": record.date.isoformat()})
        if record.date < start:
            raise ServiceError(422, "VALIDATION_ERROR", "Data anterior à janela de 90 dias.",
                               details={"date": record.date.isoformat()})
        if record.date in by_date:
            raise ServiceError(422, "VALIDATION_ERROR", "Data duplicada na precipitação diária.",
                               details={"date": record.date.isoformat()})
        by_date[record.date] = record.precipitation_mm
    missing = [(start + timedelta(days=index)).isoformat() for index in range(90)
               if start + timedelta(days=index) not in by_date]
    if missing:
        raise ServiceError(422, "VALIDATION_ERROR", "Série incompleta: são exigidos 90 dias consecutivos.",
                           details={"missing_dates": missing, "days_expected": 90, "days_received": len(by_date)})
    windows = []
    for size in WINDOWS:
        window_start = reference - timedelta(days=size - 1)
        try:
            total = math.fsum(by_date[window_start + timedelta(days=index)] for index in range(size))
        except OverflowError:
            raise ServiceError(422, "VALIDATION_ERROR", "Total de precipitação excede a representação numérica finita.") from None
        windows.append(RainfallWindow(window_days=size, start_date=window_start, end_date=reference,
                                      total_mm=total, observed_days=size, expected_days=size))
    return windows
