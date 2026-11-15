"""Orchestration only: reuse indicator services, never copy formulas or call legacy HTTP."""
import hashlib
from datetime import datetime, timezone

from src.vendor.intelligence.core.errors import ServiceError
from src.vendor.intelligence.indicators.gdd_service import build_gdd_response
from src.vendor.intelligence.indicators.rainfall_service import build_rainfall_response
from src.vendor.intelligence.schemas.analysis import (
    ClimateResponse, WaterResponse, AgronomyResponse, EconomicsResponse,
    GDDAnalysisIndicator, RainfallAnalysisIndicator, UnavailableIndicator,
)
from src.vendor.intelligence.schemas.common import ErrorInfo, Method, Quality, Traceability

# A new calculation is added here only after its own implementation and validation.
BINDINGS = {
    "I01": ("gdd", build_gdd_response, GDDAnalysisIndicator),
    "I02": ("rainfall", build_rainfall_response, RainfallAnalysisIndicator),
    "I03": ("dry_spell", None, None),
    "I05": ("thermal_stress", None, None),
    "I07": ("crop_evapotranspiration", None, None),
    "I08": ("water_balance", None, None),
    "I09": ("climate_suitability", None, None),
    "I10": ("crop_succession", None, None),
    "I11": ("planting_risk", None, None),
    "I13": ("yield_scenario", None, None),
    "I14": ("crop_margin", None, None),
}
RESPONSE_MODELS = {"climate": ClimateResponse, "water": WaterResponse,
                   "agronomy": AgronomyResponse, "economics": EconomicsResponse}


def analyze(group: str, payload, request_id: str, *, bindings=None, response_model=None):
    bindings = BINDINGS if bindings is None else bindings
    missing = [f"inputs.{bindings[identifier][0]}" for identifier in payload.include
               if getattr(payload.inputs, bindings[identifier][0]) is None]
    if missing:
        raise ServiceError(422, "VALIDATION_ERROR", "Informe as entradas dos indicadores selecionados.",
                           details={"missing_fields": missing})
    results, successes, failures = {}, [], []
    for identifier in payload.include:
        field, service, item_model = bindings[identifier]
        try:
            if service is None:
                raise ServiceError(501, "INDICATOR_NOT_IMPLEMENTED", "Indicador selecionado ainda não implementado.",
                                   details={"indicator": identifier})
            response = service(getattr(payload.inputs, field), request_id)
        except ServiceError as exc:
            if exc.status not in {501, 502, 503, 504, 404, 429}:
                # Invalid input invalidates the request, even if a preceding ID was computed.
                raise ServiceError(exc.status, exc.code, exc.message, exc.retryable,
                                   {**exc.details, "indicator": identifier}) from None
            failures.append((identifier, exc))
            results[identifier] = UnavailableIndicator(
                status="not_implemented" if exc.status == 501 else "unavailable", reason=exc.code,
                error=ErrorInfo(code=exc.code, message=exc.message, retryable=exc.retryable,
                                details={**exc.details, "indicator": identifier}),
            )
        else:
            metadata = response.model_dump(exclude={"result", "contract_version", "operation", "status"})
            results[identifier] = item_model(**response.result.model_dump(), **metadata)
            successes.append((identifier, response))
    if not successes:
        # External unavailability takes priority over a calculation not yet implemented.
        _, primary = next(((identifier, error) for identifier, error in failures if error.status != 501), failures[0])
        raise ServiceError(primary.status, primary.code, primary.message, primary.retryable,
                           {"unavailable_indicators": [identifier for identifier, _ in failures],
                            "reasons": [f"{identifier}:{error.code}" for identifier, error in failures]})
    warnings = [f"{identifier}: {warning}" for identifier, response in successes for warning in response.quality.warnings]
    warnings += [f"{identifier}: {error.code}" for identifier, error in failures]
    return (response_model or RESPONSE_MODELS[group])(
        status="partial" if failures else "ok", result={"indicators": results},
        method=Method(name=f"{group}_analysis", version="1.0", assumptions=[
            "Orquestra apenas os IDs selecionados, reutilizando seus cálculos sem converter unidades, períodos ou bases temporais.",
            "Metadados e limitações científicas são mantidos por indicador; nenhuma disponibilidade externa é presumida.",
        ]),
        provenance=[source for _, response in successes for source in response.provenance],
        quality=Quality(kind="scenario" if any(response.quality.kind == "scenario" for _, response in successes) else "derived_estimate",
                        warnings=warnings, missing_dates=[]),
        limitations=["Cada indicador conserva sua unidade, período, origem e limitações; não interpretar os totais como um único valor.",
                     "Indicadores pendentes e integrações indisponíveis não possuem valores substitutos."],
        traceability=Traceability(request_id=request_id, input_references=[
            "sha256:" + hashlib.sha256(payload.model_dump_json().encode("utf-8")).hexdigest()]),
        generated_at=datetime.now(timezone.utc),
    )
