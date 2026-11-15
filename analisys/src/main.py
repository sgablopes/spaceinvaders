from contextlib import asynccontextmanager
import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from .gaez import ExternalError, Gaez
from .store import FILES, Store
from .nasa_power import NasaPower
from .nasa_routes import register_nasa
from .analysis_routes import register_analysis
from .meteomatics import Meteomatics
from .meteomatics_routes import register_meteomatics
from .open_meteo import OpenMeteo
from .weather_service import Weather
from .weather_routes import register_weather
from .aquacrop_routes import register_aquacrop
from .faostat_store import FaostatStore
from .faostat_routes import register_faostat

ROOT = Path(__file__).resolve().parents[1]


class Record(BaseModel):
    source_row: int
    data: dict[str, Any]


class Page(BaseModel):
    dataset: str
    table: str
    total: int
    limit: int
    offset: int
    source: dict[str, Any]
    items: list[Record]


def create_app(root: Path = ROOT, database: Path | None = None, gaez=None, nasa=None, meteomatics=None, open_meteo=None, faostat=None):
    store = Store(root, database or root / ".runtime" / "catalog.sqlite3")

    @asynccontextmanager
    async def lifespan(app):
        store.prepare()
        app.state.store = store
        app.state.faostat = faostat or FaostatStore(root)
        app.state.faostat.prepare()
        app.state.analysis_root = root.resolve()
        app.state.gaez = gaez or Gaez()
        app.state.nasa = nasa or NasaPower()
        app.state.meteomatics = meteomatics or Meteomatics()
        app.state.open_meteo = open_meteo or OpenMeteo()
        app.state.weather = Weather(app.state.meteomatics, app.state.open_meteo)
        try:
            yield
        finally:
            app.state.gaez.close()
            app.state.nasa.close()
            app.state.meteomatics.close()
            app.state.open_meteo.close()

    app = FastAPI(title="Agrion — Dados e análises agronômicas", version="1.6.0", lifespan=lifespan,
                  description="Fontes agronômicas, FAOSTAT PP histórico indexado, GAEZ v5, NASA POWER, Meteomatics/Open-Meteo e AquaCrop-OSPy 3.0.12. Quatro operações de análise preservadas. I14 aceita preço histórico FAOSTAT USD/tonne explicitamente selecionado; custos não são inferidos. Simulações e cenários não são observações de produtividade nem previsões de preço.")

    @app.get("/health", tags=["serviço"])
    def health(request: Request) -> dict[str, Any]:
        return {"status": "ok", "datasets": len(request.app.state.store.datasets()) + int(request.app.state.faostat.configured),
                "gaez": "external_on_demand_not_checked"}

    @app.get("/api/v1/datasets", tags=["catálogo"])
    def datasets(request: Request) -> dict[str, Any]:
        return {"local": [*request.app.state.store.datasets(), *([request.app.state.faostat.metadata()] if request.app.state.faostat.configured else [])],
                "external": [{"id": "gaez", "version": "5", "endpoint": "/api/v1/gaez/layers"},
                             {"id": "nasa_power", "endpoint": "/v1/data/nasa-power/daily", "method": "POST"},
                             {"id": "meteomatics", "endpoint": "/v1/data/meteomatics/forecast", "method": "POST",
                              "credentials_configured": request.app.state.meteomatics.configured},
                             {"id": "weather_forecast", "endpoint": "/v1/data/weather/forecast", "method": "POST",
                              "providers": ["Meteomatics", "Open-Meteo"]}],
                "unavailable": ["HWSD: raster e banco MDB não estão nesta pasta."] + ([] if request.app.state.faostat.configured else ["FAOSTAT: forneça CSV e planilha de países."])}

    def source_router(dataset):
        router = APIRouter(prefix=f"/api/v1/{dataset}", tags=[dataset])

        @router.get("/tables")
        def tables(request: Request) -> list[dict[str, Any]]:
            return request.app.state.store.tables(dataset)

        @router.get("/tables/{table}")
        def schema(table: str, request: Request) -> dict[str, Any]:
            try:
                return request.app.state.store.metadata(dataset, table)
            except KeyError:
                raise HTTPException(404, "Tabela não encontrada.")

        @router.get("/{table}", response_model=Page)
        def records(table: str, request: Request,
                    limit: Annotated[int, Query(ge=1, le=500)] = 50,
                    offset: Annotated[int, Query(ge=0)] = 0,
                    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
                    filtros: Annotated[str | None, Query(max_length=4000, description='Objeto JSON com igualdade exata, nomes de colunas e tipos da fonte. Ex.: {"crop_id":"ECO_289"}. null filtra ausentes.')] = None):
            try:
                filters = json.loads(filtros) if filtros is not None else {}
                if not isinstance(filters, dict):
                    raise ValueError("filtros deve ser um objeto JSON.")
                return request.app.state.store.records(dataset, table, limit, offset, q, filters)
            except KeyError:
                raise HTTPException(404, "Tabela não encontrada.")
            except (ValueError, OverflowError) as exc:
                raise HTTPException(422, str(exc))

        return router

    # Rotas documentais antes de /conhecimento/{table}.
    docs = APIRouter(prefix="/api/v1/conhecimento/documentos", tags=["conhecimento"])

    @docs.get("")
    def documents(request: Request) -> list[str]:
        return request.app.state.store.documents()

    @docs.get("/{name}")
    def document(name: str, request: Request) -> dict[str, Any]:
        try:
            return {"name": name, "content": request.app.state.store.documents(name)}
        except KeyError:
            raise HTTPException(404, "Documento não encontrado.")

    app.include_router(docs)
    for dataset in FILES:
        app.include_router(source_router(dataset))

    external = APIRouter(prefix="/api/v1/gaez", tags=["gaez"])

    @external.get("/layers")
    def layers(request: Request,
               variable: Annotated[str | None, Query(pattern=r"^[A-Z0-9-]{1,40}$")] = None,
               filename_prefix: Annotated[str | None, Query(pattern=r"^GAEZ-V5\.[A-Za-z0-9_.-]{0,180}$")] = None,
               limit: Annotated[int, Query(ge=1, le=500)] = 50,
               page_token: Annotated[str | None, Query(max_length=4000)] = None) -> dict[str, Any]:
        if filename_prefix and not variable:
            raise HTTPException(422, "filename_prefix exige variable.")
        try:
            return request.app.state.gaez.layers(variable, filename_prefix, limit, page_token)
        except ExternalError as exc:
            raise HTTPException(exc.status, exc.message)

    @external.get("/point")
    def point(request: Request,
              layer: Annotated[str, Query(min_length=1, max_length=300)],
              latitude: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
              longitude: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]) -> dict[str, Any]:
        try:
            return request.app.state.gaez.point(layer, latitude, longitude)
        except ExternalError as exc:
            raise HTTPException(exc.status, exc.message)
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    app.include_router(external)
    register_nasa(app)
    register_analysis(app)
    register_meteomatics(app)
    register_weather(app)
    register_aquacrop(app)
    register_faostat(app)
    return app


app = create_app()
