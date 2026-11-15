"""Contrato INT S01: série diária histórica, nunca forecast."""
from datetime import date, datetime, timezone
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Parameter = Literal["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN"]
PARAMETERS = {
    "T2M": ("tmean_c", "C"), "T2M_MAX": ("tmax_c", "C"), "T2M_MIN": ("tmin_c", "C"),
    "PRECTOTCORR": ("precip_mm_day", "mm/day"), "RH2M": ("relative_humidity_pct", "%"),
    "ALLSKY_SFC_SW_DWN": ("solar_radiation_mj_m2_day", "MJ/m^2/day"),
}


def civil_date(value):
    if type(value) is date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value)
    raise ValueError("Informe data civil YYYY-MM-DD, sem horário.")


CivilDate = Annotated[date, BeforeValidator(civil_date)]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Location(Schema):
    latitude: float = Field(strict=True, ge=-90, le=90, description="WGS84 em graus decimais.")
    longitude: float = Field(strict=True, ge=-180, le=180, description="WGS84 em graus decimais.")


class DailyRequest(Schema):
    location: Location
    start_date: CivilDate
    end_date: CivilDate
    parameters: list[Parameter] = Field(default_factory=lambda: list(PARAMETERS), min_length=1, max_length=6)
    time_standard: Literal["UTC", "LST"] = Field(default="UTC", description="Dia da fonte; LST é hora solar, não fuso IANA. Sem conversão entre bases.")
    require_complete: bool = Field(default=False, strict=True, description="Se true, lacunas retornam 404. Caso contrário, null e status partial.")

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end_date < self.start_date:
            raise ValueError("Intervalo invertido.")
        if self.start_date < date(1981, 1, 1):
            raise ValueError("NASA POWER diário: início não pode anteceder 1981-01-01.")
        if self.end_date > datetime.now(timezone.utc).date():
            raise ValueError("Este conector não fornece forecast nem datas futuras.")
        if (self.end_date - self.start_date).days >= 366:
            raise ValueError("Máximo de 366 dias inclusivos por consulta.")
        if len(set(self.parameters)) != len(self.parameters):
            raise ValueError("Parâmetros duplicados.")
        return self


class DailyRow(Schema):
    date: date
    tmean_c: float | None = None
    tmax_c: float | None = None
    tmin_c: float | None = None
    precip_mm_day: float | None = None
    relative_humidity_pct: float | None = None
    solar_radiation_mj_m2_day: float | None = None
    missing_parameters: list[Parameter]


class ParameterMetadata(Schema):
    field: str
    unit: str
    source_unit: str
    long_name: str


class Period(Schema):
    start: date
    end: date
    calendar: Literal["gregorian"] = "gregorian"
    time_standard: Literal["UTC", "LST"]
    timezone: Literal["UTC"] | None


class DailyResult(Schema):
    location: Location
    period: Period
    parameters: dict[str, ParameterMetadata]
    days_expected: int
    days_complete: int
    series: list[DailyRow]


class NasaProvenance(Schema):
    provider: Literal["NASA POWER"] = "NASA POWER"
    dataset: list[str]
    source_url: str
    accessed_at: datetime
    api_version: str | None
    source_geometry: dict[str, Any]
    spatial_resolution: str
    temporal_resolution: Literal["daily"] = "daily"
    kind: Literal["modeled_estimate"] = "modeled_estimate"
    license: str | None = None
    documentation_url: str


class Quality(Schema):
    kind: Literal["modeled_estimate"] = "modeled_estimate"
    confidence: None = None
    missing_dates: dict[str, list[date]]
    warnings: list[str]


class Method(Schema):
    category: Literal["INT"] = "INT"
    name: Literal["nasa_power_daily_normalization"] = "nasa_power_daily_normalization"
    version: Literal["1.0"] = "1.0"
    assumptions: list[str]


class CacheInfo(Schema):
    hit: bool
    ttl_seconds: int
    expires_at: datetime


class Traceability(Schema):
    request_id: str
    input_sha256: str
    upstream_sha256: str


class DailyResponse(Schema):
    contract_version: Literal["1.0"] = "1.0"
    operation: Literal["get_nasa_power_daily_weather"] = "get_nasa_power_daily_weather"
    status: Literal["ok", "partial"]
    result: DailyResult
    method: Method
    provenance: list[NasaProvenance]
    quality: Quality
    limitations: list[str]
    cache: CacheInfo
    traceability: Traceability
    generated_at: datetime


class ErrorInfo(Schema):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any]


class ErrorResponse(Schema):
    error: ErrorInfo
