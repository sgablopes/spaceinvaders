"""Quatro operações do planejamento original, registradas na API única."""
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Request
from fastapi.exceptions import RequestValidationError

from .analysis_schemas import (ClimateRequest, ClimateResponse, GDDRequest, RainfallRequest, IntegratedGDDResponse, IntegratedRainfallResponse,
    WaterRequest, WaterResponse, EconomicsRequest, EconomicsResponse)
from .analysis_service import run, gdd, rainfall
from .indicator_schemas import DrySpellRequest, ThermalRequest, ETcRequest, WaterBalanceRequest, MarginRequest, CalculationResponse
from .vendor.intelligence.core.errors import ServiceError, error_response
from .vendor.intelligence.schemas.analysis import AgronomyRequest, AgronomyResponse
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
            if item["id"] in {"I03", "I05", "I07", "I08", "I14"}:
                item["available"] = True
                item["implementation_status"] = "implemented_explicit_inputs"
                item["summary"] = {"I03": "Maior sequência de dias secos na janela",
                    "I05": "Triagem de exposição térmica, sem estimativa de dano",
                    "I07": "ETc padrão com ETo e Kc explícitos",
                    "I08": "Variação hídrica com fluxos explícitos",
                    "I14": "Margem do cenário econômico declarado"}[item["id"]]
                item["limitations"] = {
                    "I03": ["Maior sequência com chuva < limiar explícito; não classifica risco de seca.", "NASA histórica e forecast Meteomatics/Open-Meteo; disponibilidade não é garantida."],
                    "I05": ["Somente contagem de exposição a limites declarados ou gerais ECOCROP; não diagnostica dano por estádio."],
                    "I07": ["ETc=Kc×ETo sob condições padrão. ETo e escolha do Kc devem ser fornecidas; sem cálculo de ETo."],
                    "I08": ["Variação contábil ΔS; fluxos/perdas e ETo explícitos. Não estima estoque real do solo ou irrigação recomendada."],
                    "I14": ["Preço declarado ou observação FAOSTAT USD/tonne selecionada explicitamente. Custos continuam informados; não prevê preço/rendimento ou lucro líquido."]}[item["id"]]
                item["modes"] = ["caller_supplied", "nasa_power", "automatic_forecast_meteomatics_open_meteo"] if item["id"] in {"I03", "I05"} else ["explicit_inputs_scenario"]
                if item["id"] == "I08":
                    item["modes"] += ["nasa_power_precipitation", "automatic_forecast_precipitation"]
                if item["id"] == "I14":
                    item["modes"] += ["faostat_historical_usd_price"]
        if group["id"] == "analyze_climate":
            group["when_to_use"] = "GDD, chuva, sequências secas e triagem de exposição térmica, sem inferir dano ou risco agronômico."
        if group["id"] == "analyze_water":
            group["when_to_use"] = "Calcular ETc padrão e variação hídrica com ETo, Kc e fluxos explícitos, sem inferir estoque de água no solo."
        if group["id"] == "analyze_economics":
            group["when_to_use"] = "Calcular margem com área/rendimento/custos declarados e preço próprio ou FAOSTAT histórico explicitamente selecionado. I13 permanece pendente."
        group["available"] = any(i["available"] for i in group["supported_indicators"])
        group["implementation_status"] = "implemented" if all(i["available"] for i in group["supported_indicators"]) else "partial" if group["available"] else "planned"
    return groups


