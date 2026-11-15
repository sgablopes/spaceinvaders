from typing import Annotated, Literal
from fastapi import APIRouter, Query, Request, Response
from .faostat_schemas import PricePage, LatestPricePage, CropCandidatePage
from .faostat_candidates import candidates
from .vendor.intelligence.schemas.common import ErrorResponse

PREFIX = "/v1/data/faostat"


def capability(service):
    return {"id": "get_faostat_producer_prices", "category": "INT", "method": "GET", "path": PREFIX + "/prices",
        "openapi_operation_id": "get_faostat_producer_prices", "status": "implemented" if service.configured else "files_missing",
        "summary": "Preços históricos recebidos pelo produtor e índices FAOSTAT por país, produto e período.",
        "catalogs": {"metadata": PREFIX + "/metadata", "countries": PREFIX + "/countries", "items": PREFIX + "/items",
            "crop_candidates": PREFIX + "/items/candidates"}, "latest_price": PREFIX + "/prices/latest",
        "limitations": ["Dados nacionais históricos; não são custos, cotação atual ou previsão de preço.",
            "Candidatos de culturas são lexicais e não revisados; confirme produto e forma comercial antes de selecionar item_code.",
            "LCU, SLC, USD/tonne e índice são preservados separadamente; sem câmbio ou interpolação.",
            "I14 aceita opcionalmente uma observação exata USD/tonne; custos e demais hipóteses continuam explícitos."]}


def register_faostat(app):
    router = APIRouter(prefix=PREFIX, tags=["FAOSTAT preços"], responses={c: {"model": ErrorResponse} for c in (404, 422, 503)})

    @router.get("/metadata", operation_id="get_faostat_price_metadata", summary="Cobertura real, unidades, flags e fontes da base local")
    def metadata(request: Request):
        return request.app.state.faostat.metadata()

    @router.get("/countries", operation_id="get_faostat_countries", summary="Correspondências FAOSTAT/M49/ISO/MapTiler fornecidas pelo AGRION")
    def countries(request: Request, q: Annotated[str | None, Query(min_length=1, max_length=200)] = None):
        return request.app.state.faostat.countries(q)

    @router.get("/items", operation_id="get_faostat_price_items", summary="Produtos e códigos CPC com dados de preços")
    def items(request: Request, q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
        area_code: Annotated[str | None, Query(pattern=r"^[0-9]{1,10}$")] = None,
        country_iso2: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None):
        store = request.app.state.faostat
        area = store.area_code(area_code=area_code, country_iso2=country_iso2) if area_code is not None or country_iso2 is not None else None
        return store.items(q, area)

    @router.get("/items/candidates", operation_id="get_faostat_crop_candidates", response_model=CropCandidatePage,
        summary="Candidatos lexicais entre culturas AGRION/ECOCROP e produtos FAOSTAT; revisão obrigatória")
    def crop_candidates(request: Request, q: Annotated[str, Query(min_length=2, max_length=200, pattern=r".*\S.*")],
        area_code: Annotated[str | None, Query(pattern=r"^[0-9]{1,10}$")] = None,
        country_iso2: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None):
        store = request.app.state.faostat
        area = store.area_code(area_code=area_code, country_iso2=country_iso2) if area_code is not None or country_iso2 is not None else None
        return candidates(request.app.state.store, store, q, area)

    @router.get("/prices/latest", operation_id="get_latest_faostat_producer_price", response_model=LatestPricePage,
        summary="Última observação não nula por país/produto/elemento e frequência, sem percorrer páginas",
        description="Padrão annual e 5532 USD/t. Recência por ano e mês; não mistura annual/monthly. Zero é observado. Duplicatas do último período são retornadas como ambiguous, sem escolha automática. Snapshot histórico, não cotação atual.")
    def latest(request: Request, response: Response,
        item_code: Annotated[str, Query(pattern=r"^[0-9]{1,10}$")],
        area_code: Annotated[str | None, Query(pattern=r"^[0-9]{1,10}$")] = None,
        country_iso2: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
        element_code: Annotated[str, Query(pattern=r"^[0-9]{1,10}$")] = "5532",
        frequency: Literal["annual", "monthly"] = "annual",
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        start_year: Annotated[int, Query(ge=1900, le=2100)] = 1991,
        end_year: Annotated[int, Query(ge=1900, le=2100)] = 2100):
        store = request.app.state.faostat
        area = store.area_code(area_code=area_code, country_iso2=country_iso2)
        response.headers["Cache-Control"] = "no-store"
        return store.latest_price(area, item_code, start_year, end_year, frequency=frequency, month=month, element_code=element_code)

    @router.get("/prices", operation_id="get_faostat_producer_prices", response_model=PricePage,
        summary="Consulta preços e índices históricos por produto, país e período",
        description="Snapshot FAOSTAT PP indexado em SQLite. Informe código FAOSTAT de país OU ISO2 inequívoco da planilha e item_code explícito. Ano inclusivo, frequência annual/monthly/all; month somente com monthly. 5530 LCU/tonne, 5531 SLC/tonne, 5532 USD/tonne; 5539 é índice 2014–2016=100, sem unidade monetária. Unit, Value textual e Flag originais preservados. Não calcula médias, câmbio, custos nem previsão; falta retorna lista vazia, não zero. Códigos ISO compartilhados por países históricos são recusados; escolha area_code.")
    def prices(request: Request, response: Response,
        item_code: Annotated[str, Query(pattern=r"^[0-9]{1,10}$")],
        area_code: Annotated[str | None, Query(pattern=r"^[0-9]{1,10}$")] = None,
        country_iso2: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
        start_year: Annotated[int, Query(ge=1900, le=2100)] = 1991,
        end_year: Annotated[int, Query(ge=1900, le=2100)] = 2100,
        frequency: Literal["annual", "monthly", "all"] = "annual",
        month: Annotated[int | None, Query(ge=1, le=12)] = None,
        element_code: Annotated[str | None, Query(pattern=r"^[0-9]{1,10}$")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
        order: Literal["asc", "desc"] = "asc"):
        store = request.app.state.faostat
        area = store.area_code(area_code=area_code, country_iso2=country_iso2)
        response.headers["Cache-Control"] = "no-store"
        return store.prices(area, item_code, start_year, end_year, frequency=frequency, month=month,
            element_code=element_code, limit=limit, offset=offset, order=order)

    app.include_router(router)
