from src.vendor.intelligence.core.errors import ServiceError
from src.vendor.intelligence.schemas.common import Schema
from typing import Literal


class Capability(Schema):
    id: str
    indicator_id: str
    category: Literal["IND"] = "IND"
    method: Literal["POST"] = "POST"
    path: str
    summary: str
    when_to_use: str
    limitations: list[str]
    openapi_operation_id: str
    available: bool = False
    implementation_status: Literal["planned", "implemented_local"] = "planned"


def entry(identifier: str, slug: str, operation: str, summary: str, use: str, limit: str) -> Capability:
    return Capability(id=operation, indicator_id=identifier, path=f"/v1/indicators/{slug}",
                      summary=summary, when_to_use=use, limitations=[limit, "Não implementado nesta etapa; retorna HTTP 501."],
                      openapi_operation_id=operation)


CATALOG = [
    entry("I01", "gdd", "calculate_gdd", "GDD acumulado", "Estimar avanço térmico com temperatura-base e temperaturas diárias em °C.", "Graus-dia °C não equivalem a estádio observado em campo."),
    entry("I02", "accumulated-rainfall", "calculate_accumulated_rainfall", "Chuva acumulada", "Somar precipitação em mm nas janelas 7/15/30/90 dias.", "Histórico e forecast separados; horizonte depende da cobertura real."),
    entry("I03", "dry-spell", "calculate_dry_spell", "Dias consecutivos sem chuva", "Contar dias com limiar diário explícito em mm.", "Dias faltantes não podem ser tratados como ausência de chuva."),
    entry("I05", "thermal-stress", "assess_thermal_stress", "Estresse térmico", "Avaliar temperaturas em °C com limiares por cultura e estádio.", "Exige catálogo versionado; sem limiar universal ou probabilidade calibrada."),
    entry("I07", "crop-evapotranspiration", "calculate_crop_evapotranspiration", "ETc por estádio", "Estimar ETc em mm/dia com ET₀ e Kc curado por estádio.", "Depende de ET₀ disponível e hipóteses FAO-56 documentadas."),
    entry("I08", "water-balance", "calculate_simplified_water_balance", "Balanço hídrico simplificado", "Relacionar chuva e ETc em mm com hipóteses explícitas.", "Não representa balanço hídrico real do talhão."),
    entry("I09", "climate-suitability", "assess_climate_suitability", "Aptidão climática", "Comparar clima e requisitos da cultura com score explicável.", "Escala regional e cenários GAEZ não são previsão diária local."),
    entry("I10", "crop-succession", "assess_crop_succession", "Compatibilidade teórica de sucessão", "Aplicar regras curadas às culturas anterior e seguinte.", "Compatibilidade qualitativa; simulação não é histórico real."),
    entry("I11", "planting-risk", "assess_planting_risk", "Risco agroclimático de plantio", "Avaliar regras de risco por cultura, período e local.", "Resultado próprio não equivale ao ZARC oficial nem a probabilidade calibrada."),
    entry("I13", "yield-scenario", "estimate_yield_scenario", "Cenários de produtividade", "Construir cenário em t/ha com referência país/período.", "Dados nacionais não preveem produtividade do talhão; sem ML nesta etapa."),
    entry("I14", "crop-margin", "estimate_crop_margin", "Margem estimada", "Relacionar área ha, rendimento t/ha, preço/moeda por t e custo por ha.", "Cenário condicionado às hipóteses; não garante lucro."),
]

CATALOG[0] = CATALOG[0].model_copy(update={
    "available": True,
    "implementation_status": "implemented_local",
    "when_to_use": "Calcular GDD diário, cumulativo e total em degree_day_c com série diária própria em °C e temperatura-base explícita, sem consulta externa.",
    "limitations": [
        "Método simple_average_no_upper_cap v1.0; Tbase e método influenciam o resultado. Não determina fase fenológica.",
        "Modo estrito: exige todos os dias inclusivos; ordena a série e rejeita lacunas, duplicatas e sentinels.",
        "Origem e natureza das entradas são declaradas pelo solicitante, sem verificação externa.",
        "Sem daily_temperatures, consulta automática indisponível: HTTP 503, contrato agrion-data pendente.",
    ],
})

