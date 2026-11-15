"""Entradas explícitas e resultados dos indicadores com metodologia disponível."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .nasa_schemas import CivilDate
from .vendor.intelligence.schemas.common import Schema, NonEmpty, Period, Geography, Location, Provenance
from .vendor.intelligence.schemas.analysis import IndicatorMetadata as OriginalMetadata
from .vendor.intelligence.schemas.gdd import DailyTemperature, TemperatureC
from .vendor.intelligence.schemas.rainfall import DailyPrecipitation
from .vendor.intelligence.schemas import indicators as original
from .faostat_schemas import PriceSelection, PriceObservation

NonNegative = Annotated[float, Field(strict=True, ge=0)]
SeriesKind = Literal["declared", "simulation", "forecast"]


class IndicatorProvenance(Provenance):
    kind: Literal["observed", "modeled_estimate", "operational_forecast", "scenario", "farmer_declared", "caller_supplied", "catalog_reference"]
    fallback_used: bool = False
    fallback_reasons: list[str] = Field(default_factory=list)
    forecast_basis: str | None = None


class IndicatorMetadata(OriginalMetadata):
    provenance: list[IndicatorProvenance] = Field(min_length=1)


class DrySpellRequest(original.DrySpellRequest):
    start_date: CivilDate
    end_date: CivilDate
    location: Location | None = None
    rain_threshold_mm: NonNegative
    daily_precipitation: list[DailyPrecipitation] | None = Field(default=None, min_length=1, max_length=36600)
    series_kind: SeriesKind = "declared"
    threshold_reference: NonEmpty | None = None


class ThermalRequest(original.ThermalStressRequest):
    start_date: CivilDate
    end_date: CivilDate
    location: Location | None = None
    daily_temperatures: list[DailyTemperature] | None = Field(default=None, min_length=1, max_length=36600)
    lower_threshold_c: TemperatureC | None = None
    upper_threshold_c: TemperatureC | None = None
    threshold_reference: NonEmpty | None = None
    ecocrop_crop_id: str | None = Field(default=None, pattern=r"^ECO_[0-9]+$")
    series_kind: SeriesKind = "declared"

    @model_validator(mode="after")
    def limits(self):
        if self.lower_threshold_c is not None and self.upper_threshold_c is not None and self.lower_threshold_c >= self.upper_threshold_c:
            raise ValueError("Limite inferior deve ser menor que o superior.")
        if self.ecocrop_crop_id and (self.lower_threshold_c is not None or self.upper_threshold_c is not None):
            raise ValueError("Use limites explícitos ou ECOCROP, sem mistura.")
        if (self.lower_threshold_c is not None or self.upper_threshold_c is not None) and not self.threshold_reference:
            raise ValueError("Limites explícitos exigem referência declarada.")
        return self


class EToDay(Schema):
    date: CivilDate
    eto_mm_day: NonNegative


class KcSelection(Schema):
    record_id: NonEmpty
    parameter: Literal["kc_ini", "kc_mid", "kc_end"]


class ETcRequest(original.ETcRequest):
    start_date: CivilDate
    end_date: CivilDate
    location: Location | None = None
    eto_series: list[EToDay] | None = Field(default=None, min_length=1, max_length=36600)
    eto_reference: NonEmpty | None = None
    kc: NonNegative | None = None
    kc_reference: NonEmpty | None = None
    kc_selection: KcSelection | None = None
    series_kind: SeriesKind = "declared"

    @model_validator(mode="after")
    def coefficient(self):
        if self.kc is not None and self.kc_selection is not None:
            raise ValueError("Use Kc explícito ou seleção FAO, sem mistura.")
        if self.kc is not None and not self.kc_reference:
            raise ValueError("Kc explícito exige referência declarada.")
        if self.eto_series is not None and not self.eto_reference:
            raise ValueError("ETo exige origem/método declarados.")
        return self


class WaterFluxDay(Schema):
    date: CivilDate
    precipitation_mm: NonNegative | None = Field(default=None, description="Se omitida em todos os dias, consulta NASA/Meteomatics conforme data_kind; sem mistura de modos.")
    irrigation_mm: NonNegative
    capillary_rise_mm: NonNegative
    runoff_mm: NonNegative
    deep_percolation_mm: NonNegative


class WaterBalanceRequest(ETcRequest):
    assumptions_reference: NonEmpty
    daily_fluxes: list[WaterFluxDay] | None = Field(default=None, min_length=1, max_length=36600)


class MarginRequest(original.MarginRequest):
    area_ha: Annotated[float, Field(strict=True, gt=0)]
    expected_yield_t_per_ha: NonNegative
    price_per_t: NonNegative | None = None
    faostat_price: PriceSelection | None = None
    cost_per_ha: NonNegative
    cost_basis: Literal["declared_costs", "variable_costs"] = Field(default="declared_costs", description="Somente variable_costs permite denominar a saída margem bruta. Não inclui automaticamente custos ausentes.")

    @model_validator(mode="after")
    def price_mode(self):
        if (self.price_per_t is None) == (self.faostat_price is None):
            raise ValueError("Informe price_per_t ou faostat_price, exclusivamente.")
        if self.faostat_price is not None and self.currency != "USD":
            raise ValueError("Preço FAOSTAT automático requer moeda USD; custos também devem ser declarados em USD.")
        return self


class ResultBase(Schema):
    value: float | int
    unit: str
    period: Period
    geography: Geography
    validation_scope: str


class DrySpellDay(Schema):
    date: CivilDate
    precipitation_mm: float
    is_dry: bool
    consecutive_dry_days: int


class DrySpellResult(ResultBase):
    longest_run_days: int
    trailing_run_days: int
    dry_days: int
    rain_threshold_mm: float
    threshold_comparison: Literal["precipitation_mm < rain_threshold_mm"]
    starts_dry: bool
    series: list[DrySpellDay]


class ThermalDay(Schema):
    date: CivilDate
    tmin_c: float
    tmax_c: float
    below_lower: bool
    above_upper: bool


class ThermalResult(ResultBase):
    cold_exposure_days: int
    heat_exposure_days: int
    lower_threshold_c: float | None
    upper_threshold_c: float | None
    threshold_scope: Literal["caller_declared", "ecocrop_general_species_envelope"]
    threshold_reference: str
    crop_id: str
    growth_stage: str
    series: list[ThermalDay]


class ETcDay(Schema):
    date: CivilDate
    eto_mm_day: float
    kc: float
    etc_mm_day: float


class ETcResult(ResultBase):
    kc: float
    kc_reference: str
    crop_id: str
    growth_stage: str
    series: list[ETcDay]


class WaterBalanceDay(Schema):
    date: CivilDate
    precipitation_mm: float
    irrigation_mm: float
    capillary_rise_mm: float
    runoff_mm: float
    deep_percolation_mm: float
    etc_mm_day: float
    storage_change_mm: float
    cumulative_storage_change_mm: float


class WaterBalanceResult(ResultBase):
    series: list[WaterBalanceDay]
    etc_total_mm: float
    interpretation: Literal["storage_change_accounting_not_soil_water_content"]


class MarginResult(ResultBase):
    currency: str
    area_ha: float
    production_t: float
    revenue: float
    declared_costs: float
    margin_per_ha: float
    margin_definition: Literal["revenue_less_declared_costs", "gross_margin_variable_costs"]
    assumptions_reference: str
    price_per_t_used: float | None = None
    faostat_price_record: PriceObservation | None = None
    price_data_sha256: str | None = None


class DrySpellIndicator(DrySpellResult, IndicatorMetadata):
    pass


class ThermalIndicator(ThermalResult, IndicatorMetadata):
    pass


class ETcIndicator(ETcResult, IndicatorMetadata):
    pass


class WaterBalanceIndicator(WaterBalanceResult, IndicatorMetadata):
    pass


class MarginIndicator(MarginResult, IndicatorMetadata):
    pass


class CalculationResponse(IndicatorMetadata):
    contract_version: Literal["1.0"] = "1.0"
    operation: str
    result: DrySpellResult | ThermalResult | ETcResult | WaterBalanceResult | MarginResult
