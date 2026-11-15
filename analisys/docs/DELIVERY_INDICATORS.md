# Indicadores com metodologia e entradas disponíveis

> Registro da API 1.3.0. Na continuação 1.4.0, a validação forecast real foi concluída com Meteomatics e Open-Meteo; I03/I05 e chuva de I08 passaram a compartilhar o seletor automático. Consulte [DELIVERY_WEATHER.md](DELIVERY_WEATHER.md). ETo/Kc/fluxos explícitos e limitações agronômicas continuam aplicáveis.

Entrega de 15/11/2026, API 1.3.0, branch `analisys`. Implementação aditiva na mesma FastAPI/container. Não altera a aplicação principal, as planilhas/ZIP originais ou os módulos de cálculo anteriores em `src/vendor/intelligence/`.

## Estado e dependências

| ID | Disponibilizado | Limite ou dependência |
| --- | --- | --- |
| I01 | GDD anterior, série própria ou NASA histórica | Tbase explícita; método preservado, sem forecast automático |
| I02 | Chuva acumulada anterior, série própria ou NASA histórica | Janela original de 90 dias, sem forecast automático |
| I03 | Maior sequência e sequência final de dias secos; contagem total | Limiar explícito; NASA histórica validada. Forecast preparado/testado com mock, não validado com previsão real |
| I05 | Triagem de exposição: dias abaixo/acima de limites térmicos | Limites declarados ou envelope geral ECOCROP. Não é modelo de dano/estresse por estádio; forecast real pendente |
| I07 | ETc padrão diária e acumulada | ETo diária fornecida e referenciada; Kc declarado ou registro FAO escalar selecionado explicitamente |
| I08 | Variação contábil diária/acumulada de água | ETo/Kc e todos os demais fluxos explícitos; chuva própria ou NASA. Ponte forecast de chuva preparada; sem estoque inicial ou calibração do solo |
| I14 | Receita menos custos declarados, total e por hectare | Área, produtividade, preço, custo e moeda fornecidos; cenário, sem previsão de mercado/produtividade |
| I09 | Pendente: aptidão climática | Método de classificação/pesos, equivalência de culturas e interpretação dos produtos GAEZ ainda não validados |
| I10 | Pendente: sucessão | Regras revisadas por contexto e evidências agronômicas; biblioteca é consultável, não motor validado de recomendação |
| I11 | Pendente: risco de plantio | Limiares/regras por cultura, estádio e região; previsão autenticada sozinha não valida o método |
| I13 | Pendente: cenário de produtividade | Método calibrado e dados produtivos/manejo/solo; AquaCrop tem entradas vazias e HWSD raster/MDB ausente |

I03/I05/I07/I08 aceitam séries controladas declaradas como `series_kind: "forecast"` ou `"simulation"`; respostas ficam identificadas como cenário. Isso testa a matemática e o contrato, sem validar previsões reais. A ponte Meteomatics automática está preparada para I03/I05 e para a chuva de I08: exige `data_kind: "forecast"`, credenciais e acesso aos parâmetros no plano. I07 não recebe ETo automaticamente desse conector.

## Métodos e fontes

