from typing import Annotated

from fastapi import APIRouter, Body, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse

from .nasa_power import NasaError
from .nasa_schemas import DailyRequest, DailyResponse, ErrorResponse, PARAMETERS
from .analysis_routes import analysis_capabilities
from .meteomatics_routes import capability as meteomatics_capability

PATH = "/v1/data/nasa-power/daily"


def register_nasa(app: FastAPI):
    @app.exception_handler(NasaError)
    async def nasa_error(request: Request, exc: NasaError):
        return JSONResponse(status_code=exc.status, content={"error": exc.error})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path != PATH:
            return await request_validation_exception_handler(request, exc)
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR",
                            "message": "Entrada inválida; confira o contrato OpenAPI.", "retryable": False, "details": {}}})

    router = APIRouter(tags=["NASA POWER"])

    @router.post(PATH, response_model=DailyResponse, operation_id="get_nasa_power_daily_weather",
                 summary="Consulta clima diário histórico por coordenada na NASA POWER",
                 description="INT S01, consulta sob demanda para o AGRION. Temperaturas em °C, chuva corrigida em mm/day, umidade em % e radiação em MJ/m²/day. Até 366 dias inclusivos, UTC ou LST explícitos. Lacunas são null e status partial; require_complete rejeita série incompleta. Cache limitado com procedência preservada. Sem forecast, cálculo de ETo ou preenchimento de lacunas.",
                 responses={code: {"model": ErrorResponse} for code in (404, 422, 429, 502, 503, 504)})
    def daily(payload: Annotated[DailyRequest, Body(openapi_examples={
                  "historical": {"summary": "Consulta histórica ilustrativa; os dados serão obtidos na NASA, sem resposta fixa",
                      "value": {"location": {"latitude": -16.5, "longitude": -49.3},
                                "start_date": "2025-10-01", "end_date": "2025-10-03",
                                "parameters": list(PARAMETERS), "time_standard": "UTC", "require_complete": False}}})],
              request: Request, response: Response):
        result = request.app.state.nasa.daily(payload)
        response.headers["X-Request-ID"] = result.traceability.request_id
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get("/v1/capabilities", operation_id="get_data_capabilities", tags=["catálogo"])
    def capabilities(request: Request) -> dict:
        return {"contract_version": "1.0", "capabilities": [{"id": "get_nasa_power_daily_weather",
                "category": "INT", "method": "POST", "path": PATH,
                "openapi_operation_id": "get_nasa_power_daily_weather", "status": "implemented",
                "summary": "Clima diário histórico NASA POWER para séries de temperatura, chuva, umidade e radiação.",
                "when_to_use": "Obter dados reais da fonte regional para alimentar o AGRION e os indicadores existentes, sem forecast.",
                "parameters": list(PARAMETERS), "limitations": ["Máximo 366 dias por consulta.", "Lacunas não são zeros.",
                "UTC/LST explícitos; disponibilidade recente depende da fonte."]}, *analysis_capabilities(),
                meteomatics_capability(request.app.state.meteomatics)],
                "other_data_catalog": "/api/v1/datasets",
                "pending": (["Validação autenticada Meteomatics e permissões do plano"] if not request.app.state.meteomatics.configured else [])
                    + ["ET₀", "Nove indicadores ainda não implementados e integração do Flask"]}

    app.include_router(router)
