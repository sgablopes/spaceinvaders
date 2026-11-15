# Integração automática NASA POWER → indicadores existentes

## Escopo e decisão de integração

Esta continuação conclui a ligação automática das séries NASA aos dois indicadores já implementados no AGRION: I01 GDD e I02 chuva acumulada. Não implementa novos métodos científicos, previsões, modelos de produtividade ou recomendações. Mantém os contratos dos quatro grupos previstos: clima, água, agronomia e economia, sem inventar resultados para seus nove cálculos pendentes.

O planejamento anterior separava Dados e Inteligência em dois serviços. A instrução explícita deste trabalho exige **uma única API** e alterações exclusivamente em `analisys/`. Por isso as duas responsabilidades continuam em módulos separados, mas seus routers são registrados na mesma aplicação FastAPI, no mesmo Swagger e no mesmo container na porta 8001 do host. Não há subaplicação, chamada HTTP da API para si mesma ou dependência da Área de Trabalho em execução. A aplicação Flask na porta 8000 e o projeto original foram preservados.

## Reaproveitamento rastreável

Foram incorporados 15 módulos do núcleo existente de `agrion-intelligence` em `src/vendor/intelligence/`, com manifesto de SHA-256 da origem e da cópia empacotada. Os arquivos de GDD, chuva, validações e envelopes mantêm o conteúdo anterior, exceto o namespace dos imports. O orquestrador anterior recebeu dois argumentos opcionais (`bindings` e `response_model`) para injetar serviços de integração e envelopes de procedência, mantendo seu comportamento padrão. Nenhuma fórmula foi reescrita.

`tools/import_indicators.py` documenta essa importação reproduzível e idempotente, rejeitando sobrescritas divergentes. O manifesto não inclui segredos nem dados do agricultor. O container copia o pacote interno; o caminho local do projeto original não é usado em produção.

`src/analysis_service.py` faz somente consulta, validação, adaptação e enriquecimento da procedência. O cálculo continua nas funções originais `calculate_daily_gdd` e `calculate_rainfall_windows`.

## Consumo

No mesmo `http://127.0.0.1:8001/docs`, execute:

```http
POST /v1/analysis/climate
Content-Type: application/json
```

```json
{
  "include": ["I01", "I02"],
  "inputs": {
    "gdd": {
      "location": {"latitude": -16.5, "longitude": -49.3},
      "crop_id": "maize",
      "start_date": "2025-10-01",
      "end_date": "2025-10-03",
      "base_temperature_c": 10,
      "timezone": "UTC"
    },
    "rainfall": {
      "location": {"latitude": -16.5, "longitude": -49.3},
      "reference_date": "2025-10-03",
      "day_basis": "UTC"
    }
  }
}
```

É uma requisição ilustrativa: Tbase=10 °C é hipótese explícita do consumidor, não uma calibração automática da cultura. Valores de produção são calculados a partir da NASA; não existe resposta fixa.

Omitir `daily_temperatures` ou `daily_precipitation` seleciona a consulta NASA correspondente. Fornecer uma série mantém o modo manual, com seus métodos, validações e procedência `caller_supplied`, sem consultar a rede. `include` pode selecionar somente I01 ou I02; chuva não exige Tbase ou temperaturas.

- **I01:** consulta apenas `T2M_MIN`/`T2M_MAX` no intervalo inclusivo informado, até 366 dias. Exige UTC, localização e Tbase explícita. Reutiliza `simple_average_no_upper_cap` v1.0, sem cutoff superior ou ajuste de Tmin. Não determina estágio fenológico observado.
- **I02:** consulta apenas `PRECTOTCORR` de `reference_date-89` até `reference_date`. Calcula quatro somas retrospectivas de 7/15/30/90 dias. Aceita UTC ou LST e mantém a base temporal, sem conversão. O valor POWER em mm/day no passo diário é mapeado para lâmina de um dia em mm.
- As consultas usam a mesma instância do conector e o mesmo cache da rota INT `/v1/data/nasa-power/daily`; não baixam variáveis desnecessárias como radiação para calcular GDD ou chuva.

As 11 rotas legadas `/v1/indicators/...` existem para compatibilidade e permanecem ocultas do OpenAPI. As duas funcionais também aceitam o automático. O formato legado de chuva `start_date/end_date/window_days`, anteriormente reservado e sem semântica operacional confirmada, continua retornando 503 `LEGACY_AUTOMATIC_PENDING`; para consultar automaticamente, use `reference_date/day_basis/location`, sem misturar formatos.

## Saída, falhas e procedência

O envelope v1 e os campos originais são preservados. `result.indicators.I01`/`I02` mantêm unidade, período, série/janelas e metadados próprios. Em automático:

- `provenance.provider=NASA POWER`, `kind=modeled_estimate`, URL e data de acesso da consulta real.
- I01 declara `series[].data_kind=modeled_estimate`; I02 declara `source_type=nasa_power` e `source_kind=modeled_estimate`.
- Esses valores são extensões aditivas dos enums de **saída**. Os valores e comportamento manuais antigos continuam válidos. Clientes estritos devem utilizar o OpenAPI atual para validar o automático, que antes retornava indisponibilidade.
- Hashes do request original, da entrada usada no cálculo e da resposta NASA permitem rastrear a cadeia. `accessed_at` da NASA não é substituído pelo horário do cálculo em hits de cache.
- Geografia é uma estimativa da grade regional consultada; nunca apresentada como medição de campo. Confiança decorativa e previsão não são acrescentadas.

