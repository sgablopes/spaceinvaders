"""Four domain tools. Only inputs for selected indicators are required."""
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from src.vendor.intelligence.schemas.common import ErrorInfo, Method, NonEmpty, Provenance, Quality, Schema, Traceability
from src.vendor.intelligence.schemas.gdd import GDDResult
from src.vendor.intelligence.schemas.rainfall import RainfallRequest, RainfallResult
from src.vendor.intelligence.schemas.indicators import (
    GDDRequest, DrySpellRequest, ThermalStressRequest, ETcRequest, WaterBalanceRequest,
    SuitabilityRequest, SuccessionRequest, PlantingRiskRequest, YieldScenarioRequest, MarginRequest,
)


class Selection(Schema):
    include: list[str]

    @model_validator(mode="after")
    def unique_selection(self):
        if len(self.include) != len(set(self.include)):
            raise ValueError("Não repita IDs em include.")
        return self


class ClimateInputs(Schema):
    gdd: GDDRequest | None = Field(default=None, description="Entradas I01; necessárias somente se include contém I01.")
    rainfall: RainfallRequest | None = Field(default=None, description="Entradas I02; independentes das temperaturas e da Tbase de I01.")
    dry_spell: DrySpellRequest | None = None
    thermal_stress: ThermalStressRequest | None = None


class WaterInputs(Schema):
    crop_evapotranspiration: ETcRequest | None = None
    water_balance: WaterBalanceRequest | None = None


class AgronomyInputs(Schema):
    climate_suitability: SuitabilityRequest | None = Field(default=None, description="I09; não exige culturas de sucessão de I10.")
    crop_succession: SuccessionRequest | None = None
    planting_risk: PlantingRiskRequest | None = None


class EconomicsInputs(Schema):
    yield_scenario: YieldScenarioRequest | None = None
    crop_margin: MarginRequest | None = None


class ClimateRequest(Selection):
    include: list[Literal["I01", "I02", "I03", "I05"]] = Field(min_length=1, max_length=4)
    inputs: ClimateInputs = Field(default_factory=ClimateInputs)


class WaterRequest(Selection):
    include: list[Literal["I07", "I08"]] = Field(min_length=1, max_length=2)
    inputs: WaterInputs = Field(default_factory=WaterInputs)


class AgronomyRequest(Selection):
    include: list[Literal["I09", "I10", "I11"]] = Field(min_length=1, max_length=3)
    inputs: AgronomyInputs = Field(default_factory=AgronomyInputs)


class EconomicsRequest(Selection):
    include: list[Literal["I13", "I14"]] = Field(min_length=1, max_length=2)
    inputs: EconomicsInputs = Field(default_factory=EconomicsInputs)


class IndicatorMetadata(Schema):
    status: Literal["ok"] = "ok"
    method: Method
    provenance: list[Provenance] = Field(min_length=1)
    quality: Quality
    limitations: list[NonEmpty] = Field(min_length=1)
    traceability: Traceability
    generated_at: AwareDatetime


class GDDAnalysisIndicator(GDDResult, IndicatorMetadata):
    """Existing GDD result fields, enriched with its own full metadata."""


class RainfallAnalysisIndicator(RainfallResult, IndicatorMetadata):
    """Existing rainfall result fields, enriched with its own full metadata."""


class UnavailableIndicator(Schema):
    status: Literal["unavailable", "not_implemented"]
    reason: NonEmpty
    error: ErrorInfo


class ClimateResult(Schema):
    indicators: dict[Literal["I01", "I02", "I03", "I05"], GDDAnalysisIndicator | RainfallAnalysisIndicator | UnavailableIndicator] = Field(min_length=1)


class WaterResult(Schema):
    indicators: dict[Literal["I07", "I08"], UnavailableIndicator] = Field(min_length=1)


class AgronomyResult(Schema):
    indicators: dict[Literal["I09", "I10", "I11"], UnavailableIndicator] = Field(min_length=1)


class EconomicsResult(Schema):
    indicators: dict[Literal["I13", "I14"], UnavailableIndicator] = Field(min_length=1)


class AnalysisResponse(Schema):
    contract_version: Literal["1.0"] = "1.0"
    operation: Literal["analyze_climate", "analyze_water", "analyze_agronomy", "analyze_economics"]
    status: Literal["ok", "partial"]
    method: Method
    provenance: list[Provenance] = Field(min_length=1)
    quality: Quality
    limitations: list[NonEmpty] = Field(min_length=1)
    traceability: Traceability
    generated_at: AwareDatetime


class ClimateResponse(AnalysisResponse):
    operation: Literal["analyze_climate"] = "analyze_climate"
    result: ClimateResult


class WaterResponse(AnalysisResponse):
    operation: Literal["analyze_water"] = "analyze_water"
    result: WaterResult


class AgronomyResponse(AnalysisResponse):
    operation: Literal["analyze_agronomy"] = "analyze_agronomy"
    result: AgronomyResult


class EconomicsResponse(AnalysisResponse):
    operation: Literal["analyze_economics"] = "analyze_economics"
    result: EconomicsResult