def register_analysis(app):
    previous_validation = app.exception_handlers[RequestValidationError]

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path.startswith(("/v1/analysis/", "/v1/indicators/", "/v1/simulations/")):
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

    @router.post("/climate", response_model=ClimateResponse, operation_id="analyze_climate", summary="GDD, chuva, sequências secas e exposição térmica",
        description="I01 GDD e I02 chuva mantêm métodos e contratos anteriores. I03 calcula maior sequência de dias com chuva abaixo do limiar explícito. I05 conta exposição fora de limites declarados ou gerais ECOCROP, sem diagnosticar dano. I03/I05 aceitam séries próprias, NASA histórica ou dias completos UTC com Meteomatics e alternativa automática Open-Meteo. Fonte e motivo da troca são preservados; não há equivalência garantida entre extremos dos provedores.")
    def climate(payload: Annotated[ClimateRequest, Body(openapi_examples={"nasa_historical": EXAMPLE})], request: Request):
        return run("climate", payload, request.state.request_id, request.app.state.nasa, request.app.state.store, request.app.state.weather)

    @router.post("/water", response_model=WaterResponse, operation_id="analyze_water", summary="ETc padrão e variação hídrica com entradas explícitas",
        description="I07: ETc=Kc×ETo com ETo diária fornecida e Kc explícito ou registro FAO escalar selecionado. I08: ΔS=P+I+CR−RO−ETc−DP; fluxos/perdas obrigatórios, sem zeros presumidos. Chuva forecast usa Meteomatics com alternativa Open-Meteo. Não estima água disponível/estresse no solo nem calcula ETo; demais entradas permanecem explícitas.")
    def water(payload: WaterRequest, request: Request):
        return run("water", payload, request.state.request_id, request.app.state.nasa, request.app.state.store, request.app.state.weather)

    @router.post("/agronomy", response_model=AgronomyResponse, operation_id="analyze_agronomy", summary="Contrato agronômico — indicadores pendentes",
        description="I09 aptidão, I10 sucessão e I11 risco aguardam validação dos métodos e catálogos. Não exige sucessão para selecionar I09. Entradas válidas retornam 501.")
    def agronomy(payload: AgronomyRequest, request: Request):
        return run("agronomy", payload, request.state.request_id, request.app.state.nasa)

    @router.post("/economics", response_model=EconomicsResponse, operation_id="analyze_economics", summary="Margem do cenário econômico declarado",
        description="I14 reutiliza área×rendimento×preço menos custos declarados. Informe price_per_t ou faostat_price exato, exclusivamente. FAOSTAT somente USD/tonne, moeda USD e referência explícita do uso histórico no cenário; custos/ha em USD continuam obrigatórios, sem câmbio. Índices/LCU/SLC não viram preço financeiro. Não prevê produtividade/preços ou lucro líquido. I13 permanece pendente.")
    def economics(payload: EconomicsRequest, request: Request):
        return run("economics", payload, request.state.request_id, request.app.state.nasa, request.app.state.store, request.app.state.weather, request.app.state.faostat)

    app.include_router(router)
    legacy = APIRouter(include_in_schema=False)

    @legacy.post("/v1/indicators/gdd", response_model=IntegratedGDDResponse, operation_id="calculate_gdd")
    def legacy_gdd(payload: GDDRequest, request: Request):
        return gdd(request.app.state.nasa, payload, request.state.request_id)

    @legacy.post("/v1/indicators/accumulated-rainfall", response_model=IntegratedRainfallResponse, operation_id="calculate_accumulated_rainfall")
    def legacy_rain(payload: RainfallRequest, request: Request):
        return rainfall(request.app.state.nasa, payload, request.state.request_id)

    def placeholder(item, model):
        implemented = {"I03": ("climate", "dry_spell", ClimateRequest), "I05": ("climate", "thermal_stress", ClimateRequest),
            "I07": ("water", "crop_evapotranspiration", WaterRequest), "I08": ("water", "water_balance", WaterRequest),
            "I14": ("economics", "crop_margin", EconomicsRequest)}
        def pending(payload: model, request: Request):
            if item.indicator_id not in implemented:
                raise ServiceError(501, "INDICATOR_NOT_IMPLEMENTED", "Indicador previsto, ainda não implementado.", details={"operation": item.id})
            group, field, group_model = implemented[item.indicator_id]
            selected = group_model.model_validate({"include": [item.indicator_id], "inputs": {field: payload.model_dump(mode="json")}})
            answer = run(group, selected, request.state.request_id, request.app.state.nasa, request.app.state.store, request.app.state.weather, request.app.state.faostat)
            data = answer.result.indicators[item.indicator_id].model_dump()
            metadata = {k: data.pop(k) for k in ("status", "method", "provenance", "quality", "limitations", "traceability", "generated_at")}
            return CalculationResponse(operation=item.id, result=data, **metadata)
        legacy.post(item.path, operation_id=item.id)(pending)

    for item, model in zip(CATALOG[2:], (DrySpellRequest, ThermalRequest, ETcRequest,
        WaterBalanceRequest, indicators.SuitabilityRequest, indicators.SuccessionRequest, indicators.PlantingRiskRequest,
        indicators.YieldScenarioRequest, MarginRequest)):
        placeholder(item, model)
    app.include_router(legacy)
