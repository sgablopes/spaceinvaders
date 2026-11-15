"""Processo isolado: motor versionado, sem rede, credenciais ou alterações no código científico."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys


def simulate(payload):
    import aquacrop
    from aquacrop import AquaCropModel, Soil, Crop, InitialWaterContent, IrrigationManagement, CO2
    from importlib.metadata import version
    import pandas as pd
    import numpy as np
    if version("aquacrop") != "3.0.12":
        return {"error": "ENGINE_VERSION_MISMATCH"}
    weather = payload["weather"]["daily"]
    # Ordem nativa do motor: ele converte o DataFrame em ndarray por posição.
    df = pd.DataFrame({"MinTemp": [r["tmin_c"] for r in weather], "MaxTemp": [r["tmax_c"] for r in weather],
        "Precipitation": [r["precipitation_mm"] for r in weather], "ReferenceET": [r["eto_mm_day"] for r in weather],
        "Date": pd.to_datetime([r["date"] for r in weather])})
    # Doze compartimentos iguais, profundidade explícita; perfil de biblioteca, não solo geolocalizado.
    soil = Soil(payload["soil"]["preset"], dz=[payload["soil"]["depth_m"] / 12] * 12)
    crop = Crop(payload["crop"], planting_date=pd.Timestamp(payload["start_date"]).strftime("%m/%d"))
    if len(weather) < int(crop.MaturityCD):
        return {"error": "SEASON_INCOMPLETE"}
    snapshots = {"soil": json.loads(soil.profile.to_json(orient="records")),
        "soil_curve_number": soil.cn, "soil_readily_evaporable_water_mm": soil.rew,
        "crop": json.loads(json.dumps(crop.__dict__, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)))}
    selected = {"FC": "th_fc", "WP": "th_wp", "SAT": "th_s"}[payload["initial_water"]["method"]]
    initial = float((soil.profile[selected] * soil.profile.dz * 1000).sum())
    co2 = CO2(constant_conc=True, current_concentration=payload["co2"]["concentration_ppm"])
    model = AquaCropModel(payload["start_date"].replace("-", "/"), payload["end_date"].replace("-", "/"),
        weather_df=df, soil=soil, crop=crop, initial_water_content=InitialWaterContent(value=[payload["initial_water"]["method"]]),
        irrigation_management=IrrigationManagement(irrigation_method=0), co2_concentration=co2, off_season=False)
    model.run_model(till_termination=True)
    final = model.get_simulation_results()
    if (not model._init_cond.harvest_flag or not (model._init_cond.crop_mature or model._init_cond.crop_dead)
            or len(final) != 1 or not isinstance(final.iloc[0]["Harvest Date (YYYY/MM/DD)"], pd.Timestamp)):
        return {"error": "SEASON_INCOMPLETE"}
    stats = final.iloc[0]
    count = int(stats["Harvest Date (Step)"]) + 1
    if not 1 <= count <= len(weather):
        return {"error": "ENGINE_OUTPUT_INVALID"}
    flux, storage, growth = model.get_water_flux().iloc[:count], model.get_water_storage().iloc[:count], model.get_crop_growth().iloc[:count]
    series, previous = [], initial
    totals = {name: 0.0 for name in ("precipitation_mm", "irrigation_mm", "evaporation_mm", "transpiration_mm", "runoff_mm", "deep_percolation_mm", "capillary_rise_mm", "groundwater_inflow_mm")}
    previous_surface = 0.0
    for i in range(count):
        row, sw, gr = flux.iloc[i], storage.iloc[i], growth.iloc[i]
        if int(row.time_step_counter) != i or row.dap <= 0:
            return {"error": "ENGINE_OUTPUT_INVALID"}
        current = sum(float(sw[f"th{j+1}"]) * float(soil.profile.iloc[j].dz) * 1000 for j in range(12))
        day = {"date": weather[i]["date"], "eto_mm_day": weather[i]["eto_mm_day"],
            "soil_water_mm": current, "surface_storage_mm": float(row.surface_storage),
            "precipitation_mm": weather[i]["precipitation_mm"], "irrigation_mm": float(row.IrrDay),
            "evaporation_mm": float(row.Es), "transpiration_mm": float(row.Tr), "runoff_mm": float(row.Runoff),
            "deep_percolation_mm": float(row.DeepPerc), "capillary_rise_mm": float(row.CR), "groundwater_inflow_mm": float(row.GwIn),
            "canopy_cover_fraction": float(gr.canopy_cover), "root_depth_m": float(gr.z_root)}
        for key in totals:
            totals[key] += day[key]
        day["water_balance_residual_mm"] = (previous + previous_surface + day["precipitation_mm"] + day["irrigation_mm"] + day["capillary_rise_mm"] + day["groundwater_inflow_mm"]
            - current - day["surface_storage_mm"] - day["evaporation_mm"] - day["transpiration_mm"] - day["runoff_mm"] - day["deep_percolation_mm"])
        previous, previous_surface = current, day["surface_storage_mm"]
        series.append(day)
    residual = initial + totals["precipitation_mm"] + totals["irrigation_mm"] + totals["capillary_rise_mm"] + totals["groundwater_inflow_mm"] - previous - previous_surface - totals["evaporation_mm"] - totals["transpiration_mm"] - totals["runoff_mm"] - totals["deep_percolation_mm"]
    result = {"simulated_days": count, "last_simulated_date": weather[count-1]["date"],
        "harvest_timestamp_engine": stats["Harvest Date (YYYY/MM/DD)"].isoformat(),
        "crop_mature": bool(model._init_cond.crop_mature), "crop_dead": bool(model._init_cond.crop_dead),
        "dry_yield_t_ha": float(stats["Dry yield (tonne/ha)"]), "fresh_yield_t_ha": float(stats["Fresh yield (tonne/ha)"]),
        "water_balance": {**totals, "initial_soil_water_mm": initial, "final_soil_water_mm": previous,
            "final_surface_storage_mm": previous_surface, "residual_mm": residual, "tolerance_mm": 0.0001}, "daily": series}
    if abs(residual) > 0.0001 or any(abs(d["water_balance_residual_mm"]) > 0.0001 for d in series):
        return {"error": "WATER_BALANCE_NOT_CLOSED"}
    base = Path(aquacrop.__file__).parent
    source_hashes = {str(p.relative_to(base)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(base.rglob("*.py"))}
    output = {"result": result, "engine": {"name": "AquaCrop-OSPy", "version": version("aquacrop"),
        "official_fao_7_3": False, "numpy_version": np.__version__, "pandas_version": pd.__version__,
        "source_sha256": hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
        "parameters_sha256": hashlib.sha256(json.dumps(snapshots, sort_keys=True).encode()).hexdigest()}, "parameters": snapshots}
    json.dumps(output, allow_nan=False)
    return output


def main():
    payload = json.load(sys.stdin)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            output = simulate(payload)
    except (ImportError, ModuleNotFoundError):
        output = {"error": "ENGINE_DEPENDENCY_MISSING"}
    except Exception:
        output = {"error": "ENGINE_EXECUTION_FAILED"}
    print(json.dumps(output, allow_nan=False))


if __name__ == "__main__":
    main()
