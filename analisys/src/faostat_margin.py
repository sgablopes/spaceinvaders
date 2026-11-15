"""Resolve somente o preço; delega a aritmética ao I14 existente, sem inventar custos."""
from datetime import datetime, timezone
import hashlib
from .indicators import margin
from .indicator_schemas import IndicatorProvenance, MarginRequest
from .faostat_store import DOCS
from .faostat_schemas import PriceObservation
from .vendor.intelligence.core.errors import ServiceError


def calculate(store, payload, request_id):
    if payload.faostat_price is None:
        return margin(payload, request_id)
    if store is None:
        raise ServiceError(503, "FAOSTAT_FILES_MISSING", "Índice FAOSTAT indisponível; não foi inventado preço.")
    selection = payload.faostat_price
    area = store.area_code(area_code=selection.area_code, country_iso2=selection.country_iso2)
    page = store.prices(area, selection.item_code, selection.year, selection.year, frequency=selection.frequency,
        month=selection.month, element_code=selection.element_code, limit=2)
    if page["total"] == 0:
        raise ServiceError(404, "FAOSTAT_PRICE_NOT_FOUND", "Não há observação para a seleção exata; sem ano/país/produto substituto.")
    if page["total"] != 1:
        raise ServiceError(503, "FAOSTAT_PRICE_AMBIGUOUS", "Observação duplicada/ambígua; nenhum preço foi escolhido ou agregado.")
    record = page["items"][0]
    if record["value"] is None:
        raise ServiceError(404, "FAOSTAT_PRICE_MISSING_VALUE", "Observação sem valor; não foi substituída por zero.")
    if record["value_kind"] != "usd_per_tonne" or payload.currency != "USD" or record["value"] < 0:
        raise ServiceError(422, "FAOSTAT_PRICE_UNIT_INCOMPATIBLE", "I14 exige preço USD/tonne e custos declarados em USD; índice/LCU/SLC não são convertidos.")
    values = payload.model_dump(mode="json")
    values.update(price_per_t=record["value"], faostat_price=None)
    computed = margin(MarginRequest.model_validate(values), request_id)
    computed.result.price_per_t_used = record["value"]
    computed.result.faostat_price_record = PriceObservation.model_validate(record)
    computed.result.price_data_sha256 = page["source"]["sha256"]
    computed.provenance.append(IndicatorProvenance(provider="FAOSTAT", dataset=f"PP area={area}; item={selection.item_code}; {selection.year}/{record['months_code']}; flag={record['flag']}",
        source_url=DOCS, accessed_at=datetime.now(timezone.utc), spatial_resolution="National producer-price statistics, not field transaction",
        temporal_resolution=selection.frequency, license="CC BY 4.0 (FAO statistics)", kind="catalog_reference"))
    computed.method.assumptions += [selection.reference, "Preço histórico nacional selecionado explicitamente como hipótese do cenário; custos permanecem informados pelo consumidor."]
    computed.quality.warnings += ["FAOSTAT é referência histórica nacional, não preço atual/futuro ou receita garantida no talhão.",
        "Flag original da observação: " + record["flag"] + "; não foi promovida a observação de campo."]
    computed.traceability.input_references += ["request-sha256:" + hashlib.sha256(payload.model_dump_json().encode()).hexdigest(),
        "faostat-csv-sha256:" + page["source"]["sha256"], "faostat-countries-sha256:" + page["source"]["country_mapping"]["sha256"],
        "faostat-source-row:" + str(record["source_row"])]
    return computed
