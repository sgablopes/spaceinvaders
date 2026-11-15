"""Contrato comum aditivo; o endpoint Meteomatics original mantém seu contrato."""
from typing import Literal
from pydantic import AwareDatetime, Field
from .meteomatics_schemas import ForecastRequest, ForecastResponse, ForecastProvenance, ForecastMethod
from .nasa_schemas import Schema


class WeatherRequest(ForecastRequest):
    provider: Literal["auto", "meteomatics", "open_meteo"] = "auto"


class WeatherProvenance(ForecastProvenance):
    provider: Literal["Meteomatics", "Open-Meteo"]
    provider_generated_at: AwareDatetime | None = None
    license: str | None = None
    grid_latitude: float | None = None
    grid_longitude: float | None = None
    elevation_m: float | None = None


class WeatherMethod(ForecastMethod):
    name: Literal["meteomatics_forecast_normalization", "open_meteo_forecast_normalization"]


class ProviderFailure(Schema):
    provider: Literal["Meteomatics", "Open-Meteo"]
    code: str
    http_status: int


class WeatherResponse(ForecastResponse):
    operation: Literal["get_weather_forecast"] = "get_weather_forecast"
    method: WeatherMethod
    provenance: list[WeatherProvenance] = Field(min_length=1)
    provider_requested: Literal["auto", "meteomatics", "open_meteo"] = "auto"
    provider_used: Literal["Meteomatics", "Open-Meteo"]
    fallback_used: bool = False
    provider_failures: list[ProviderFailure] = Field(default_factory=list)
