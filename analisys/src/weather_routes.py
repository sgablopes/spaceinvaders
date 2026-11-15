from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .weather_schemas import WeatherRequest, WeatherResponse
from .nasa_schemas import ErrorResponse
from .meteomatics_schemas import PARAMETERS

PATH = "/v1/data/weather/forecast"


def capability(service):
    return {"id": "get_weather_forecast", "category": "INT", "method": "POST", "path": PATH,
        "openapi_operation_id": "get_weather_forecast", "status": "implemented",
        "providers": ["Meteomatics", "Open-Meteo"], "parameters": list(PARAMETERS),
        "summary": "Previsão por coordenada, Meteomatics preferida com alternativa automática Open-Meteo.",
        "limitations": ["Auto exige cobertura completa de uma fonte, sem mistura ou garantia de disponibilidade.",
            "Extremos térmicos Open-Meteo apenas diários UTC; fonte mix; API gratuita não comercial.",
            "ETo e NASA GEOS-FP não fazem parte deste conector."]}


def register_weather(app):
    previous = app.exception_handlers[RequestValidationError]

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path != PATH:
            return await previous(request, exc)
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR",
            "message": "Entrada inválida para previsão; consulte OpenAPI. Não envie credenciais.", "retryable": False, "details": {}}})

    router = APIRouter(tags=["Meteorologia"])

    @router.post(PATH, operation_id="get_weather_forecast", response_model=WeatherResponse,
        summary="Previsão com alternativa automática Open-Meteo",
        description="provider auto prefere Meteomatics e tenta Open-Meteo se indisponível, negada, limitada ou incompleta. Não mistura fontes. provider explícito não faz fallback. Mesmo contrato de variáveis/UTC; Open-Meteo aceita source mix e extremos/média térmicos somente em 24h encerradas à meia-noite UTC. Auto exige cobertura completa; ambas indisponíveis retornam 503. NASA POWER histórica é preservada. API pública Open-Meteo somente para uso não comercial, com atribuição e cotas.",
        responses={c: {"model": ErrorResponse} for c in (404, 422, 429, 502, 503, 504)})
    def forecast(payload: WeatherRequest, request: Request, response: Response):
        answer = request.app.state.weather.forecast(payload)
        response.headers["X-Request-ID"] = answer.traceability.request_id
        response.headers["Cache-Control"] = "no-store"
        return answer

    app.include_router(router)
