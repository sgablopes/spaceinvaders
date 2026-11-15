"""Quatro operações do planejamento original, registradas na API única."""
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Request
from fastapi.exceptions import RequestValidationError

from .analysis_schemas import ClimateRequest, ClimateResponse, GDDRequest, RainfallRequest, IntegratedGDDResponse, IntegratedRainfallResponse
from .analysis_service import run, gdd, rainfall
from .vendor.intelligence.core.errors import ServiceError, error_response
from .vendor.intelligence.schemas.analysis import WaterRequest, WaterResponse, AgronomyRequest, AgronomyResponse, EconomicsRequest, EconomicsResponse
from .vendor.intelligence.indicators.catalog import GROUP_CATALOG, CATALOG
from .vendor.intelligence.schemas import indicators
from .vendor.intelligence.schemas.common import ErrorResponse

EXAMPLE = {"summary": "NASA histórico — coordenadas e Tbase são entradas ilustrativas, sem resposta fixa",
    "value": {"include": ["I01", "I02"], "inputs": {
        "gdd": {"location": {"latitude": -16.5, "longitude": -49.3}, "crop_id": "maize",
                "start_date": "2025-10-01", "end_date": "2025-10-03", "base_temperature_c": 10, "timezone": "UTC"},
        "rainfall": {"location": {"latitude": -16.5, "longitude": -49.3}, "reference_date": "2025-10-03", "day_basis": "UTC"}}}}


def analysis_capabilities():
    groups = [g.model_dump(mode="json") for g in GROUP_CATALOG]
    for group in groups:
        group["limitations"] = ["Selecione somente os IDs necessários. Período, unidade e procedência são individuais.",
                                "Indicadores planejados sem método validado continuam 501; sem valores substitutos."]
        for item in group["supported_indicators"]:
            if item["id"] in {"I01", "I02"}:
                item["implementation_status"] = "implemented_manual_and_nasa_power"
                item["modes"] = ["caller_supplied", "nasa_power"]
                item["limitations"] = ["Sem forecast; a cobertura diária deve ser completa.",
                    "GDD automático exige UTC e Tbase explícita." if item["id"] == "I01" else "Chuva automática consulta 90 dias, em UTC ou LST explícitos."]
        if group["id"] == "analyze_climate":
            group["when_to_use"] = "Calcular GDD e chuva com séries próprias ou consulta NASA POWER automática; I03/I05 permanecem pendentes."
    return groups


def register_analysis(app):
    previous_validation = app.exception_handlers[RequestValidationError]

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path.startswith(("/v1/analysis/", "/v1/indicators/")):
            return error_response(ServiceError(422, "VALIDATION_ERROR", "Entrada inválida para esta operação.", details={"issue_count": len(exc.errors())}))
        return await previous_validation(request, exc)

    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        if request.url.path.startswith(("/v1/analysis/", "/v1/indicators/")):
            request.state.request_id = uuid4().hex
            response = await call_next(request)
            response.headers["X-Request-ID"] = request.state.request_id
            response.headers["Cache-Control"] = "no-store"
            return response
        return await call_next(request)

    router = APIRouter(prefix="/v1/analysis", tags=["Análises"], responses={
        code: {"model": ErrorResponse} for code in (404, 422, 429, 501, 502, 503, 504)})

    @router.post("/climate", response_model=ClimateResponse, operation_id="analyze_climate", summary="Calcula GDD e chuva acumulada com dados próprios ou NASA POWER",
        description="I01: GDD diário/total em degree_day_c, método simple_average_no_upper_cap v1.0 e Tbase explícita. I02: somas de 7/15/30/90 dias em mm, rolling_sum_precipitation v1.0. Omita a série para consulta automática NASA histórica; GDD exige UTC, chuva admite UTC/LST. Séries manuais não fazem chamadas externas. I03/I05 não implementados. Em sucesso parcial cada ID indisponível tem motivo explícito. Não calcula forecast ou recomendação de plantio.")
    def climate(payload: Annotated[ClimateRequest, Body(openapi_examples={"nasa_historical": EXAMPLE})], request: Request):
        return run("climate", payload, request.state.request_id, request.app.state.nasa)

    @router.post("/water", response_model=WaterResponse, operation_id="analyze_water", summary="Contrato de análise de água — indicadores pendentes",
        description="I07 ETc e I08 balanço hídrico ainda não implementados. Entradas válidas retornam 501; não produz valores fictícios.")
    def water(payload: WaterRequest, request: Request):
        return run("water", payload, request.state.request_id, request.app.state.nasa)

    @router.post("/agronomy", response_model=AgronomyResponse, operation_id="analyze_agronomy", summary="Contrato agronômico — indicadores pendentes",
        description="I09 aptidão, I10 sucessão e I11 risco aguardam validação dos métodos e catálogos. Não exige sucessão para selecionar I09. Entradas válidas retornam 501.")
    def agronomy(payload: AgronomyRequest, request: Request):
        return run("agronomy", payload, request.state.request_id, request.app.state.nasa)

    @router.post("/economics", response_model=EconomicsResponse, operation_id="analyze_economics", summary="Contrato econômico — indicadores pendentes",
        description="I13 cenário produtivo e I14 margem aguardam implementação/validação. Entradas válidas retornam 501; não garante produção ou lucro.")
    def economics(payload: EconomicsRequest, request: Request):
        return run("economics", payload, request.state.request_id, request.app.state.nasa)

    app.include_router(router)
    legacy = APIRouter(include_in_schema=False)

    @legacy.post("/v1/indicators/gdd", response_model=IntegratedGDDResponse, operation_id="calculate_gdd")
    def legacy_gdd(payload: GDDRequest, request: Request):
        return gdd(request.app.state.nasa, payload, request.state.request_id)

    @legacy.post("/v1/indicators/accumulated-rainfall", response_model=IntegratedRainfallResponse, operation_id="calculate_accumulated_rainfall")
    def legacy_rain(payload: RainfallRequest, request: Request):
        return rainfall(request.app.state.nasa, payload, request.state.request_id)

    def placeholder(item, model):
        def pending(payload: model):
            raise ServiceError(501, "INDICATOR_NOT_IMPLEMENTED", "Indicador previsto, ainda não implementado.", details={"operation": item.id})
        legacy.post(item.path, operation_id=item.id)(pending)

    for item, model in zip(CATALOG[2:], (indicators.DrySpellRequest, indicators.ThermalStressRequest, indicators.ETcRequest,
        indicators.WaterBalanceRequest, indicators.SuitabilityRequest, indicators.SuccessionRequest, indicators.PlantingRiskRequest,
        indicators.YieldScenarioRequest, indicators.MarginRequest)):
        placeholder(item, model)
    app.include_router(legacy)