CATALOG[1] = CATALOG[1].model_copy(update={
    "available": True,
    "implementation_status": "implemented_local",
    "summary": "Chuva acumulada retrospectiva em 7/15/30/90 dias",
    "when_to_use": "Somar lâminas diárias em mm de série própria completa nos 90 dias até reference_date, inclusive, com day_basis UTC ou LST explícito.",
    "limitations": [
        "Método rolling_sum_precipitation v1.0; quatro janelas retrospectivas, sem forecast futuro ou risco de estiagem.",
        "Rejeita lacunas, duplicatas, datas fora da janela, valores negativos ou ausentes. Zero mm é válido.",
        "Origem declarada pelo solicitante, não verificada; não converte taxas mm/h, acumulados multidiários, UTC ou LST.",
        "Sem daily_precipitation: HTTP 503 DATA_INTEGRATION_PENDING; contrato agrion-data não validado.",
    ],
})


class SupportedIndicator(Schema):
    id: str
    input_field: str
    summary: str
    limitations: list[str]
    available: bool
    implementation_status: Literal["planned", "implemented_local"]


class GroupCapability(Schema):
    id: str
    category: Literal["IND"] = "IND"
    method: Literal["POST"] = "POST"
    path: str
    summary: str
    when_to_use: str
    limitations: list[str]
    openapi_operation_id: str
    available: bool
    implementation_status: Literal["partial", "planned", "implemented"]
    supported_indicators: list[SupportedIndicator]


class CapabilitiesResponse(Schema):
    contract_version: Literal["1.0"] = "1.0"
    capabilities: list[GroupCapability]


# CATALOG remains internal metadata for compatibility routes, never a tools catalog.
def grouped_catalog() -> list[GroupCapability]:
    from src.vendor.intelligence.indicators.analysis import BINDINGS

    definitions = [
        ("climate", ["I01", "I02", "I03", "I05"], "Análise climática", "Calcular GDD e chuva retrospectiva com séries próprias; preparar dias sem chuva e estresse térmico."),
        ("water", ["I07", "I08"], "Análise de água", "Preparar ETc e balanço hídrico simplificado por estádio, com hipóteses explícitas."),
        ("agronomy", ["I09", "I10", "I11"], "Análise agronômica", "Preparar aptidão climática, sucessão de culturas e risco de plantio; entradas independentes por ID."),
        ("economics", ["I13", "I14"], "Análise econômica", "Preparar cenários de produtividade e margem, com área, unidade, moeda e hipóteses declaradas."),
    ]
    groups = []
    legacy = {item.indicator_id: item for item in CATALOG}
    for group, identifiers, summary, usage in definitions:
        supported = [SupportedIndicator(id=identifier, input_field=f"inputs.{BINDINGS[identifier][0]}",
                                       summary=legacy[identifier].summary, limitations=legacy[identifier].limitations,
                                       available=BINDINGS[identifier][1] is not None,
                                       implementation_status="implemented_local" if BINDINGS[identifier][1] is not None else "planned")
                     for identifier in identifiers]
        available = any(item.available for item in supported)
        groups.append(GroupCapability(
            id=f"analyze_{group}", path=f"/v1/analysis/{group}", summary=summary, when_to_use=usage,
            openapi_operation_id=f"analyze_{group}", available=available,
            implementation_status=("implemented" if all(item.available for item in supported) else "partial") if available else "planned",
            supported_indicators=supported,
            limitations=[
                "Selecione um ou mais IDs do grupo em include; forneça somente as entradas necessárias a esses IDs.",
                "I01/I02 funcionam localmente; I03/I05 ainda pendentes (501)." if group == "climate" else "Os cálculos deste grupo ainda não foram implementados (501 para entradas válidas).",
                "Consulta automática de dados permanece pendente (503); resultados parciais identificam IDs indisponíveis.",
                "Período, unidade, método, origem e limitações são preservados por indicador; sem zeros substitutos.",
            ],
        ))
    return groups


GROUP_CATALOG = grouped_catalog()


def not_implemented(operation: str) -> None:
    raise ServiceError(501, "INDICATOR_NOT_IMPLEMENTED", "Indicador previsto, ainda não implementado.",
                       details={"operation": operation})
