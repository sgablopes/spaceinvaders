"""FAO-56 eq. 6, 8, 11-14, 21-25, 37-40, 42; sem climatologia inventada.

Rs/Rso limitado a 0.3..1 conforme ASCE-EWRI 2005 eq. 18/35 para o termo de nebulosidade.
"""
import math
from .vendor.intelligence.core.errors import ServiceError

FAO = "https://www.fao.org/4/X0490E/x0490e08.htm"
ASCE = "https://content-hub.uidaho.edu/api/public/content/9d9ea3f325e945158730b61661e8add8?v=cc545c86"


def vapor_pressure(temperature_c):
    return 0.6108 * math.exp(17.27 * temperature_c / (temperature_c + 237.3))


def daily_eto(day, latitude, elevation_m, tmin_c, tmax_c, wind_2m_m_s, rs_mj_m2_day, pressure_kpa, *, dewpoint_c=None, ea_kpa=None):
    values = [latitude, elevation_m, tmin_c, tmax_c, wind_2m_m_s, rs_mj_m2_day, pressure_kpa]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ServiceError(422, "ETO_INPUT_INVALID", "ETo requer entradas finitas e completas nas unidades declaradas.")
    if not (-60 <= latitude <= 60 and -400 <= elevation_m <= 5000 and -100 <= tmin_c <= tmax_c <= 100 and wind_2m_m_s >= 0 and rs_mj_m2_day >= 0 and 0 < pressure_kpa <= 120):
        raise ServiceError(422, "ETO_INPUT_INVALID", "Entradas fora da faixa suportada para cálculo diário de ETo; latitude limitada a ±60 graus.")
    if (dewpoint_c is None) == (ea_kpa is None):
        raise ServiceError(422, "ETO_INPUT_INVALID", "Informe ponto de orvalho ou pressão real de vapor, exclusivamente.")
    if dewpoint_c is not None:
        if isinstance(dewpoint_c, bool) or not isinstance(dewpoint_c, (float, int)) or not math.isfinite(dewpoint_c) or not -100 <= dewpoint_c <= tmax_c:
            raise ServiceError(422, "ETO_INPUT_INVALID", "Ponto de orvalho inválido.")
        ea_kpa = vapor_pressure(dewpoint_c)
    es = (vapor_pressure(tmin_c) + vapor_pressure(tmax_c)) / 2
    if isinstance(ea_kpa, bool) or not isinstance(ea_kpa, (float, int)) or not math.isfinite(ea_kpa) or not 0 <= ea_kpa <= es:
        raise ServiceError(422, "ETO_INPUT_INVALID", "Pressão real de vapor incompatível com as temperaturas; sem correção silenciosa.")
    mean = (tmin_c + tmax_c) / 2
    delta = 4098 * vapor_pressure(mean) / (mean + 237.3) ** 2
    gamma = 0.000665 * pressure_kpa
    j = day.timetuple().tm_yday
    phi = math.radians(latitude)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    declination = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    angle = math.acos(max(-1, min(1, -math.tan(phi) * math.tan(declination))))
    ra = 24 * 60 / math.pi * 0.0820 * dr * (angle * math.sin(phi) * math.sin(declination) + math.cos(phi) * math.cos(declination) * math.sin(angle))
    rso = (0.75 + 0.00002 * elevation_m) * ra
    if rso <= 0:
        raise ServiceError(422, "ETO_INPUT_INVALID", "Radiação de céu claro nula; método fora do domínio suportado.")
    ratio = max(0.3, min(1.0, rs_mj_m2_day / rso))
    rnl = 4.903e-9 * ((tmax_c + 273.16) ** 4 + (tmin_c + 273.16) ** 4) / 2 * (0.34 - 0.14 * math.sqrt(ea_kpa)) * (1.35 * ratio - 0.35)
    rn = 0.77 * rs_mj_m2_day - rnl
    eto = (0.408 * delta * rn + gamma * 900 / (mean + 273) * wind_2m_m_s * (es - ea_kpa)) / (delta + gamma * (1 + 0.34 * wind_2m_m_s))
    if not math.isfinite(eto) or eto < 0:
        raise ServiceError(422, "ETO_INPUT_INVALID", "ETo negativa/não finita; não foi substituída ou truncada.")
    return {"eto_mm_day": eto, "net_radiation_mj_m2_day": rn, "extraterrestrial_radiation_mj_m2_day": ra,
            "actual_vapor_pressure_kpa": ea_kpa, "rs_rso_cloudiness_ratio": ratio,
            "cloudiness_ratio_bounded": ratio != rs_mj_m2_day / rso}
