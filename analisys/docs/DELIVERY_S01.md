# Entrega S01 — NASA POWER e continuidade do trabalho de indicadores

Registro da etapa inicial NASA. A pendência de ligação automática I01/I02 na API única de `analisys/` foi concluída posteriormente em [DELIVERY_AUTOMATIC_INDICATORS.md](DELIVERY_AUTOMATIC_INDICATORS.md), com núcleo empacotado e sem alterar o projeto externo. Os estados abaixo retratam esta primeira etapa.

- **Categoria:** INT, integração de dados.
- **Serviço:** API de dados existente em `analisys/`; nenhuma nova aplicação FastAPI ou container foi criada.
- **Situação:** conector de dados implementado e validado em rede; consumidor automático em `agrion-intelligence` permanece pendente. A alimentação manual dos cálculos existentes foi validada com dados reais.

## Auditoria do projeto anterior

Foi inspecionado `C:/Users/amarildoPaixao/Desktop/agrion-intelligence`, incluindo `AGENTS.md`, o padrão técnico, o agrupamento de indicadores, README, contratos, código e testes. Suas instruções estabelecem que fontes externas pertencem a `agrion-data`; a Inteligência concentra cálculos e mantém quatro operações públicas. A regra deste chat restringe alterações a `analisys/`. Por isso o projeto externo foi consultado e testado somente em leitura.

| Componente encontrado | Estado conferido |
| --- | --- |
| FastAPI, schemas Pydantic, erros, request ID e catálogo | Implementados; testes aprovados |
| `POST /v1/analysis/climate` | Orquestra I01 e I02 com séries fornecidas; I03/I05 reservados |
| I01 — GDD | Funcional: `simple_average_no_upper_cap` v1.0, sem inferir Tbase |
| I02 — chuva acumulada | Funcional: quatro somas retrospectivas de 7/15/30/90 dias, exigindo 90 dias completos |
| `/v1/analysis/water`, `/agronomy`, `/economics` | Contratos existentes; cálculos pendentes |
| 11 rotas legadas de indicadores | Preservadas, ocultas no OpenAPI; duas funcionais e nove reservadas |
| `AgrionDataClient` | Transporte HTTP assíncrono com timeout/retries; sem conector de dados concreto |
| Consulta automática de I01/I02 | Retorna `503 DATA_INTEGRATION_PENDING`; não chama NASA nem inventa séries |
| NASA POWER | Fonte prevista S01 e referência metodológica; **nenhuma chamada NASA implementada no código encontrado** |
| Outras APIs NASA | Não foram encontrados conectores GPM, SMAP, HLS ou outros no projeto auditado |
| Forecast/Meteomatics, SoilGrids e FAOSTAT | Planejamento/referências; sem implementação operacional nesse projeto |

APIs HTTP efetivamente implementadas nesse diretório eram as operações internas do próprio serviço; referências NASA na documentação não constituíam integração externa concluída. Os testes encontrados usam séries sintéticas, identificadas como tais, para conferir os cálculos. Não foi reimplementada nenhuma fórmula I01/I02.

### Regressão do projeto anterior

Foi criado um ambiente de auditoria dentro de `analisys/.runtime/intelligence-audit-venv`, com as versões exatas de `requirements-dev.txt` do projeto externo. Executado a partir do diretório original:

```powershell
L:/spaceapps/spaceinvaders/analisys/.runtime/intelligence-audit-venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider --basetemp=L:/spaceapps/spaceinvaders/analisys/.runtime/intelligence-pytest
```

**217 testes aprovados, em 19,69 s**, com um aviso de depreciação de AnyIO no cliente de testes. Bytecode e cache foram desativados; o diretório temporário ficou em `analisys/`. Na prova de integração, os hashes de todos os arquivos do projeto original, excluídos ambientes/caches/metadados Git, foram comparados antes e depois e permaneceram iguais.

## Implementação de dados

### Rota e descoberta

