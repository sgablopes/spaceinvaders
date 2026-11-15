from fastapi import APIRouter, Request, Response
from .aquacrop_schemas import SimulationRequest, SimulationResponse
from .aquacrop_service import run
from .vendor.intelligence.schemas.common import ErrorResponse

PATH = "/v1/simulations/aquacrop"


def capability():
    return {"id": "simulate_aquacrop", "category": "SIM", "method": "POST", "path": PATH,
        "openapi_operation_id": "simulate_aquacrop", "status": "implemented",
        "engine": "AquaCrop-OSPy 3.0.12", "official_fao_7_3": False, "crops": ["Maize"],
        "soil_presets": ["SandyLoam", "Loam"], "weather_sources": ["nasa_power", "caller_supplied"],
        "summary": "Executa uma safra real do motor científico com produtividade simulada e balanço hídrico diário.",
        "limitations": ["Parâmetros genéricos não calibrados localmente; resultados são cenários, não dados de colheita.",
            "Uma safra de sequeiro até 300 dias; solo, água inicial, CO2 e hipóteses explícitos.",
            "FAO AquaCrop oficial 7.3 apresentou erros internos e não é anunciado como executável validado."]}


def register_aquacrop(app):
    router = APIRouter(tags=["Simulação AquaCrop"])

    @router.post(PATH, operation_id="simulate_aquacrop", response_model=SimulationResponse,
        summary="Executa AquaCrop-OSPy com clima NASA/FAO-56 ou série fornecida",
        description="SIM: uma safra Maize de sequeiro, plantio no primeiro dia, solo genérico SandyLoam/Loam com profundidade e umidade inicial explícitas, CO2 constante declarado. NASA histórica fornece clima e entradas de ETo FAO-56; série própria deve incluir ETo. Sem lacunas ou preenchimento. Executa motor 3.0.12 em processo isolado, recusa safra incompleta e valida fechamento hídrico. Retorna produtividade simulada t/ha, fluxos/armazenamento em mm e procedência. Não equivale a FAO 7.3, calibração agronômica local ou recomendação.",
        responses={c: {"model": ErrorResponse} for c in (404, 422, 429, 502, 503, 504)})
    def simulate(payload: SimulationRequest, request: Request, response: Response):
        result = run(payload, request.app.state.nasa, request.app.state.analysis_root)
        response.headers["X-Request-ID"] = result.traceability["request_id"]
        response.headers["Cache-Control"] = "no-store"
        return result

    app.include_router(router)
