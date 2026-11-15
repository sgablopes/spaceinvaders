"""Extensões aditivas de procedência; contratos manuais anteriores continuam válidos."""
from typing import Literal

from pydantic import Field
from .vendor.intelligence.schemas.common import Provenance

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
from .indicator_schemas import (DrySpellRequest, ThermalRequest, ETcRequest, WaterBalanceRequest, MarginRequest,
    DrySpellIndicator, ThermalIndicator, ETcIndicator, WaterBalanceIndicator, MarginIndicator, IndicatorProvenance)
from .vendor.intelligence.schemas.analysis import (
    WaterInputs as OriginalWaterInputs, WaterRequest as OriginalWaterRequest, WaterResponse as OriginalWaterResponse,
    WaterResult as OriginalWaterResult, EconomicsInputs as OriginalEconomicsInputs, EconomicsRequest as OriginalEconomicsRequest,
    EconomicsResponse as OriginalEconomicsResponse, EconomicsResult as OriginalEconomicsResult,
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
    dry_spell: DrySpellRequest | None = None
    thermal_stress: ThermalRequest | None = None


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
    indicators: dict[Literal["I01", "I02", "I03", "I05"], GDDIndicator | RainfallIndicator | DrySpellIndicator | ThermalIndicator | UnavailableIndicator] = Field(min_length=1)


class ClimateResponse(OriginalClimateResponse):
    result: ClimateResult
    provenance: list[IndicatorProvenance | Provenance] = Field(min_length=1)


class WaterInputs(OriginalWaterInputs):
    crop_evapotranspiration: ETcRequest | None = None
    water_balance: WaterBalanceRequest | None = None


class WaterRequest(OriginalWaterRequest):
    inputs: WaterInputs = Field(default_factory=WaterInputs)


class WaterResult(OriginalWaterResult):
    indicators: dict[Literal["I07", "I08"], ETcIndicator | WaterBalanceIndicator | UnavailableIndicator] = Field(min_length=1)


class WaterResponse(OriginalWaterResponse):
    result: WaterResult
    provenance: list[IndicatorProvenance | Provenance] = Field(min_length=1)


class EconomicsInputs(OriginalEconomicsInputs):
    crop_margin: MarginRequest | None = None


class EconomicsRequest(OriginalEconomicsRequest):
    inputs: EconomicsInputs = Field(default_factory=EconomicsInputs)


class EconomicsResult(OriginalEconomicsResult):
    indicators: dict[Literal["I13", "I14"], MarginIndicator | UnavailableIndicator] = Field(min_length=1)


class EconomicsResponse(OriginalEconomicsResponse):
    result: EconomicsResult
    provenance: list[IndicatorProvenance | Provenance] = Field(min_length=1)
