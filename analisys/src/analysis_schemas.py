"""Extensões aditivas de procedência; contratos manuais anteriores continuam válidos."""
from typing import Literal

from pydantic import Field

from .vendor.intelligence.schemas.analysis import (
    ClimateRequest as OriginalClimateRequest, ClimateInputs as OriginalClimateInputs,
    ClimateResponse as OriginalClimateResponse, ClimateResult as OriginalClimateResult,
    IndicatorMetadata, UnavailableIndicator,
)
from .vendor.intelligence.schemas.gdd import GDDDay, GDDResult, GDDResponse, DailyTemperature
from .vendor.intelligence.schemas.indicators import GDDRequest as OriginalGDDRequest
from .vendor.intelligence.schemas.rainfall import (
    RainfallRequest as OriginalRainfallRequest, RainfallResult, RainfallResponse, DailyPrecipitation,
)


class GDDRequest(OriginalGDDRequest):
    daily_temperatures: list[DailyTemperature] | None = Field(default=None, max_length=36600,
        description="Série própria completa em °C, sem chamadas externas. Se omitida, consulta NASA POWER: location, período histórico até 366 dias, timezone UTC e Tbase explícita são obrigatórios.")
    data_kind: Literal["historical", "forecast"] = Field(default="historical",
        description="No automático, somente historical está disponível. Não determina a natureza dos dias da série manual.")


class RainfallRequest(OriginalRainfallRequest):
    daily_precipitation: list[DailyPrecipitation] | None = Field(default=None, max_length=36600,
        description="Série própria de 90 dias em mm. Se omitida, NASA POWER obtém reference_date-89 até reference_date, com location e day_basis UTC/LST. Formato legado reservado continua 503; use reference_date/day_basis.")


class ClimateInputs(OriginalClimateInputs):
    gdd: GDDRequest | None = None
    rainfall: RainfallRequest | None = None


class ClimateRequest(OriginalClimateRequest):
    inputs: ClimateInputs = Field(default_factory=ClimateInputs)


class NasaGDDDay(GDDDay):
    data_kind: Literal["observation", "forecast", "simulation", "unspecified", "modeled_estimate"]


class IntegratedGDDResult(GDDResult):
    series: list[NasaGDDDay] = Field(min_length=1)


class IntegratedGDDResponse(GDDResponse):
    result: IntegratedGDDResult


class IntegratedRainfallResult(RainfallResult):
    source_type: Literal["caller_supplied", "nasa_power"] = "caller_supplied"
    source_kind: Literal["declared", "simulation", "modeled_estimate"]


class IntegratedRainfallResponse(RainfallResponse):
    result: IntegratedRainfallResult


class GDDIndicator(IntegratedGDDResult, IndicatorMetadata):
    pass


class RainfallIndicator(IntegratedRainfallResult, IndicatorMetadata):
    pass


class ClimateResult(OriginalClimateResult):
    indicators: dict[Literal["I01", "I02", "I03", "I05"], GDDIndicator | RainfallIndicator | UnavailableIndicator] = Field(min_length=1)


class ClimateResponse(OriginalClimateResponse):
    result: ClimateResult
