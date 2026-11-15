"""Build the v1 envelope for caller-supplied daily temperatures; never claim verified origin."""
import hashlib
from datetime import datetime, timezone

from src.vendor.intelligence.indicators.gdd import calculate_daily_gdd
from src.vendor.intelligence.schemas.common import Geography, Method, Period, Provenance, Quality, Traceability
from src.vendor.intelligence.schemas.gdd import GDDResponse, GDDResult
from src.vendor.intelligence.schemas.indicators import GDDRequest


def build_gdd_response(payload: GDDRequest, request_id: str) -> GDDResponse:
    series = calculate_daily_gdd(payload)
    generated_at = datetime.now(timezone.utc)
    warnings = ["Temperaturas e natureza dos dados fornecidas pelo solicitante; origem não verificada."]
    kinds = {day.data_kind for day in series}
    if "unspecified" in kinds:
        warnings.append("Há dias sem natureza declarada: não assumir observação histórica.")
    if "forecast" in kinds:
        warnings.append("Inclui forecast declarado pelo solicitante; horizonte e origem não verificados.")
    if "simulation" in kinds:
        warnings.append("Inclui simulação declarada; o total é condicionado a essas entradas.")
    if len(kinds) > 1:
        warnings.append("Série com naturezas distintas por dia; o total não é medição observada.")
    # Fingerprint supports comparison with a retained request without logging or storing raw inputs.
    digest = hashlib.sha256(payload.model_dump_json().encode("utf-8")).hexdigest()
    return GDDResponse(
        result=GDDResult(
            value=series[-1].gdd_cumulative, crop_id=payload.crop_id,
            base_temperature_c=payload.base_temperature_c,
            base_temperature_reference=payload.base_temperature_reference,
            period=Period(start=payload.start_date, end=payload.end_date, timezone=payload.timezone),
            geography=Geography(location=payload.location, scope="caller_declared_location" if payload.location else "caller_supplied_series_unspecified_geography"),
            days_expected=(payload.end_date - payload.start_date).days + 1,
            days_received=len(series), days_valid=len(series), series=series,
        ),
        method=Method(name="simple_average_no_upper_cap", version="1.0", assumptions=[
            "GDD diário = max(0, (Tmax + Tmin) / 2 - Tbase), temperaturas em °C.",
            "Sem cutoff superior ou ajuste de Tmin; nenhuma inferência de Tbase por cultura.",
            "Período inclusivo, cobertura diária completa no fuso declarado; sem conversão de fuso.",
        ]),
        provenance=[Provenance(
            provider="caller_supplied", dataset="daily_temperatures", source_url=None,
            accessed_at=generated_at, spatial_resolution=None, temporal_resolution="daily",
            license=None, kind="caller_supplied",
        )],
        quality=Quality(kind="scenario" if "simulation" in kinds else "derived_estimate",
                        warnings=warnings, missing_dates=[]),
        limitations=[
            "GDD não determina a fase fenológica real sem parâmetros e observações adicionais.",
            "Temperatura-base e método afetam o resultado; referências declaradas não são verificadas.",
            "O período pode ser plantio hipotético; não comprova data observada de plantio.",
            "accessed_at registra recebimento pelo serviço, não consulta ao provedor original.",
        ],
        traceability=Traceability(request_id=request_id, input_references=[f"sha256:{digest}"]),
        generated_at=generated_at,
    )