- `POST /v1/data/nasa-power/daily` — `operationId=get_nasa_power_daily_weather`.
- `GET /v1/capabilities` — descoberta da operação INT; liga ao catálogo anterior `/api/v1/datasets`.
- Mesmo Swagger em `/docs`, mesmo `/openapi.json`, mesma API e container na porta 8001 do host. A porta 8000 do host permanece com a aplicação principal.
- Os caminhos e contratos `/api/v1/...` existentes foram preservados. O prefixo `/v1/data/...` segue o padrão do consumidor auditado e permite adaptar seu `AgrionDataClient`, que só aceita caminhos relativos `/v1/`.

### Entradas e unidades

```json
{
  "location": {"latitude": -16.5, "longitude": -49.3},
  "start_date": "2025-10-01",
  "end_date": "2025-10-03",
  "parameters": ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN"],
  "time_standard": "UTC",
  "require_complete": false
}
```

É um exemplo de requisição, sem resposta fixa. Coordenadas são WGS84; início e fim são inclusivos. Até 366 dias por consulta, início não anterior a 1981-01-01 e sem datas futuras. Não há data inicial/final padrão ou fallback para outro intervalo. Parâmetros podem ser selecionados individualmente. `UTC` é o padrão explícito; `LST` é aceito e continua LST, com `timezone=null`.

| NASA POWER | Campo diário normalizado | Unidade verificada na resposta NASA |
| --- | --- | --- |
| `T2M` | `tmean_c` | C — graus Celsius |
| `T2M_MAX` | `tmax_c` | C — graus Celsius |
| `T2M_MIN` | `tmin_c` | C — graus Celsius |
| `PRECTOTCORR` | `precip_mm_day` | mm/day |
| `RH2M` | `relative_humidity_pct` | % |
| `ALLSKY_SFC_SW_DWN` | `solar_radiation_mj_m2_day` | MJ/m²/day |

Não há conversão implícita de K, kWh ou outra unidade. Unidade divergente gera erro 502. A origem é **estimativa regional/modelada**, não leitura de sensor no talhão nem forecast. A geometria devolvida pela NASA é preservada; não é identificada como centro de célula ou elevação medida na propriedade. A resolução depende do produto de origem; não se atribui uma resolução única artificial às seis variáveis.

### Saída e qualidade

Envelope tipado v1: `contract_version`, `operation`, `status`, `result`, `method`, `provenance`, `quality`, `limitations`, `traceability`, `cache` e `generated_at`. Os schemas completos estão no OpenAPI central.

- `result.series`: uma linha por dia, com valores e `missing_parameters`.
- `result.parameters`: campos/unidades dos parâmetros selecionados. Campos de variáveis não selecionadas são `null`, mas não contam como lacuna.
- `days_complete`: dias com **todos os parâmetros selecionados** disponíveis; zero não significa necessariamente que todas as variáveis estejam ausentes.
- `quality.missing_dates`: lista de datas ausentes por parâmetro.
- Sentinel do provedor, -999, null e datas ausentes tornam-se `null`; zero de chuva é preservado como valor válido. Não há interpolação.
- Com algum dado ausente, retorna HTTP 200 e `status=partial`. Com `require_complete=true`, retorna 404 `DATA_INCOMPLETE`. Sem nenhum valor disponível, retorna 404 `DATA_UNAVAILABLE`.
- Datas ou base temporal incompatíveis, Tmin maior que Tmax, valores inválidos, unidades inesperadas e resposta malformada geram 502; não são imputados à entrada do usuário.
- Entrada inválida retorna 422 `VALIDATION_ERROR`; cota, 429; indisponibilidade de rede, 503; timeout, 504. Erros de provedor não expõem seu corpo ou stacktrace.

`provenance` preserva provedor, produtos de origem, URL consultada, data de acesso, versão da API e geometria. `traceability` traz hash do request, SHA-256 da resposta upstream e request ID. Confiança numérica e licença permanecem null: não foram inventadas. As condições de uso devem ser conferidas antes de redistribuição.

### Cache e eficiência

