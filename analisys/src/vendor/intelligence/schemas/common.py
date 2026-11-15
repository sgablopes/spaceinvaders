from datetime import date
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, AwareDatetime, field_validator, model_validator

NonEmpty = Annotated[str, Field(min_length=1, max_length=200)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Location(Schema):
    latitude: float = Field(ge=-90, le=90, description="Latitude WGS84, graus decimais.")
    longitude: float = Field(ge=-180, le=180, description="Longitude WGS84, graus decimais.")


class Period(Schema):
    start: date
    end: date
    timezone: str = "UTC"
    calendar: Literal["gregorian"] = "gregorian"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Fuso IANA inválido.") from exc
        return value

    @model_validator(mode="after")
    def ordered(self) -> "Period":
        if self.end < self.start:
            raise ValueError("O fim do período deve ser igual ou posterior ao início.")
        return self


class Geography(Schema):
    location: Location | None = None
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    scope: NonEmpty = Field(description="Escala aplicável: ponto, região, país ou contexto declarado.")


class Method(Schema):
    category: Literal["IND"] = "IND"
    name: NonEmpty
    version: NonEmpty
    assumptions: list[str]


class Provenance(Schema):
    provider: NonEmpty
    dataset: NonEmpty
    source_url: HttpUrl | None
    accessed_at: AwareDatetime
    spatial_resolution: str | None
    temporal_resolution: str | None
    license: str | None
    kind: Literal["observed", "modeled_estimate", "operational_forecast", "scenario", "farmer_declared", "caller_supplied"]


class Quality(Schema):
    kind: Literal["derived_estimate", "scenario", "qualitative_risk"]
    confidence: None = Field(default=None, description="Reservado: confiança numérica exige método validado.")
    warnings: list[str]
    missing_dates: list[date]


class Traceability(Schema):
    request_id: NonEmpty
    input_references: list[NonEmpty] = Field(min_length=1)


class IndicatorResult(Schema):
    value: float | str | None = Field(description="Ausência permanece null; nunca preencher com zero.")
    unit: NonEmpty
    period: Period
    geography: Geography


class IndicatorResponse(Schema):
    contract_version: Literal["1.0"] = "1.0"
    operation: NonEmpty
    status: Literal["ok"] = "ok"
    result: IndicatorResult
    method: Method
    provenance: list[Provenance] = Field(min_length=1)
    quality: Quality
    limitations: list[NonEmpty] = Field(min_length=1)
    traceability: Traceability
    generated_at: AwareDatetime


class ErrorInfo(Schema):
    code: str
    message: str
    retryable: bool
    details: dict[str, str | int | list[str]] = Field(default_factory=dict)


class ErrorResponse(Schema):
    error: ErrorInfo
