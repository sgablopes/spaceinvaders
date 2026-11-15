from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .meteomatics import ForecastError
from .meteomatics_schemas import ForecastRequest, ForecastResponse, ErrorResponse, PARAMETERS

PATH = "/v1/data/meteomatics/forecast"


def capability(service):
    return {"id": "get_meteomatics_forecast", "category": "INT", "method": "POST", "path": PATH,
        "openapi_operation_id": "get_meteomatics_forecast", "status": "configured_unverified" if service.configured else "credentials_missing",
        "implementation_status": "implemented", "credentials_configured": service.configured,
        "summary": "Previsões meteorológicas Meteomatics por coordenada e intervalo UTC.",
        "when_to_use": "Consultar previsões futuras de temperatura, chuva, umidade, vento e radiação, sem misturar com histórico NASA.",
        "parameters": list(PARAMETERS), "max_forecast_days_application_limit": service.max_days,
        "limitations": ["Permissões, parâmetros, fonte e horizonte dependem da conta; configuração não comprova autorização.",
                        "Acumulados/extremos terminam em valid_time; radiação e vento são instantâneos."]}


def register_meteomatics(app):
    previous_validation = app.exception_handlers[RequestValidationError]

    @app.exception_handler(ForecastError)
    async def forecast_error(request, exc):
        return JSONResponse(status_code=exc.status, content={"error": exc.error})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path != PATH:
            return await previous_validation(request, exc)
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR",
            "message": "Entrada inválida; confira o contrato de previsão. Credenciais pertencem ao ambiente do servidor.",
            "retryable": False, "details": {}}})

    router = APIRouter(tags=["Meteomatics"])

    @router.post(PATH, operation_id="get_meteomatics_forecast", response_model=ForecastResponse,
        summary="Consulta previsão operacional Meteomatics por coordenada",
        description="INT forecast em UTC, separado de NASA histórica. Parâmetros selecionáveis e step_hours 1/3/6/24. Temperatura, umidade, vento 10 m e radiação são instantâneos; temperatura média/mínima/máxima e chuva referem-se ao intervalo anterior. O primeiro intervalo deve estar inteiramente no futuro. Autenticação Basic HTTPS só no servidor por variáveis de ambiente, nunca no request. Limite padrão do serviço: 7 dias; não garante horizonte/permissões do plano. Dados incompletos são null/partial ou 404 com require_complete; sem fallback ou agregação diária.",
        responses={code: {"model": ErrorResponse} for code in (404, 422, 429, 502, 503, 504)})
    def forecast(payload: ForecastRequest, request: Request, response: Response):
        result = request.app.state.meteomatics.forecast(payload)
        response.headers["X-Request-ID"] = result.traceability.request_id
        response.headers["Cache-Control"] = "no-store"
        return result

    app.include_router(router)
