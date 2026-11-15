"""I02 metadata: caller-supplied retrospective daily depths, never verified NASA data."""
import hashlib
from datetime import datetime, timezone

from src.vendor.intelligence.indicators.rainfall_accumulation import calculate_rainfall_windows
from src.vendor.intelligence.schemas.common import Geography, Method, Provenance, Quality, Traceability
from src.vendor.intelligence.schemas.rainfall import RainfallPeriod, RainfallRequest, RainfallResponse, RainfallResult


def build_rainfall_response(payload: RainfallRequest, request_id: str) -> RainfallResponse:
    windows = calculate_rainfall_windows(payload)
    generated_at = datetime.now(timezone.utc)
    warnings = [
        "Série diária e base temporal declaradas pelo solicitante, sem verificação de origem.",
        "observed_days conta registros válidos fornecidos, não observações de provedor verificadas.",
    ]
    if payload.source_kind == "simulation":
        warnings.append("Série declarada como simulação; totais condicionados a essas entradas.")
    if payload.day_basis == "LST":
        warnings.append("Datas em hora solar local declarada; não convertidas nem rotuladas como UTC.")
    return RainfallResponse(
        result=RainfallResult(
            value=windows[-1].total_mm,
            period=RainfallPeriod(start=windows[-1].start_date, end=windows[-1].end_date,
                                  day_basis=payload.day_basis, timezone="UTC" if payload.day_basis == "UTC" else None),
            geography=Geography(location=payload.location, scope="caller_declared_location" if payload.location else "caller_supplied_series_unspecified_geography"),
            reference_date=payload.reference_date, day_basis=payload.day_basis,
            source_kind=payload.source_kind, source_reference=payload.source_reference, windows=windows,
        ),
        method=Method(name="rolling_sum_precipitation", version="1.0", assumptions=[
            "Cada valor é lâmina acumulada em um único dia civil, em mm, na mesma base temporal declarada.",
            "Janelas retrospectivas de 7/15/30/90 dias, início e fim inclusivos em reference_date.",
            "Cobertura estrita de 90 datas, sem interpolação, conversão de unidades ou de base temporal.",
        ]),
        provenance=[Provenance(provider="caller_supplied", dataset="daily_precipitation", source_url=None,
                               accessed_at=generated_at, spatial_resolution=None, temporal_resolution="daily",
                               license=None, kind="caller_supplied")],
        quality=Quality(kind="scenario" if payload.source_kind == "simulation" else "derived_estimate",
                        warnings=warnings, missing_dates=[]),
        limitations=[
            "Totais retrospectivos; não são forecast futuro nem classificação de risco de estiagem.",
            "O solicitante deve garantir que cada valor acumula apenas um dia, em mm, na base declarada.",
            "Origem e referência declaradas não comprovam observação NASA ou medição no talhão.",
            "accessed_at registra recebimento pelo serviço, não consulta ao provedor original.",
        ],
        traceability=Traceability(request_id=request_id,
                                 input_references=["sha256:" + hashlib.sha256(payload.model_dump_json().encode("utf-8")).hexdigest()]),
        generated_at=generated_at,
    )