Cache LRU somente em memória, por coordenadas exatas, datas, parâmetros ordenados e base temporal. Não arredonda nem desloca a coordenada. `require_complete` é aplicado também em respostas de cache. TTL padrão 300 segundos, capacidade padrão 128 respostas; não retorna cache expirado em caso de falha. `accessed_at` mantém a data da consulta original em hits; `generated_at` e request ID identificam a resposta atual. Não há coleta mundial ou banco climático adicional.

Configuração pelo ambiente do container ou processo:

| Variável | Padrão | Limite |
| --- | --- | --- |
| `NASA_POWER_TIMEOUT_SECONDS` | 40 | 1–120 |
| `NASA_POWER_MAX_RETRIES` | 1 | 0–2 |
| `NASA_POWER_CACHE_TTL_SECONDS` | 300 | 0–86400; zero desativa cache |
| `NASA_POWER_CACHE_ENTRIES` | 128 | 1–1024 |

São repetidos apenas GETs após timeout, falha de rede ou erro 5xx, com espera exponencial curta. HTTP 429 não é repetido imediatamente. As chamadas por processo são serializadas para evitar rajadas/duplicação concorrente. Esses limites priorizam o MVP, sem prometer suporte a grandes volumes.

## Fonte oficial e acesso

[NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) e endpoint efetivamente consultado `https://power.larc.nasa.gov/api/temporal/daily/point`, comunidade `AG`, formato JSON. O provedor documenta UTC/LST e acesso histórico até próximo do tempo real; isso **não é forecast operacional**. As consultas desta entrega não exigiram chave de API.

## Consumo pelo AGRION

```sh
curl -X POST "http://127.0.0.1:8001/v1/data/nasa-power/daily" \
  -H "Content-Type: application/json" \
  -d '{"location":{"latitude":-16.5,"longitude":-49.3},"start_date":"2025-10-01","end_date":"2025-10-03","parameters":["T2M_MAX","T2M_MIN","PRECTOTCORR"],"time_standard":"UTC","require_complete":true}'
```

Exemplo em Bash; no Windows use o Swagger ou o Python abaixo:

```python
import httpx

response = httpx.post("http://127.0.0.1:8001/v1/data/nasa-power/daily", json={
    "location": {"latitude": -16.5, "longitude": -49.3},
    "start_date": "2025-10-01", "end_date": "2025-10-03",
    "parameters": ["T2M_MAX", "T2M_MIN", "PRECTOTCORR"],
    "time_standard": "UTC", "require_complete": True,
}, timeout=120)
response.raise_for_status()
weather = response.json()
```

Entre containers configurados na rede `agrion-analisys-data`, use `http://agrion-data:8000`. Não use `localhost:8001` dentro do container do consumidor. Não foi alterado o Flask ou o Compose principal.

## Reaproveitamento do agrion-intelligence

`src/intelligence_bridge.py` contém somente uma preparação de entrada `climate_request`: pega a resposta INT validada, verifica unidades, datas e lacunas e monta o request manual já aceito pelo `POST /v1/analysis/climate`. **Não calcula GDD, chuva ou indicadores novos.**

Para I01, utiliza todo o intervalo solicitado, a Tbase explícita e o método já existente. Só aceita UTC porque o I01 existente exige fuso IANA; não chama LST de UTC. A natureza modelada NASA não possui valor equivalente no enum antigo `data_kind`, portanto a ponte usa `unspecified`, referência com SHA-256 e preserva a proveniência INT separadamente. Para I02, seleciona os últimos 90 dias e mapeia o valor POWER em mm/day para a lâmina de cada passo de um dia (valor × 1 dia), sem aplicar essa regra a dados horários/multidiários.

Os envelopes do serviço de indicadores continuam corretamente marcados como `caller_supplied`, pois a série é entregue por um consumidor. A fonte NASA verificada é a da resposta INT, não uma atribuição retroativa no código antigo. Alterar essa procedência para integração automática exige adaptar o consumidor, seus schemas e testes deliberadamente.

## Testes e verificações reais

