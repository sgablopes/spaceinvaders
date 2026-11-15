from typing import Annotated, Any, Literal
from pydantic import Field, model_validator
from .nasa_schemas import Schema

Code = Annotated[str, Field(pattern=r"^[0-9]{1,10}$")]
ISO2 = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class PriceSelection(Schema):
    area_code: Code | None = None
    country_iso2: ISO2 | None = None
    item_code: Code
    year: Annotated[int, Field(strict=True, ge=1900, le=2100)]
    element_code: Literal["5532"] = "5532"
    frequency: Literal["annual", "monthly"] = "annual"
    month: Annotated[int, Field(strict=True, ge=1, le=12)] | None = None
    reference: Annotated[str, Field(min_length=1, max_length=200, description="Hipótese explícita de usar esta observação histórica nacional no cenário; não é previsão/cotação atual.")]

    @model_validator(mode="after")
    def exact_observation(self):
        if (self.area_code is None) == (self.country_iso2 is None):
            raise ValueError("Informe area_code ou country_iso2, exclusivamente.")
        if (self.frequency == "monthly") != (self.month is not None):
            raise ValueError("Seleção mensal exige mês; seleção anual não aceita mês.")
        return self


class PriceObservation(Schema):
    source_row: int
    area_code: str
    area_m49: str
    area: str
    item_code: str
    item_cpc: str
    item: str
    element_code: str
    element: str
    year: int
    months_code: str
    months: str
    unit: str
    value: float | None
    value_text: str
    flag: str
    value_kind: Literal["local_currency_per_tonne", "standard_local_currency_per_tonne", "usd_per_tonne", "index_2014_2016_100", "unknown"]
    currency_iso3: Literal["USD"] | None
    raw: dict[str, str]


class PricePage(Schema):
    total: int
    limit: int
    offset: int
    items: list[PriceObservation]
    source: dict[str, Any]


class LatestPricePage(PricePage):
    selection_status: Literal["found", "not_found", "ambiguous"]
    frequency: Literal["annual", "monthly"]
    element_code: str
    non_null_only: Literal[True]
    selected_period: dict[str, int | None] | None


class CropCandidate(Schema):
    item_code: str
    cpc_raw: str
    name: str
    mapping_status: Literal["candidate_unreviewed"]
    match_strength: Literal["complete_alias_tokens", "partial_alias_tokens"]
    evidence: list[dict[str, Any]]


class CropCandidatePage(Schema):
    query: str
    mapping_status: Literal["candidate_unreviewed"]
    requires_review: Literal[True]
    selected_item_code: None
    candidates: list[CropCandidate]
    additional_partial_candidates: list[CropCandidate]
    knowledge_cultures: list[dict[str, Any]]
    ecocrop_cultures: list[dict[str, Any]]
    search_coverage: dict[str, Any]
    sources: dict[str, Any]
    method: str
    limitations: list[str]
