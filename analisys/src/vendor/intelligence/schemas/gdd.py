import re
from datetime import date as Date
from typing import Annotated, Literal

from pydantic import Field, field_validator

from src.vendor.intelligence.schemas.common import IndicatorResponse, IndicatorResult, NonEmpty, Schema

# Broad input sanity bounds, not agronomic cutoffs. They reject absence sentinels
# such as -999 without clipping or modifying accepted temperatures.
TemperatureC = Annotated[float, Field(strict=True, ge=-100, le=100)]
DeclaredDataKind = Literal["observation", "forecast", "simulation", "unspecified"]


class DailyTemperature(Schema):
    date: Date = Field(description="Dia civil ISO YYYY-MM-DD no fuso declarado; não aceita horário.")
    tmin_c: TemperatureC
    tmax_c: TemperatureC
    data_kind: DeclaredDataKind = "unspecified"
    source_reference: NonEmpty | None = Field(default=None, description="Referência declarada pelo caller, não verificada.")

    @field_validator("date", mode="before")
    @classmethod
    def daily_date_only(cls, value):
        if type(value) is Date:
            return value
        if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return Date.fromisoformat(value)
        raise ValueError("Use uma data diária YYYY-MM-DD sem horário.")


class GDDDay(Schema):
    date: Date
    tmin_c: float
    tmax_c: float
    tmean_c: float
    gdd_daily: float = Field(ge=0)
    gdd_cumulative: float = Field(ge=0)
    unit: Literal["degree_day_c"] = "degree_day_c"
    data_kind: DeclaredDataKind
    source_reference: NonEmpty | None


class GDDResult(IndicatorResult):
    value: float = Field(ge=0)
    unit: Literal["degree_day_c"] = "degree_day_c"
    crop_id: NonEmpty
    base_temperature_c: float
    base_temperature_reference: NonEmpty | None
    days_expected: int = Field(ge=1)
    days_received: int = Field(ge=1)
    days_valid: int = Field(ge=1)
    series: list[GDDDay] = Field(min_length=1)


class GDDResponse(IndicatorResponse):
    operation: Literal["calculate_gdd"] = "calculate_gdd"
    result: GDDResult