- **23 testes da API de dados aprovados**, incluindo os 12 anteriores e 11 novos: unidades, nulos/zero, UTC/LST, entradas inválidas, cache/expiração/capacidade/concorrência, falhas/retries/cota, OpenAPI, endpoint HTTP e ponte de consumo. Os mocks NASA são explicitamente sintéticos.
- **217 testes do projeto anterior aprovados**, com dependências fixadas conforme o projeto original.
- Container de dados reconstruído e **healthy**; `/health`, `/docs`, `/openapi.json` e `/v1/capabilities` responderam por HTTP.
- NASA real para Brasil (-16,5; -49,3) e EUA (41,5; -93,6), de 01 a 03/10/2025: HTTP 200, status ok e três dias completos, com hit de cache confirmado.
- Consulta recente brasileira, 05 a 07/11/2026: HTTP 200 partial. Temperaturas, precipitação e umidade disponíveis; radiação ausente nos três dias, preservada como null. Dados recentes não foram declarados completos artificialmente.
- Prova de 90 dias reais (06/07 a 03/10/2025) no consumidor original: GDD 1.405,185 °C·dia **sob a hipótese explícita Tbase=10 °C**, sem afirmar calibração da cultura. Chuva acumulada: 0,01 / 18,81 / 19,57 / 20,05 mm para 7/15/30/90 dias. Os resultados da rota agrupada e das legadas coincidiram.
- Hashes do projeto original antes/depois da prova confirmaram ausência de alterações.

Comandos de reprodução a partir de `analisys/`:

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -v
.venv/Scripts/python.exe -B tools/verify_nasa.py
.runtime/intelligence-audit-venv/Scripts/python.exe -B tools/verify_intelligence_bridge.py --intelligence-dir C:/Users/amarildoPaixao/Desktop/agrion-intelligence --base-temperature-c 10
```

O último comando pressupõe as dependências originais instaladas no ambiente de auditoria. Importa o app anterior em memória com TestClient, sem criar serviço/container adicional. Relatórios reais ficam em `.runtime/nasa-live-check.json` e `.runtime/intelligence-bridge-check.json`, ignorados pelo Git.

## Arquivos e execução

Novos: `src/nasa_schemas.py`, `src/nasa_power.py`, `src/nasa_routes.py`, `src/intelligence_bridge.py`, `tests/test_nasa.py`, `tools/verify_nasa.py`, `tools/verify_intelligence_bridge.py` e este relatório. Atualizados: `src/main.py`, `compose.yaml`, `README.md`, `docs/API.md` e a referência histórica em `docs/VALIDACAO.md`. O Compose repassa as quatro configurações NASA do host ao serviço de dados. Não houve alteração de dependências, fontes originais ou instruções do projeto externo.

Execução local e Docker continuam conforme [API.md](API.md). Reconstrua somente o serviço de dados com `docker compose -f analisys/compose.yaml up -d --build` a partir da raiz. Não foi feito commit, push ou merge desta continuação.

## Pendências

1. O modo automático **dentro de agrion-intelligence** continua 503. O contrato real está agora disponível; o responsável por esse projeto deve adicionar o adaptador `AgrionDataClient → /v1/data/nasa-power/daily`, manter a procedência real e preservar os quatro operationIds e as rotas legadas. A prova manual não deve ser anunciada como modo automático concluído.
2. Conectar Flask/assistente à API de dados e, quando desejado, ao serviço de indicadores, no trabalho do desenvolvedor principal.
3. I03, I05, I07, I08, I09, I10, I11, I13 e I14 continuam não implementados no projeto auditado. Não foram recriados como parte desta integração.
4. Forecast operacional, ETo/ETc, balanço hídrico e execução AquaCrop não foram acrescentados. A disponibilidade de radiação recente depende da atualização NASA.
5. HWSD/SoilGrids, fontes financeiras FAOSTAT/CONAB e outras integrações externas continuam frentes separadas. Nenhum conector NASA adicional foi presumido ou criado sem necessidade.
