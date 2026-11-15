"""Indicadores determinísticos: métodos explícitos, sem parâmetros agronômicos inferidos."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import math
from types import SimpleNamespace

from .indicator_schemas import CalculationResponse, DrySpellResult, ThermalResult, ETcResult, WaterBalanceResult, MarginResult
from .indicator_weather import full_series, weather, supplied_source
from .indicator_catalogs import ecocrop_limits, fao_kc
from .vendor.intelligence.core.errors import ServiceError

CLIMDEX = "https://climate-scenarios.canada.ca/?page=climdex-indices"
FAO_ETC = "https://www.fao.org/4/X0490E/x0490e0b.htm"
FAO_BALANCE = "https://www.fao.org/4/X0490E/x0490e0e.htm"
FAO_MARGIN = "https://www.fao.org/4/i3228e/i3228e.pdf"


def finite(value):
    if not math.isfinite(value):
        raise ServiceError(422, "NUMERIC_RANGE_ERROR", "Resultado excede a faixa numérica suportada.")
    return value


def total(values):
    try:
        return finite(math.fsum(values))
    except (OverflowError, ValueError):
        raise ServiceError(422, "NUMERIC_RANGE_ERROR", "Soma excede a faixa numérica suportada.") from None


def base(payload, value, unit, scope):
    return {"value": value, "unit": unit, "period": {"start": payload.start_date, "end": payload.end_date, "timezone": payload.timezone},
        "geography": {"location": payload.location, "scope": "declared_or_source_regional_context"}, "validation_scope": scope}


def response(operation, payload, result, result_type, request_id, method, source, assumptions, limitations, *, extras=None, hashes=None):
    now = datetime.now(timezone.utc)
    scenario = (getattr(payload, "series_kind", "declared") in {"simulation", "forecast"}
        or getattr(payload, "data_kind", "historical") == "forecast"
        or any(getattr(r, "data_kind", "unspecified") in {"simulation", "forecast"} for r in (getattr(payload, "daily_temperatures", None) or []))
        or any(p["kind"] == "operational_forecast" for p in source) or operation == "estimate_crop_margin")
    return CalculationResponse(operation=operation, result=result_type.model_validate(result),
        method={"category": "IND", "name": method, "version": "1.0", "assumptions": assumptions}, provenance=source + (extras or []),
        quality={"kind": "scenario" if scenario else "derived_estimate", "confidence": None,
            "warnings": ["Resultado condicionado às entradas e referências declaradas; não equivale a recomendação agronômica.",
                         "Séries fornecidas como forecast/simulação não são previsões verificadas pelo serviço."] if scenario else ["Dados regionais e limites gerais não comprovam condições ou danos no talhão."], "missing_dates": []},
        limitations=limitations, generated_at=now, traceability={"request_id": request_id,
            "input_references": ["sha256:" + hashlib.sha256(payload.model_dump_json().encode()).hexdigest(), *(hashes or [])]})


def catalog_source(source, dataset, url):
    return {"provider": "local_agronomic_catalog", "dataset": dataset[:200], "source_url": url,
        "accessed_at": datetime.now(timezone.utc), "spatial_resolution": "General reference; not field-calibrated",
        "temporal_resolution": None, "license": None, "kind": "catalog_reference"}


def precipitation(payload, nasa, meteomatics):
    if payload.daily_precipitation is not None:
        return full_series(payload, payload.daily_precipitation), supplied_source(), []
    rows, source, digest = weather(payload, nasa, meteomatics)
    return full_series(payload, [SimpleNamespace(**r) for r in rows]), source, ["weather-sha256:" + digest]


def dry_spell(nasa, meteomatics, payload, request_id):
    records, source, hashes = precipitation(payload, nasa, meteomatics)
    running, longest, dry_count, series = 0, 0, 0, []
    for record in records:
        dry = record.precipitation_mm < payload.rain_threshold_mm
        running = running + 1 if dry else 0
        longest = max(longest, running)
        dry_count += dry
        series.append({"date": record.date, "precipitation_mm": record.precipitation_mm, "is_dry": dry, "consecutive_dry_days": running})
    result = {**base(payload, longest, "day", "complete_window_dry_run_not_drought_risk"),
        "longest_run_days": longest, "trailing_run_days": running, "dry_days": dry_count,
        "rain_threshold_mm": payload.rain_threshold_mm, "threshold_comparison": "precipitation_mm < rain_threshold_mm",
        "starts_dry": series[0]["is_dry"], "series": series}
    return response("calculate_dry_spell", payload, result, DrySpellResult, request_id, "maximum_consecutive_days_below_explicit_threshold", [source],
        [f"Dia seco: precipitação < {payload.rain_threshold_mm} mm; igualdade encerra a sequência.",
         "Limite de 1 mm reproduz a condição CDD Climdex; outros limites são escolhas explícitas, não CDD padrão.", CLIMDEX],
        ["Contagem limitada ao período; sequências podem continuar fora da janela.", "Não estima risco de seca nem necessidade de irrigação."], hashes=hashes)


def thermal(nasa, meteomatics, store, payload, request_id):
    lower, upper, reference, scope = payload.lower_threshold_c, payload.upper_threshold_c, payload.threshold_reference, "caller_declared"
    extra, hashes = [], []
    if payload.ecocrop_crop_id:
        lower, upper, url, source, name = ecocrop_limits(store, payload.ecocrop_crop_id)
        reference, scope = f"{payload.ecocrop_crop_id}: {name}; limites absolutos gerais", "ecocrop_general_species_envelope"
        extra.append(catalog_source(source, reference, url))
        hashes.append("ecocrop-sha256:" + source["sha256"])
    if lower is None and upper is None:
        raise ServiceError(503, "THRESHOLD_CATALOG_PENDING", "Informe limites explícitos com referência ou um ID ECOCROP; não há limiar universal por estádio.")
    if payload.daily_temperatures is not None:
        rows, source = full_series(payload, payload.daily_temperatures), supplied_source()
    else:
        data, source, digest = weather(payload, nasa, meteomatics, temperature=True)
        rows = full_series(payload, [SimpleNamespace(**r) for r in data])
        hashes.append("weather-sha256:" + digest)
    series = []
    for row in rows:
        if row.tmin_c > row.tmax_c:
            raise ServiceError(422, "VALIDATION_ERROR", "Tmin maior que Tmax.")
        series.append({"date": row.date, "tmin_c": row.tmin_c, "tmax_c": row.tmax_c,
            "below_lower": lower is not None and row.tmin_c < lower, "above_upper": upper is not None and row.tmax_c > upper})
    result = {**base(payload, sum(r["below_lower"] or r["above_upper"] for r in series), "day", "threshold_exposure_screening_not_damage_prediction"),
        "cold_exposure_days": sum(r["below_lower"] for r in series), "heat_exposure_days": sum(r["above_upper"] for r in series),
        "lower_threshold_c": lower, "upper_threshold_c": upper, "threshold_scope": scope, "threshold_reference": reference,
        "crop_id": payload.crop_id, "growth_stage": payload.growth_stage, "series": series}
    return response("assess_thermal_stress", payload, result, ThermalResult, request_id, "daily_temperature_threshold_exposure", [source],
        ["Conta dias com Tmin < limite inferior ou Tmax > superior; igualdade não excede a faixa.",
         "Limites não são inferidos a partir do nome da cultura ou do estádio."],
        ["Exposição fora de limites não diagnostica dano ou perda de produtividade.", "ECOCROP oferece limites gerais da espécie; não calibração por estádio/cultivar."], extras=extra, hashes=hashes)


def etc_values(store, payload):
    if payload.eto_series is None:
        raise ServiceError(503, "ETO_SOURCE_PENDING", "Informe ETo diária em mm/dia e sua referência; o serviço não calcula ETo nem a substitui por radiação.")
    rows = full_series(payload, payload.eto_series)
    extra, hashes = [], []
    kc, reference = payload.kc, payload.kc_reference
    if payload.kc_selection is not None:
        kc, reference, source, crop, qa = fao_kc(store, payload.kc_selection)
        extra.append(catalog_source(source, f"FAO-56 {crop}: {reference}", "https://doi.org/10.4060/cd6621en"))
        hashes.append("fao56-sha256:" + source["sha256"])
    if kc is None:
        raise ServiceError(503, "KC_SELECTION_PENDING", "Informe Kc com referência ou ID/parâmetro escalar FAO; não há seleção automática por cultura/estádio.")
    values = [{"date": row.date, "eto_mm_day": row.eto_mm_day, "kc": kc, "etc_mm_day": finite(row.eto_mm_day * kc)} for row in rows]
    return values, kc, reference, extra, hashes


def etc(store, payload, request_id):
    values, kc, reference, extra, hashes = etc_values(store, payload)
    result = {**base(payload, total(r["etc_mm_day"] for r in values), "mm", "standard_conditions_etc_from_declared_eto_and_selected_kc"),
        "kc": kc, "kc_reference": reference, "crop_id": payload.crop_id, "growth_stage": payload.growth_stage, "series": values}
    return response("calculate_crop_evapotranspiration", payload, result, ETcResult, request_id, "fao56_single_coefficient_etc", [supplied_source(payload.eto_reference)],
        ["ETc = Kc × ETo; mesmo Kc explícito/selecionado ao longo deste período/estádio declarado.", FAO_ETC,
         "A seleção de registro FAO é do consumidor; não há equivalência automática entre IDs de culturas."],
        ["ETc sob condições padrão, não evapotranspiração real sob estresse.", "Ajustes de Kc ao clima/manejo e validade regional dependem de avaliação agronômica."], extras=extra, hashes=hashes)


def balance(nasa, meteomatics, store, payload, request_id):
    values, kc, reference, extra, hashes = etc_values(store, payload)
    if payload.daily_fluxes is None:
        raise ServiceError(503, "WATER_FLUXES_PENDING", "Informe fluxos diários; irrigação, ascensão, runoff e drenagem não são presumidos como zero.")
    rows = full_series(payload, payload.daily_fluxes)
    flags = [r.precipitation_mm is None for r in rows]
    if any(flags) and not all(flags):
        raise ServiceError(422, "VALIDATION_ERROR", "Precipitação deve ser inteiramente fornecida ou consultada; sem mistura implícita.")
    sources = [supplied_source(payload.assumptions_reference), supplied_source(payload.eto_reference)]
    rain = {}
    automatic_rain = all(flags)
    if automatic_rain:
        data, source, digest = weather(payload, nasa, meteomatics)
        rain = {r["date"]: r["precipitation_mm"] for r in data}
        sources.append(source)
        hashes.append("weather-sha256:" + digest)
    series, changes, cumulative = [], [], 0.0
    for row, evap in zip(rows, values):
        p = rain[row.date] if automatic_rain else row.precipitation_mm
        delta = total([p, row.irrigation_mm, row.capillary_rise_mm, -row.runoff_mm, -row.deep_percolation_mm, -evap["etc_mm_day"]])
        changes.append(delta)
        cumulative = total([cumulative, delta])
        series.append({**row.model_dump(), "precipitation_mm": p, "etc_mm_day": evap["etc_mm_day"],
                       "storage_change_mm": delta, "cumulative_storage_change_mm": cumulative})
    series[-1]["cumulative_storage_change_mm"] = total(changes)
    result = {**base(payload, total(changes), "mm", "explicit_flux_storage_change_no_initial_soil_state"),
        "series": series, "etc_total_mm": total(r["etc_mm_day"] for r in values),
        "interpretation": "storage_change_accounting_not_soil_water_content"}
    return response("calculate_simplified_water_balance", payload, result, WaterBalanceResult, request_id, "daily_explicit_flux_water_balance", sources,
        ["ΔS = P + I + CR − RO − ETc − DP, com todos os componentes explícitos e ETc = Kc × ETo.", FAO_BALANCE,
         f"Kc constante declarado/selecionado: {kc}; referência: {reference}.",
         "Não são inferidos armazenamento inicial, capacidade de campo ou perdas."],
        ["Saída é variação contábil, não estoque/umidade real do solo.", "Não diagnostica estresse, necessidade de irrigação ou água disponível às raízes."], extras=extra, hashes=hashes)


def margin(payload, request_id):
    with localcontext() as context:
        context.prec = 80
        area, yield_, price, cost = (Decimal(str(v)) for v in (payload.area_ha, payload.expected_yield_t_per_ha, payload.price_per_t, payload.cost_per_ha))
        production, revenue, costs = area * yield_, area * yield_ * price, area * cost
        amount, per_ha = revenue - costs, yield_ * price - cost
        numbers = [finite(float(v)) for v in (production, revenue, costs, amount, per_ha)]
    result = {**base(SimpleNamespace(**payload.model_dump(), location=None), numbers[3], payload.currency, "declared_economic_scenario_not_profit_forecast"),
        "currency": payload.currency, "area_ha": payload.area_ha, "production_t": numbers[0], "revenue": numbers[1],
        "declared_costs": numbers[2], "margin_per_ha": numbers[4], "assumptions_reference": payload.assumptions_reference,
        "margin_definition": "gross_margin_variable_costs" if payload.cost_basis == "variable_costs" else "revenue_less_declared_costs"}
    return response("estimate_crop_margin", payload, result, MarginResult, request_id, "declared_revenue_less_costs", [supplied_source(payload.assumptions_reference)],
        ["Produção = área × produtividade declarada; receita = produção × preço; margem = receita − área × custo/ha.", FAO_MARGIN,
         "Margem bruta somente quando custos são declarados variáveis; sem câmbio, impostos ou custos presumidos."],
        ["Cenário aritmético; não prevê produtividade ou preços nem garante lucro.", "Custos não informados não são incluídos; não representa lucro líquido contábil." ])