As séries necessárias ao cálculo devem estar completas. Lacunas geram indisponibilidade explícita, sem zero substituto nem soma parcial silenciosa. Se outro ID selecionado tiver resultado, a resposta é HTTP 200 `partial`, com o ID indisponível e sua razão. Se nenhum puder ser calculado, retorna erro 404/429/502/503/504 conforme a causa; entradas inválidas geram 422. Todos os IDs ainda não implementados geram 501. Forecast automático continua 503 `FORECAST_UNAVAILABLE`.

Os envelopes de erro de análise usam `error.code/message/retryable/details`, sem ecoar corpos ou campos privados. As rotas anteriores `/api/v1/...` continuam com seus erros `detail`, e a rota NASA mantém seu contrato já entregue.

## Operações e catálogo

| Operação pública | operationId | Estado |
| --- | --- | --- |
| `/v1/analysis/climate` | `analyze_climate` | I01/I02 manuais e automáticos; I03/I05 pendentes |
| `/v1/analysis/water` | `analyze_water` | I07/I08 pendentes |
| `/v1/analysis/agronomy` | `analyze_agronomy` | I09/I10/I11 pendentes |
| `/v1/analysis/economics` | `analyze_economics` | I13/I14 pendentes |

`/v1/capabilities` conserva a operação NASA INT já publicada e acrescenta as quatro análises IND, com seus IDs internos e estados reais. O catálogo das bases locais continua em `/api/v1/datasets`. Não são anunciadas 11 ferramentas novas nem criados novos Swaggers.

## Execução e validação

Os comandos gerais continuam em [API.md](API.md). A dependência adicional `tzdata==2025.2` é a mesma do projeto anterior e preserva a validação de fusos, inclusive no Windows. Não foi adicionado framework, banco ou serviço.

```sh
docker compose -f analisys/compose.yaml up -d --build --wait --wait-timeout 60
```

A partir de `analisys/`:

```sh
python -B -m unittest discover -s tests -v
python -B tools/verify_automatic_indicators.py
```

A suíte inclui as regressões anteriores, preservação do modo manual, namespace/hash do núcleo importado, automático com parâmetros mínimos, UTC/LST, cache, falhas/cota/lacunas, partial, ausência de valores substitutos, quatro operationIds públicos e ocultação das rotas legadas. Mocks são explicitamente sintéticos. A prova real não depende do projeto original: acessa somente a API do container e a NASA.

O relatório real foi gravado em `.runtime/automatic-indicators-check.json`, ignorado pelo Git. A validação executada em 15/11/2026 confirmou:

- **31 testes aprovados em 26,734 s**, sem chamadas reais nos testes determinísticos.
- Build concluído e container **healthy**, mantendo 8001 do host e um único Swagger.
- Consulta automática HTTP 200 e `status=ok` nas três provas abaixo, com procedência NASA real e igualdade dos valores nas rotas agrupada e legadas.

| Prova | Período GDD | GDD (°C·dia), sob hipótese explícita Tbase=10 °C | Chuva nos 90 dias até a referência (mm) |
| --- | --- | --- | --- |
| Brasil (-16,5; -49,3) | 01–03/10/2025 | 58,345 | 20,05 |
| EUA (41,5; -93,6) | 01–03/10/2025 | 42,120000000000005 | 285,74 |
| Brasil recente (-16,5; -49,3) | 05–07/11/2026 | 60,095 | 180,51 |

Os valores não foram arredondados no cálculo. A Tbase é entrada de prova, não recomendação calibrada. Temperaturas/chuva recentes foram consultadas sem exigir radiação, que estava ausente na prova da etapa S01. Essa escolha não preenche lacunas nem supõe variáveis inexistentes.

Os 15 módulos empacotados também foram comparados à origem disponível: hashes da cópia coincidem com o manifesto e o conteúdo corresponde à transformação documentada de imports e à injeção opcional no orquestrador. A importação foi repetida como verificação de idempotência sem modificar o projeto original. `.gitattributes` dentro de `analisys/` mantém LF no pacote para que a validação dos hashes seja estável após checkout no Windows.

## Arquivos desta continuação

- Novos: `src/analysis_schemas.py`, `src/analysis_service.py`, `src/analysis_routes.py`, `src/vendor/`, `tests/test_analysis.py`, `tools/import_indicators.py`, `tools/verify_automatic_indicators.py`, `.gitattributes` e este relatório.
- Atualizados: `src/main.py`, `src/nasa_routes.py`, `requirements.txt`, `README.md`, `docs/API.md`, `docs/COLABORACAO.md` e a referência histórica em `docs/DELIVERY_S01.md`.
- Alterações anteriores NASA ainda não commitadas foram preservadas. Não houve commit, push, merge ou deploy remoto nesta continuação.

## Pendências mantidas sem ampliar o escopo

- I03/I05 e os demais sete indicadores não têm implementação científica validada no material anterior. Esta entrega conecta métodos prontos; não inventa limiares, ET₀, calibração de produtividade ou regras de recomendação para declarar tudo concluído.
- HWSD raster/MDB não estão disponíveis em `analisys/`; não é possível gerar perfil hidráulico validado apenas do README.
- Forecast operacional, ETo/ETc, AquaCrop e dados financeiros continuam etapas separadas, com suas dependências de dados/método.
- A interpretação agronômica de GAEZ e a revisão documental da relação mandioca → milho continuam pendentes; seus dados de consulta já disponíveis não foram alterados.
- A ligação ao Flask e seu Compose é responsabilidade do desenvolvedor principal. O consumidor deve configurar `http://agrion-data:8000` na rede Docker compartilhada, ou a porta 8001 do host no desenvolvimento.
- O projeto original da Área de Trabalho continua intacto e, isoladamente, mantém seu comportamento anterior. O automático concluído e empacotado é o da API única em `analisys/`.
