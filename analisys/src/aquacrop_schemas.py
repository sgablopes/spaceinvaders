"""Uma safra explícita, sem inventar solo, manejo ou meteorologia."""
from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal
from pydantic import Field, model_validator
from .nasa_schemas import Schema, Location, CivilDate

Reference = Annotated[str, Field(min_length=1, max_length=500)]
NonNegative = Annotated[float, Field(strict=True, ge=0)]


class WeatherDay(Schema):
    date: CivilDate
    tmin_c: Annotated[float, Field(strict=True, ge=-100, le=100)]
    tmax_c: Annotated[float, Field(strict=True, ge=-100, le=100)]
    precipitation_mm: NonNegative
    eto_mm_day: Annotated[float, Field(strict=True, ge=0.1, le=50)]

    @model_validator(mode="after")
    def temperatures(self):
        if self.tmin_c > self.tmax_c:
            raise ValueError("Tmin maior que Tmax.")
        return self


class WeatherInput(Schema):
    source: Literal["nasa_power", "caller_supplied"]
    time_standard: Literal["UTC"] = "UTC"
    reference: Reference
    daily: list[WeatherDay] | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def mode(self):
        if (self.source == "caller_supplied") != (self.daily is not None):
            raise ValueError("Série própria exige daily; NASA não aceita mistura com daily.")
        return self


class SoilInput(Schema):
    preset: Literal["SandyLoam", "Loam"]
    depth_m: Annotated[float, Field(strict=True, ge=2.4, le=3, description="2.4–3 m para impedir que o motor estenda silenciosamente o perfil do Maize de biblioteca.")]
    reference: Reference
    kind: Literal["assumed_engine_preset"]


class InitialWater(Schema):
    method: Literal["FC", "WP", "SAT"]
    reference: Reference
    kind: Literal["assumed"]


class CO2Input(Schema):
    concentration_ppm: Annotated[float, Field(strict=True, ge=250, le=1000)]
    reference: Reference


class Management(Schema):
    irrigation: Literal["rainfed"]
    reference: Reference


class SimulationRequest(Schema):
    scenario_id: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")]
    start_date: CivilDate
    end_date: CivilDate
    crop: Literal["Maize"]
    location: Location
    weather: WeatherInput
    soil: SoilInput
    initial_water: InitialWater
    co2: CO2Input
    management: Management
    assumptions_reference: Reference
    elevation_m: Annotated[float, Field(strict=True, ge=-400, le=5000)] | None = None
    timezone: Literal["UTC"] = "UTC"

    @model_validator(mode="after")
    def period(self):
        if not 1 <= (self.end_date - self.start_date).days + 1 <= 300:
            raise ValueError("Uma safra, 1 a 300 dias inclusivos; plantio no primeiro dia.")
        if self.start_date < date(1981, 1, 1):
            raise ValueError("Período deve começar a partir de 1981.")
        if (self.start_date.month, self.start_date.day) == (2, 29):
            raise ValueError("Plantio em 29/02 não é suportado pelo calendário de referência deste motor.")
        if self.weather.source == "nasa_power" and self.end_date > datetime.now(timezone.utc).date():
            raise ValueError("NASA POWER é histórica; não completa safra futura com valores fictícios.")
        if self.weather.daily is not None:
            days = [r.date for r in self.weather.daily]
            if len(days) != (self.end_date - self.start_date).days + 1 or len(set(days)) != len(days) or min(days) != self.start_date or max(days) != self.end_date:
                raise ValueError("Clima deve cobrir exatamente todos os dias, sem lacunas/duplicatas/datas externas.")
        return self


class EngineInfo(Schema):
    name: Literal["AquaCrop-OSPy"]
    version: Literal["3.0.12"]
    official_fao_7_3: Literal[False]
    numpy_version: str
    pandas_version: str
    source_sha256: str
    parameters_sha256: str


class WaterBalance(Schema):
    precipitation_mm: NonNegative
    irrigation_mm: NonNegative
    evaporation_mm: NonNegative
    transpiration_mm: NonNegative
    runoff_mm: NonNegative
    deep_percolation_mm: NonNegative
    capillary_rise_mm: NonNegative
    groundwater_inflow_mm: NonNegative
    initial_soil_water_mm: NonNegative
    final_soil_water_mm: NonNegative
    final_surface_storage_mm: NonNegative
    residual_mm: float
    tolerance_mm: Literal[0.0001]


class SimulationDay(Schema):
    date: CivilDate
    eto_mm_day: NonNegative
    soil_water_mm: NonNegative
    surface_storage_mm: NonNegative
    precipitation_mm: NonNegative
    irrigation_mm: NonNegative
    evaporation_mm: NonNegative
    transpiration_mm: NonNegative
    runoff_mm: NonNegative
    deep_percolation_mm: NonNegative
    capillary_rise_mm: NonNegative
    groundwater_inflow_mm: NonNegative
    canopy_cover_fraction: float = Field(ge=0, le=1)
    root_depth_m: NonNegative
    water_balance_residual_mm: float


class SimulationResult(Schema):
    simulated_days: int = Field(ge=1, le=300)
    last_simulated_date: CivilDate
    harvest_timestamp_engine: str
    crop_mature: bool
    crop_dead: bool
    dry_yield_t_ha: NonNegative = Field(description="Produtividade seca simulada; t/ha, não colheita observada.")
    fresh_yield_t_ha: NonNegative = Field(description="Produtividade fresca simulada conforme YldWC do parâmetro da cultura; t/ha.")
    water_balance: WaterBalance
    daily: list[SimulationDay] = Field(min_length=1, max_length=300)


class SimulationResponse(Schema):
    contract_version: Literal["1.0"] = "1.0"
    operation: Literal["simulate_aquacrop"] = "simulate_aquacrop"
    status: Literal["ok"] = "ok"
    scenario_id: str
    engine: EngineInfo
    result: SimulationResult
    weather: list[WeatherDay]
    inputs: dict[str, Any]
    provenance: list[dict[str, Any]]
    method: dict[str, Any]
    quality: dict[str, Any]
    limitations: list[str]
    traceability: dict[str, Any]
