"""I02 contracts: daily precipitation depths, not hourly rates or multiday totals."""
import re
from datetime import date as Date, timedelta
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from src.vendor.intelligence.schemas.common import IndicatorResponse, IndicatorResult, Location, NonEmpty, Period, Schema


def civil_date(value):
    if type(value) is Date:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return Date.fromisoformat(value)
    raise ValueError("Use uma data civil YYYY-MM-DD sem horário.")


CivilDate = Annotated[Date, BeforeValidator(civil_date)]
DayBasis = Literal["UTC", "LST"]


class DailyPrecipitation(Schema):
    date: CivilDate
    precipitation_mm: float = Field(strict=True, ge=0, description="Lâmina acumulada neste único dia, em mm. Zero é válido. Não é taxa mm/h nem acumulado multidiário.")


class RainfallRequest(Schema):
    reference_date: CivilDate | None = Field(default=None, description="Fim inclusivo comum às quatro janelas retrospectivas.")
    day_basis: DayBasis | None = Field(default=None, description="UTC ou hora solar local (LST), conforme definição da série; nenhuma conversão implícita.")
    daily_precipitation: list[DailyPrecipitation] | None = Field(
        default=None, max_length=36600,
        description="Exige exatamente as 90 datas de reference_date-89 até reference_date. Sem lista, consulta automática pendente retorna 503.",
    )
    location: Location | None = None
    source_reference: NonEmpty | None = Field(default=None, description="Referência declarada pelo solicitante, não verificada.")
    source_kind: Literal["declared", "simulation"] = "declared"

    # Preserve the previous reserved request only for the pending automatic mode.
    start_date: CivilDate | None = Field(default=None, json_schema_extra={"deprecated": True})
    end_date: CivilDate | None = Field(default=None, json_schema_extra={"deprecated": True})
    window_days: Literal[7, 15, 30, 90] | None = Field(default=None, json_schema_extra={"deprecated": True})
    timezone: str | None = Field(default=None, json_schema_extra={"deprecated": True})
    data_kind: Literal["historical", "forecast"] | None = Field(default=None, json_schema_extra={"deprecated": True})

    @model_validator(mode="after")
    def validate_modes(self) -> "RainfallRequest":
        legacy_fields = (self.start_date, self.end_date, self.window_days, self.timezone, self.data_kind)
        if any(value is not None for value in legacy_fields):
            if self.reference_date is not None or self.day_basis is not None or self.daily_precipitation is not None:
                raise ValueError("Não misture campos do request antigo com a série manual ou reference_date/day_basis.")
            if self.start_date is None or self.end_date is None or self.window_days is None or self.location is None:
                raise ValueError("Request antigo exige início, fim, janela e localização.")
            Period(start=self.start_date, end=self.end_date, timezone=self.timezone or "UTC")
            return self
        if self.reference_date is None or self.day_basis is None:
            raise ValueError("Informe reference_date e day_basis.")
        if self.reference_date < Date.min + timedelta(days=89):
            raise ValueError("Reference_date não permite representar a janela de 90 dias.")
        return self


class RainfallWindow(Schema):
    window_days: Literal[7, 15, 30, 90]
    start_date: Date
    end_date: Date
    total_mm: float = Field(ge=0)
    observed_days: int = Field(ge=1, description="Contagem de registros válidos fornecidos; não comprova observação verificada.")
    expected_days: int = Field(ge=1)


class RainfallPeriod(Schema):
    start: Date
    end: Date
    calendar: Literal["gregorian"] = "gregorian"
    day_basis: DayBasis
    timezone: Literal["UTC"] | None = Field(description="UTC quando day_basis=UTC; null em LST, que não é um fuso IANA.")


class RainfallResult(IndicatorResult):
    value: float = Field(ge=0, description="Total da janela de 90 dias; os quatro totais estão em windows.")
    unit: Literal["mm"] = "mm"
    period: RainfallPeriod
    reference_date: Date
    day_basis: DayBasis
    source_type: Literal["caller_supplied"] = "caller_supplied"
    source_kind: Literal["declared", "simulation"]
    source_reference: NonEmpty | None
    windows: list[RainfallWindow] = Field(min_length=4, max_length=4)


class RainfallResponse(IndicatorResponse):
    operation: Literal["calculate_accumulated_rainfall"] = "calculate_accumulated_rainfall"
    result: RainfallResult