- **I03:** dia seco se `precipitation_mm < rain_threshold_mm`, estritamente. `value` e `longest_run_days` são o maior comprimento na janela; `trailing_run_days` é o comprimento ao final; `dry_days` é a contagem total. A condição de 1 mm corresponde à definição de dia seco CDD do [Climdex oficial](https://climate-scenarios.canada.ca/?page=climdex-indices). Outros limiares são escolhas do consumidor. Uma janela arbitrária não deve ser apresentada como o índice anual CDD. Sequências podem ultrapassar o início/fim do período; `starts_dry` informa censura possível na borda inicial. Não calcula probabilidade de seca.
- **I05:** conta dias com `Tmin < lower_threshold_c` ou `Tmax > upper_threshold_c`; igualdade não é exposição. `value` conta a união, sem duplicar dias com as duas condições; as contagens individuais também são retornadas. É uma comparação explícita, sem fórmula de dano. A seleção opcional por `ecocrop_crop_id` usa somente `temp_abs_min_C`/`temp_abs_max_C` da tabela normalizada preservada, com hash/origem. Limites da espécie não representam tolerância da cultivar, estádio, duração horária ou perda produtiva.
- **I07:** `ETc = Kc × ETo`, em mm/dia, conforme [FAO-56, capítulo 6](https://www.fao.org/4/X0490E/x0490e0b.htm). `value` soma a lâmina no período, em mm. Um Kc constante aplica-se ao período/estádio declarado. O serviço não interpola estádios nem ajusta Kc automaticamente ao vento, umidade ou altura. É ETc de condições padrão, sem coeficiente de estresse e sem estimar ET real.
- **I08:** `ΔS = P + I + CR − RO − ETc − DP`, em mm por dia, invertendo a variação de depleção do [balanço FAO-56, capítulo 8](https://www.fao.org/4/X0490E/x0490e0e.htm). P=precipitação, I=irrigação, CR=ascensão capilar, RO=escoamento superficial, DP=percolação profunda. Todos são fornecidos; P pode ser consultada automaticamente. ETc vem do mesmo componente I07. Esse balanço sob as hipóteses declaradas não modela solo sob estresse: faltam armazenamento inicial, capacidade de campo, ponto de murcha e dinâmica radicular. Valores negativos indicam variação, não umidade negativa. Não calcula irrigação recomendada.
- **I14:** produção=área×rendimento; receita=produção×preço; custos=área×custo/ha; margem=receita−custos. A denominação margem bruta só é usada com `cost_basis: "variable_costs"`, conforme a definição de receita menos custos variáveis da [FAO, Farm business analysis](https://www.fao.org/4/i3228e/i3228e.pdf). O padrão `declared_costs` retorna receita menos custos informados. Não é lucro líquido e não inclui custos, impostos, câmbio ou preços ausentes.

O Kc opcional da base local usa `indice_atomico` e `auditoria_registros`. Exige ID/parâmetro únicos, valor finito escalar adimensional, `Revisao=OK_EXTRAIDO`, situação estrutural conferida ou pendência de faixas/notas em outros campos. Campos Kc marcados não escalares, culturas não identificadas e variantes não desdobradas são recusados. Isso é validação estrutural; a escolha e adequação agronômica do registro continuam sob responsabilidade do consumidor. Nenhuma faixa é substituída por média. Consulte também as notas e auditorias pelas rotas FAO. Não há mapeamento automático entre IDs ECOCROP, biblioteca e FAO.

## Contrato comum

Mantidos os quatro endpoints públicos `POST /v1/analysis/climate`, `/water`, `/agronomy`, `/economics`. Use `include` para selecionar IDs e os seguintes campos em `inputs`:

| ID | Endpoint | Campo |
| --- | --- | --- |
| I03 | climate | dry_spell |
| I05 | climate | thermal_stress |
| I07 | water | crop_evapotranspiration |
| I08 | water | water_balance |
| I14 | economics | crop_margin |

Os novos indicadores de série exigem `start_date`/`end_date` inclusivos, `timezone: "UTC"`, um registro para cada dia, sem datas duplicadas, extras ou lacunas. Modo manual até 36.600 dias; NASA até 366. Não se preenche ausência com zero. Chuva/fluxos/ETo/Kc devem ser números finitos não negativos; temperatura em °C, chuva/fluxos em mm diários, ETo em mm/dia. Séries manuais são usadas sem consulta meteorológica automática. Sem série meteorológica, é obrigatória `location` WGS84. I07/I08 sempre precisam de ETo própria.

As respostas incluem `result.indicators[ID]`, `value`, `unit`, `period`, `validation_scope`, `method`, `provenance`, `quality`, `limitations`, hashes em `traceability` e detalhamento diário quando aplicável. A raiz agrega metadados, não valores entre indicadores. A origem `catalog_reference` identifica catálogo de parâmetros, separada da origem meteorológica `modeled_estimate`/`operational_forecast` ou `caller_supplied`. Inputs referenciados não são automaticamente certificados pelo serviço.

Faltas estruturais retornam 422. ETo, Kc, fluxos ou limites indispensáveis ausentes retornam 503 com motivo específico; registro não encontrado retorna 404, catálogo ambíguo/pendente retorna 503. Lacunas externas são recusadas. IDs ainda não implementados retornam 501. Um grupo com sucesso e indisponibilidade retorna `status: "partial"`, com motivo por ID e sem valores substitutos. I01/I02 preservam seus contratos e unidades anteriores.

### NASA → I03 e ECOCROP → I05

POST em `http://127.0.0.1:8001/v1/analysis/climate`:

```json
{
  "include": ["I03", "I05"],
  "inputs": {
    "dry_spell": {
      "location": {"latitude": -16.5, "longitude": -49.3},
      "start_date": "2025-10-01", "end_date": "2025-10-03",
      "timezone": "UTC", "rain_threshold_mm": 1
    },
    "thermal_stress": {
      "location": {"latitude": -16.5, "longitude": -49.3},
      "start_date": "2025-10-01", "end_date": "2025-10-03", "timezone": "UTC",
      "crop_id": "ECO_289", "ecocrop_crop_id": "ECO_289",
      "growth_stage": "not_stage_calibrated", "threshold_catalog_version": "local_preserved"
    }
  }
}
```

`ECO_289` é quiabo. Aqui o envelope geral absoluto é selecionado explicitamente, sem alegar limites por estádio. Alternativa: omitir `ecocrop_crop_id`, fornecer um ou ambos `lower_threshold_c`/`upper_threshold_c` e `threshold_reference`. Para série própria, adicione `daily_temperatures` com `date`, `tmin_c`, `tmax_c`. I03 aceita `daily_precipitation` com `date`, `precipitation_mm`.

### ETc e balanço: exemplo controlado, não dados reais

POST em `/v1/analysis/water`; os valores são hipóteses sintéticas para testar o contrato:

```json
{
  "include": ["I07", "I08"],
  "inputs": {
    "crop_evapotranspiration": {
      "start_date": "2025-10-01", "end_date": "2025-10-01", "timezone": "UTC",
      "crop_id": "test", "growth_stage": "test", "kc_catalog_version": "controlled_test",
      "series_kind": "simulation", "eto_reference": "synthetic test, not forecast",
      "eto_series": [{"date": "2025-10-01", "eto_mm_day": 4}],
      "kc": 1.2, "kc_reference": "synthetic test, not a crop recommendation"
    },
    "water_balance": {
      "start_date": "2025-10-01", "end_date": "2025-10-01", "timezone": "UTC",
      "crop_id": "test", "growth_stage": "test", "kc_catalog_version": "controlled_test",
      "series_kind": "simulation", "eto_reference": "synthetic test, not forecast",
      "eto_series": [{"date": "2025-10-01", "eto_mm_day": 4}],
      "kc": 1.2, "kc_reference": "synthetic test, not a crop recommendation",
      "assumptions_reference": "all fluxes synthetic for arithmetic verification",
      "daily_fluxes": [{"date": "2025-10-01", "precipitation_mm": 5,
        "irrigation_mm": 1, "capillary_rise_mm": 0, "runoff_mm": 0.5, "deep_percolation_mm": 0.5}]
    }
  }
}
```

Resultados aritméticos controlados: I07=4,8 mm; I08=0,2 mm de variação. Para selecionar Kc da base, remova `kc`/`kc_reference` e use, por exemplo, `"kc_selection": {"record_id": "FAO56-25-61-197-03", "parameter": "kc_mid"}`; o registro é Asparagus e sua escolha não deve ser estendida a outras culturas. Selecione `kc_ini`, `kc_mid` ou `kc_end` conforme o registro e sua aplicação revisada. Para chuva automática em I08, omita `precipitation_mm` em **todos** os dias e forneça `location`. Os demais fluxos permanecem obrigatórios, inclusive zeros assumidos explicitamente.

### Margem: cenário econômico controlado

POST em `/v1/analysis/economics`:

```json
{
  "include": ["I14"],
  "inputs": {"crop_margin": {
    "start_date": "2025-10-01", "end_date": "2025-10-03", "timezone": "UTC",
    "crop_id": "controlled_test", "area_ha": 2, "expected_yield_t_per_ha": 3,
    "price_per_t": 1000, "cost_per_ha": 2000, "currency": "BRL",
    "cost_basis": "declared_costs", "assumptions_reference": "synthetic economic scenario"
  }}
}
```

O exemplo produz receita 6.000 BRL, custos declarados 4.000 BRL e margem 2.000 BRL, sem correspondência com observações de mercado. Margem negativa é permitida. Área em ha, rendimento em t/ha, preço em moeda/t e custo em moeda/ha.

### Forecast preparado

I03/I05 sem séries próprias e com `data_kind: "forecast"` solicitam precipitação acumulada ou Tmin/Tmax em intervalos de 24 horas encerrados na meia-noite UTC seguinte ao dia civil. Ex.: dia D usa intervalo `[D 00:00, D+1 00:00]` da fonte; não atribui o acumulado ao dia de encerramento. Intervalos incompletos/futuros além do horizonte são recusados. I08 usa a mesma ponte para chuva omitida, preservando ETo e fluxos explícitos. Os testes usam fixtures sintéticas, incluindo a associação correta de datas.

Sem credenciais, a consulta automática retorna 503 `METEOMATICS_CREDENTIALS_MISSING`, sem fallback NASA ou previsão inventada. Configure no servidor `METEOMATICS_USERNAME`/`METEOMATICS_PASSWORD` conforme [DELIVERY_METEOMATICS.md](DELIVERY_METEOMATICS.md). O cliente AGRION não envia segredos. Acesso do plano a precipitação e extremos de 24h, horizonte e validação científica ainda precisam ser confirmados com a conta. ETo derivada de forecast não está implementada: exige método completo, radiação adequada, vento na altura requerida e demais entradas validadas.

## Verificação reproduzível

A partir de `analisys/`:

```sh
python -B -m unittest discover -s tests -v
python -B tools/verify_indicators.py
python -B tools/verify_automatic_indicators.py
```

O primeiro roda 58 testes determinísticos, incluindo 13 novos de limites, zeros, lacunas, duplicatas, ambiguidade dos catálogos, equações, overflow, margem negativa, previsões simuladas e compatibilidade das quatro operações. Preserva a verificação de hashes do núcleo anterior e dos arquivos originais.

Os dois scripts HTTP exigem o container iniciado; consultam a rede real. Em 15/11/2026, I03/I05 foram consultados com NASA real no Brasil/EUA, período 01–03/10/2025, com igualdade entre séries explícitas e consulta automática. I07/I08/I14 passaram por HTTP com entradas controladas e Kc real selecionado, sem declarar ETo/fluxos/preços como observados. I01/I02 passaram novamente no Brasil/EUA e em período recente, preservando equivalência com rotas legadas. O container ficou saudável em `127.0.0.1:8001`. Evidências locais em `.runtime/indicators-live-check.json` e `.runtime/automatic-indicators-check.json` (não versionadas).

A tentativa forecast pela rota de indicador confirmou ausência de credenciais (503). **Nenhuma previsão Meteomatics autenticada foi validada nesta entrega.** Não há bloqueio para consumir indicadores com NASA histórica ou entradas próprias. Integração do Flask, revisão científica por cultura/região e quatro indicadores sem método suficiente continuam pendentes.
