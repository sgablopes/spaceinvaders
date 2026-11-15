"""Adaptação de entrada, sem copiar fórmulas ou alterar o consumidor existente."""
from datetime import timedelta

from .nasa_schemas import DailyResponse


def climate_request(data: DailyResponse, crop_id: str, base_temperature_c: float) -> dict:
    """Prepara I01/I02 manuais do contrato existente; procedência real permanece na resposta INT."""
    result = data.result
    if result.period.time_standard != "UTC":
        raise ValueError("I01 existente exige fuso IANA; esta ponte aceita somente UTC, sem converter LST.")
    required = {"T2M_MIN", "T2M_MAX", "PRECTOTCORR"}
    if not required.issubset(result.parameters):
        raise ValueError("Selecione Tmin, Tmax e precipitação na API de dados.")
    if any(result.parameters[p].unit != ("mm/day" if p == "PRECTOTCORR" else "C") for p in required):
        raise ValueError("Unidade incompatível com os cálculos existentes.")
    expected = [result.period.start + timedelta(days=i) for i in range((result.period.end - result.period.start).days + 1)]
    if [r.date for r in result.series] != expected:
        raise ValueError("A série deve estar completa, ordenada e sem datas duplicadas.")
    if len(result.series) < 90:
        raise ValueError("I02 requer 90 dias; consulte um intervalo com pelo menos 90 dias.")
    if any(r.tmin_c is None or r.tmax_c is None for r in result.series):
        raise ValueError("GDD não pode receber lacunas de temperatura.")
    if any(r.precip_mm_day is None for r in result.series[-90:]):
        raise ValueError("Chuva acumulada não pode receber lacunas nos últimos 90 dias.")
    # A variável POWER é mm/day no passo de um dia: lâmina de cada dia = valor × 1 dia.
    # Não se aplica esta equivalência a acumulados multidiários ou a dados horários.
    reference = "NASA POWER; upstream_sha256:" + data.traceability.upstream_sha256
    return {"include": ["I01", "I02"], "inputs": {
        "gdd": {"crop_id": crop_id, "location": result.location.model_dump(),
                "start_date": result.period.start.isoformat(), "end_date": result.period.end.isoformat(),
                "timezone": "UTC", "base_temperature_c": base_temperature_c,
                "daily_temperatures": [{"date": r.date.isoformat(), "tmin_c": r.tmin_c, "tmax_c": r.tmax_c,
                                        "data_kind": "unspecified", "source_reference": reference} for r in result.series]},
        "rainfall": {"reference_date": result.period.end.isoformat(), "day_basis": "UTC",
                     "location": result.location.model_dump(), "source_kind": "declared", "source_reference": reference,
                     "daily_precipitation": [{"date": r.date.isoformat(), "precipitation_mm": r.precip_mm_day} for r in result.series[-90:]]}}}
