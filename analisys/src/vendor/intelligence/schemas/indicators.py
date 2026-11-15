from datetime import date
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from src.vendor.intelligence.schemas.common import Location, NonEmpty, Period, Schema
from src.vendor.intelligence.schemas.gdd import DailyTemperature, TemperatureC
from src.vendor.intelligence.schemas.rainfall import RainfallRequest  # Re-export preserves existing imports.


class DatedRequest(Schema):
    start_date: date
    end_date: date
    timezone: str = Field(default="UTC", description="Fuso IANA das agregações diárias; calendário gregoriano.")

    @model_validator(mode="after")
    def valid_period(self) -> "DatedRequest":
        Period(start=self.start_date, end=self.end_date, timezone=self.timezone)
        return self


class WeatherRequest(DatedRequest):
    location: Location
    data_kind: Literal["historical", "forecast"] = "historical"


class GDDRequest(WeatherRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "location": {"latitude": -23.5, "longitude": -47.5}, "crop_id": "maize",
        "start_date": "2026-10-01", "end_date": "2026-10-15", "base_temperature_c": 10.0,
        "timezone": "UTC", "data_kind": "historical",
    }]})
    location: Location | None = Field(default=None, description="WGS84; opcional com série própria, obrigatório no modo automático.")
    crop_id: NonEmpty
    base_temperature_c: TemperatureC = Field(description="Temperatura-base explícita em °C; afeta fortemente o resultado. Não inferida pela cultura.")
    base_temperature_reference: NonEmpty | None = None
    data_kind: Literal["historical", "forecast"] = Field(default="historical", description="Somente para futura consulta automática. Na série própria, a natureza é declarada em cada dia.")
    daily_temperatures: list[DailyTemperature] | None = Field(
        default=None, max_length=36600,
        description="Série diária própria em °C, completa no intervalo inclusivo, sem duplicatas. Sem série, modo automático retorna 503 até integrar agrion-data.",
    )

    @model_validator(mode="after")
    def validate_gdd_mode(self) -> "GDDRequest":
        if self.daily_temperatures is None and self.location is None:
            raise ValueError("Location é obrigatório no modo automático.")
        return self


class DrySpellRequest(WeatherRequest):
    rain_threshold_mm: float = Field(ge=0, description="Limiar diário em mm, a versionar no método.")


class ThermalStressRequest(WeatherRequest):
    crop_id: NonEmpty
    growth_stage: NonEmpty
    threshold_catalog_version: NonEmpty


class ETcRequest(WeatherRequest):
    crop_id: NonEmpty
    growth_stage: NonEmpty
    kc_catalog_version: NonEmpty


class WaterBalanceRequest(ETcRequest):
    assumptions_reference: NonEmpty


class SuitabilityRequest(WeatherRequest):
    crop_id: NonEmpty
    requirements_catalog_version: NonEmpty


class SuccessionRequest(Schema):
    previous_crop_id: NonEmpty
    next_crop_id: NonEmpty
    rules_catalog_version: NonEmpty
    context_kind: Literal["simulation", "farmer_declared"]


class PlantingRiskRequest(WeatherRequest):
    crop_id: NonEmpty
    growth_stage: NonEmpty
    rules_catalog_version: NonEmpty


class YieldScenarioRequest(DatedRequest):
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    crop_id: NonEmpty
    scenario_reference: NonEmpty


class MarginRequest(DatedRequest):
    crop_id: NonEmpty
    area_ha: float = Field(gt=0)
    expected_yield_t_per_ha: float = Field(ge=0)
    price_per_t: float = Field(ge=0)
    cost_per_ha: float = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$", description="Código monetário ISO 4217 a confirmar na integração.")
    assumptions_reference: NonEmpty
