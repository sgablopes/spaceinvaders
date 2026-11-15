"""Seleção única por consulta: Meteomatics preferida, Open-Meteo alternativa explícita."""
import hashlib
from .meteomatics import ForecastError
from .meteomatics_schemas import ForecastRequest
from .weather_schemas import WeatherResponse


class Weather:
    def __init__(self, meteomatics, open_meteo):
        self.meteomatics, self.open_meteo = meteomatics, open_meteo

    def forecast(self, payload):
        requested = getattr(payload, "provider", "auto")
        # Validação de intervalo/formato é comum, sem encaminhar provider ao legado.
        query = ForecastRequest.model_validate(payload.model_dump(exclude={"provider"}))
        failures = []
        providers = [("Meteomatics", self.meteomatics), ("Open-Meteo", self.open_meteo)] if requested == "auto" else [("Meteomatics", self.meteomatics)] if requested == "meteomatics" else [("Open-Meteo", self.open_meteo)]
        for name, service in providers:
            try:
                # Em auto só se aceita um provedor com cobertura completa, sem completar lacunas de outro.
                answer = service.forecast(query.model_copy(update={"require_complete": True}) if requested == "auto" else query)
            except ForecastError as exc:
                if exc.status == 422 or requested != "auto":
                    raise
                failures.append({"provider": name, "code": exc.error["code"], "http_status": exc.status})
                continue
            data = answer.model_dump(mode="json")
            data.update(operation="get_weather_forecast", provider_requested=requested, provider_used=name,
                        fallback_used=bool(failures), provider_failures=failures)
            data["traceability"]["input_sha256"] = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
            if failures:
                data["quality"]["warnings"].append("Meteomatics indisponível/incompleta; consulta inteira atendida pela Open-Meteo, sem mistura de provedores.")
            return WeatherResponse.model_validate(data)
        raise ForecastError(503, "FORECAST_PROVIDERS_UNAVAILABLE", "Nenhuma fonte de previsão atendeu integralmente à consulta.", True,
            {"providers": [f["provider"] for f in failures], "reasons": [f["provider"] + ":" + f["code"] for f in failures]})
