"""Previsão por instante/intervalo; não é histórico NASA nem série diária inferida."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import AwareDatetime, BeforeValidator, Field, field_validator, model_validator

from .nasa_schemas import Schema, Location, CacheInfo, Traceability, ErrorResponse

Parameter = Literal["temperature", "temperature_mean", "temperature_min", "temperature_max", "precipitation", "relative_humidity", "wind_speed", "solar_radiation"]
PARAMETERS = {
    "temperature": ("t_2m:C", "temperature_c", "C", "instantaneous"),
    "temperature_mean": ("t_mean_2m_{hours}h:C", "temperature_mean_c", "C", "mean_over_interval"),
    "temperature_min": ("t_min_2m_{hours}h:C", "temperature_min_c", "C", "minimum_over_interval"),
    "temperature_max": ("t_max_2m_{hours}h:C", "temperature_max_c", "C", "maximum_over_interval"),
    "precipitation": ("precip_{hours}h:mm", "precipitation_mm", "mm", "sum_over_interval"),
    "relative_humidity": ("relative_humidity_2m:p", "relative_humidity_pct", "%", "instantaneous"),
    "wind_speed": ("wind_speed_10m:ms", "wind_speed_10m_m_s", "m/s", "instantaneous"),
    "solar_radiation": ("global_rad:W", "solar_radiation_w_m2", "W/m²", "instantaneous"),
}


def iso_timestamp(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and "T" in value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("Informe um timestamp ISO 8601 com fuso, sem epoch numérico.")


Timestamp = Annotated[AwareDatetime, BeforeValidator(iso_timestamp)]


class ForecastRequest(Schema):
    location: Location
    start_time: Timestamp
    end_time: Timestamp
    step_hours: Literal[1, 3, 6, 24] = Field(default=1, description="Resolução solicitada. Acumulados e extremos usam este mesmo intervalo, encerrado no horário de validade.")
    parameters: list[Parameter] = Field(default_factory=lambda: ["temperature", "precipitation", "relative_humidity", "wind_speed"], min_length=1, max_length=8)
    source: Literal["mix", "ecmwf-ifs", "ncep-gfs"] = Field(default="mix", description="Fonte solicitada; modelo, horizonte e parâmetros dependem da permissão da conta.")
    require_complete: bool = Field(default=False, strict=True)

    @field_validator("step_hours", mode="before")
    @classmethod
    def integer_step(cls, value):
        if type(value) is not int:
            raise ValueError("step_hours deve ser inteiro JSON, não booleano ou texto.")
        return value

    @model_validator(mode="after")
    def interval(self):
        self.start_time = self.start_time.astimezone(timezone.utc)
        self.end_time = self.end_time.astimezone(timezone.utc)
        if self.end_time < self.start_time:
            raise ValueError("Intervalo invertido.")
        if any(t.minute or t.second or t.microsecond for t in (self.start_time, self.end_time)):
            raise ValueError("Use horários alinhados à hora inteira.")
        duration = self.end_time - self.start_time
        if duration > timedelta(days=16) or duration.total_seconds() % (self.step_hours * 3600):
            raise ValueError("Até 16 dias e intervalo divisível por step_hours.")
        if len(set(self.parameters)) != len(self.parameters):
            raise ValueError("Parâmetros duplicados.")
        return self


class ForecastRow(Schema):
    valid_time: AwareDatetime
    interval_start: AwareDatetime | None
    temperature_c: float | None = None
    temperature_mean_c: float | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    precipitation_mm: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_10m_m_s: float | None = None
    solar_radiation_w_m2: float | None = None
    missing_parameters: list[Parameter]


class ForecastParameter(Schema):
    provider_parameter: str
    field: str
    unit: str
    temporal_semantics: str
    interval_hours: int | None


class ForecastResult(Schema):
    location: Location
    start_time: AwareDatetime
    end_time: AwareDatetime
    time_standard: Literal["UTC"] = "UTC"
    step_hours: int
    points_expected: int
    points_complete: int
    available_end_by_parameter: dict[str, AwareDatetime | None]
    parameters: dict[str, ForecastParameter]
    series: list[ForecastRow]


class ForecastProvenance(Schema):
    provider: Literal["Meteomatics"] = "Meteomatics"
    kind: Literal["operational_forecast"] = "operational_forecast"
    source_url: str
    source_requested: str
    api_version: str
    upstream_http_status: Literal[200, 206] = 200
    provider_generated_at: AwareDatetime
    forecast_reference_time: None = Field(default=None, description="Não foi consultado get_init_date; dateGenerated não é identificado como horário de inicialização do modelo.")
    accessed_at: AwareDatetime
    spatial_resolution: str
    license: None = None
    documentation_url: str


class ForecastQuality(Schema):
    kind: Literal["operational_forecast"] = "operational_forecast"
    confidence: None = None
    missing_times: dict[str, list[AwareDatetime]]
    warnings: list[str]


class ForecastMethod(Schema):
    category: Literal["INT"] = "INT"
    name: Literal["meteomatics_forecast_normalization"] = "meteomatics_forecast_normalization"
    version: Literal["1.0"] = "1.0"
    assumptions: list[str]


class ForecastResponse(Schema):
    contract_version: Literal["1.0"] = "1.0"
    operation: Literal["get_meteomatics_forecast"] = "get_meteomatics_forecast"
    status: Literal["ok", "partial"]
    result: ForecastResult
    method: ForecastMethod
    provenance: list[ForecastProvenance]
    quality: ForecastQuality
    limitations: list[str]
    cache: CacheInfo
    traceability: Traceability
    generated_at: AwareDatetime
