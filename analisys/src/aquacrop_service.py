"""Ponte NASA/FAO-56 → processo AquaCrop, sem duplicar o motor ou os indicadores."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import BoundedSemaphore
from uuid import uuid4

from pydantic import ValidationError
from .aquacrop_schemas import WeatherDay, SimulationResponse, SimulationResult, EngineInfo
from .fao56_eto import daily_eto, FAO, ASCE
from .indicator_weather import full_series
from .nasa_schemas import DailyRequest
from .nasa_power import NasaError, bounded_env
from .vendor.intelligence.core.errors import ServiceError

WEATHER_PARAMETERS = ["T2M_MIN", "T2M_MAX", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "WS2M", "T2MDEW", "PS"]
SLOTS = BoundedSemaphore(1)


def prepare_weather(payload, nasa):
    if payload.weather.source == "caller_supplied":
        rows = full_series(payload, payload.weather.daily)
        return rows, [{"provider": "caller_supplied", "kind": "caller_supplied", "reference": payload.weather.reference}], {}
    try:
        data = nasa.daily(DailyRequest(location=payload.location, start_date=payload.start_date, end_date=payload.end_date,
            parameters=WEATHER_PARAMETERS, time_standard="UTC", require_complete=True))
    except NasaError as exc:
        raise ServiceError(exc.status, exc.error["code"], exc.error["message"], exc.error["retryable"], {"provider": "NASA POWER"}) from None
    elevation = payload.elevation_m
    if elevation is None:
        coords = data.provenance[0].source_geometry.get("coordinates", [])
        elevation = coords[2] if len(coords) == 3 else None
    if isinstance(elevation, bool) or not isinstance(elevation, (float, int)) or not math.isfinite(elevation):
        raise ServiceError(503, "ELEVATION_REQUIRED", "NASA não informou elevação válida; forneça elevation_m com referência nas hipóteses.")
    rows, diagnostics = [], []
    for day in data.result.series:
        eto = daily_eto(day.date, payload.location.latitude, elevation, day.tmin_c, day.tmax_c,
            day.wind_speed_2m_m_s, day.solar_radiation_mj_m2_day, day.surface_pressure_kpa, dewpoint_c=day.dewpoint_c)
        try:
            rows.append(WeatherDay(date=day.date, tmin_c=day.tmin_c, tmax_c=day.tmax_c,
                precipitation_mm=day.precip_mm_day, eto_mm_day=eto["eto_mm_day"]))
        except ValidationError:
            raise ServiceError(422, "ETO_OUTSIDE_ENGINE_RANGE", "ETo/clima fora da faixa aceita pelo motor; nenhum valor foi truncado ou preenchido.") from None
        diagnostics.append({"date": day.date.isoformat(), **eto})
    return full_series(payload, rows), [data.provenance[0].model_dump(mode="json"),
        {"provider": "AGRION calculation", "kind": "derived_estimate", "reference": FAO,
         "cloudiness_bounds_reference": ASCE, "method": "fao56_penman_monteith_daily_asce_cloudiness_bounds",
         "elevation_m": elevation, "elevation_source": "caller_supplied" if payload.elevation_m is not None else "NASA POWER geometry"}], {
             "nasa_input": data.model_dump(mode="json"), "eto_diagnostics": diagnostics}


def run(payload, nasa, root: Path):
    if not SLOTS.acquire(blocking=False):
        raise ServiceError(429, "SIMULATION_BUSY", "Uma simulação já está em execução; tente novamente após concluir.", True)
    try:
        weather, provenance, details = prepare_weather(payload, nasa)
        prepared = payload.model_dump(mode="json")
        prepared["weather"] = {**prepared["weather"], "daily": [r.model_dump(mode="json") for r in weather]}
        runtime = root / ".runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="aquacrop-", dir=runtime) as temporary:
            # Ambiente mínimo: o processo científico não recebe segredos meteorológicos.
            env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "LD_LIBRARY_PATH", "LANG"}}
            env.update(DEVELOPMENT="True", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
                TMP=temporary, TEMP=temporary, TMPDIR=temporary, MPLCONFIGDIR=temporary,
                XDG_CACHE_HOME=temporary, NUMBA_CACHE_DIR=temporary)
            try:
                process = subprocess.run([sys.executable, "-B", "-m", "src.aquacrop_worker"], cwd=root,
                    input=json.dumps(prepared), text=True, encoding="utf-8", capture_output=True,
                    timeout=bounded_env("AQUACROP_TIMEOUT_SECONDS", 90, 5, 180), env=env, check=False)
            except subprocess.TimeoutExpired:
                raise ServiceError(504, "SIMULATION_TIMEOUT", "A simulação excedeu o limite; o processo foi encerrado sem resultado substituto.", True) from None
        try:
            answer = json.loads(process.stdout) if process.returncode == 0 else {}
        except (ValueError, TypeError):
            answer = {}
        error = answer.get("error")
        if error == "SEASON_INCOMPLETE":
            raise ServiceError(422, error, "Safra não foi concluída no período informado; amplie o histórico. Não foi retornada produtividade parcial como colheita.")
        if error in {"ENGINE_DEPENDENCY_MISSING", "ENGINE_VERSION_MISMATCH"}:
            raise ServiceError(503, error, "Instale as dependências versionadas de analisys e reconstrua o container.")
        if error or not all(k in answer for k in ("result", "engine", "parameters")):
            raise ServiceError(502, error or "ENGINE_OUTPUT_INVALID", "O motor não produziu resultado validado; não foi gerada estimativa substituta.")
        try:
            SimulationResult.model_validate(answer["result"])
            EngineInfo.model_validate(answer["engine"])
        except ValidationError:
            raise ServiceError(502, "ENGINE_OUTPUT_INVALID", "Resultado do motor incompatível com o contrato; nenhum valor foi substituído.") from None
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        return SimulationResponse(scenario_id=payload.scenario_id, engine=answer["engine"], result=answer["result"], weather=weather,
            inputs={"request": payload.model_dump(mode="json"), "parameters": answer["parameters"], **details},
            provenance=provenance + [{"provider": "AquaCrop-OSPy", "version": "3.0.12", "kind": "model_parameter_reference",
                "source_url": "https://github.com/aquacropos/aquacrop", "license": "Apache-2.0",
                "soil": "generic library preset explicitly assumed, not a measured/geolocated profile",
                "crop": "generic Maize library parameters, not locally calibrated"}],
            method={"name": "aquacrop_os_py_single_season", "planting_date": payload.start_date.isoformat(),
                "weather_basis": "UTC", "soil_compartments": 12, "soil_mesh": "equal thickness across declared depth",
                "irrigation": "rainfed; no irrigation", "groundwater": "no water table; engine default",
                "fertility_salinity_weeds": "not simulated/calibrated by this adapter",
                "co2": "explicit constant concentration; engine A1B projection dataset is not used",
                "water_balance": "initial soil + P + I + CR + GwIn - final soil - final surface storage - Es - Tr - runoff - deep percolation",
                "harvest_timestamp": "engine step_end_time (exclusive daily boundary); last_simulated_date identifies the final civil day"},
            quality={"kind": "scenario", "field_validated": False, "engine_executed": True,
                "completed_crop_cycle": answer["result"]["crop_mature"], "simulation_terminated": True,
                "water_balance_closed": True, "crop_died": answer["result"]["crop_dead"],
                "warnings": ["Simulação científica executada; produtividade simulada não é colheita observada nem promessa de produção.",
                    "Solo, água inicial, CO2 e manejo são hipóteses explícitas; não foram obtidos da propriedade."]},
            limitations=["AquaCrop-OSPy 3.0.12 não é a distribuição oficial FAO AquaCrop 7.3.",
                "Somente Maize de biblioteca, uma safra de sequeiro e perfil genérico SandyLoam/Loam explicitamente selecionado.",
                "HWSD raster/MDB e análises de solo validadas ausentes; sem conversão automática de textura para parâmetros hidráulicos.",
                "Séries NASA são estimativas regionais; ETo é cálculo derivado com limites de nebulosidade ASCE declarados.",
                "Agregação UTC pode diferir do dia solar/local do manejo; não houve calibração dessa diferença.",
                "Sem efeitos de rotação, custos, recomendação, calibração local, fertilidade, salinidade ou plantas daninhas.",
                "Sem completar safra com forecast curto ou interpolação; somente uma execução concorrente, até 300 dias e timeout limitado."],
            traceability={"request_id": uuid4().hex, "generated_at": datetime.now(timezone.utc).isoformat(),
                "input_sha256": digest(payload.model_dump(mode="json")), "weather_sha256": digest(prepared["weather"]["daily"]),
                "result_sha256": digest(answer["result"])})
    finally:
        SLOTS.release()
