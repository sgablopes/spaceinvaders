# Meteomatics — integração de previsões meteorológicas

- **Categoria:** INT forecast, conforme o planejamento AGRION.
- **Serviço:** mesma API FastAPI e container de `analisys/`, sem alterações no Flask.
- **Situação:** conector, autenticação, endpoint, schemas e testes implementados. **Previsões reais autenticadas NÃO VALIDADAS: credenciais não disponíveis neste ambiente.** A consulta real sem autenticação confirmou HTTP 401 do provedor.

## Fonte e contrato verificados

Consultada a documentação oficial da [Meteomatics](https://www.meteomatics.com/en/api/getting-started/), incluindo [JSON](https://www.meteomatics.com/en/api/response/json/), [seleção de fonte](https://www.meteomatics.com/en/api/request/optional-parameters/), [períodos](https://www.meteomatics.com/en/api/request/required-parameters/date-time-description/), [valores reservados](https://www.meteomatics.com/en/api/response/reserved-values/) e [códigos HTTP](https://www.meteomatics.com/en/api/response/api-response-error-codes/).

A requisição externa usa o host fixo HTTPS `api.meteomatics.com`, datas UTC, uma coordenada, parâmetros autorizados pelo conector e formato JSON, com `source` explícito. O usuário não pode enviar URL de provedor, headers de autenticação ou credenciais pelo contrato AGRION. Basic Auth é aplicado no servidor por `httpx.BasicAuth`; não há usuário/senha embutidos em URL ou arquivo de código. A documentação também descreve OAuth; não foi necessário acrescentar esse segundo fluxo de autenticação ao MVP.

## Endpoint e parâmetros AGRION

**`POST /v1/data/meteomatics/forecast`**, operationId **`get_meteomatics_forecast`**.

O mesmo `/docs` e `/openapi.json` apresenta os contratos completos. `/v1/capabilities` e `/api/v1/datasets` identificam o conector e informam somente se as credenciais foram configuradas, sem expor valores. `configured_unverified` não comprova login ou permissão; `credentials_missing` identifica ausência de configuração. O catálogo preserva NASA INT e as quatro operações IND existentes.

| Parâmetro do request | Parâmetro oficial | Campo normalizado | Unidade/semântica |
| --- | --- | --- | --- |
| `temperature` | `t_2m:C` | `temperature_c` | °C instantâneo a 2 m |
| `temperature_mean` | `t_mean_2m_{N}h:C` | `temperature_mean_c` | °C, média no intervalo |
| `temperature_min` | `t_min_2m_{N}h:C` | `temperature_min_c` | °C, mínima no intervalo |
| `temperature_max` | `t_max_2m_{N}h:C` | `temperature_max_c` | °C, máxima no intervalo |
| `precipitation` | `precip_{N}h:mm` | `precipitation_mm` | mm acumulados no intervalo, não taxa mm/h |
| `relative_humidity` | `relative_humidity_2m:p` | `relative_humidity_pct` | % instantâneo a 2 m |
| `wind_speed` | `wind_speed_10m:ms` | `wind_speed_10m_m_s` | m/s instantâneo a 10 m |
| `solar_radiation` | `global_rad:W` | `solar_radiation_w_m2` | W/m² instantâneo, não energia diária |

Os códigos e a semântica são documentados nas páginas oficiais de [temperatura](https://www.meteomatics.com/en/api/available-parameters/weather-parameter/temperature/), [precipitação](https://www.meteomatics.com/en/api/available-parameters/weather-parameter/precipitation/), [umidade](https://www.meteomatics.com/en/api/available-parameters/weather-parameter/humidity/), [vento](https://www.meteomatics.com/en/api/available-parameters/weather-parameter/standard-weather-parameters-wind/) e [radiação](https://www.meteomatics.com/en/api/available-parameters/weather-parameter/radiation/).

`N` é `step_hours`: 1, 3, 6 ou 24. Por padrão são solicitadas apenas temperatura instantânea, chuva, umidade e vento, para reduzir volume e dependências de acesso. As outras variáveis são selecionáveis explicitamente.

## Tempo, horizonte e dados ausentes

- `location`: latitude/longitude WGS84.
- `start_time` e `end_time`: timestamps ISO 8601 com fuso, normalizados para UTC, alinhados à hora inteira. O final é inclusivo e a diferença deve ser divisível por `step_hours`. Epoch numérico e horário sem fuso são rejeitados.
- `start_time` é o **primeiro horário de validade**, não necessariamente o início do primeiro acumulado. Extremos/médias e precipitação abrangem o intervalo anterior encerrado em `valid_time`. A resposta informa `interval_start` e a semântica por parâmetro; campos instantâneos continuam instantâneos.
- O primeiro instante/intervalo deve estar inteiramente no futuro. Ex.: para `step_hours=24`, o primeiro acumulado cobre as 24 horas anteriores ao primeiro `valid_time`; não é chamado automaticamente de dia civil local.
- Limite operacional padrão deste serviço: até 7 dias a partir de agora, configurável entre 1 e 16 dias. **Isso não garante que o plano/modelo ofereça esse horizonte.** Não há extrapolação ou tentativa de previsão de 90 dias.
- Fontes selecionáveis: `mix` (padrão), `ecmwf-ifs` e `ncep-gfs`. A conta precisa autorizar a fonte e os parâmetros. Não é atribuída resolução universal de 90 m ou precisão de talhão.
- `result.available_end_by_parameter` informa o último ponto válido retornado de cada variável; não garante cobertura contínua. `quality.missing_times` identifica as lacunas internas ou finais.
- Valores reservados -999/-888/-777/-666, null e horários/parâmetros ausentes viram `null`. Zero de chuva continua válido. Se parte faltar, retorna HTTP 200 `partial`; se nada estiver disponível, 404.
- `require_complete=true` rejeita lacunas ou cobertura parcial HTTP 206 do provedor com 404 `DATA_INCOMPLETE`. A indicação 206 é preservada na procedência, mesmo quando os pontos JSON presentes forem válidos.

Não são calculados ETo, agregação diária, conversão de radiação em energia, vento a 2 m ou indicadores a partir dessas previsões nesta entrega. O consumo é separado da NASA histórica e das somas retrospectivas I02 já existentes.

## Autenticação e configuração

Configure **`METEOMATICS_USERNAME`** e **`METEOMATICS_PASSWORD`** no ambiente do processo/serviço, usando as credenciais da conta Meteomatics. Não envie esses valores pelo chat, request JSON, URL ou parâmetros de consulta. O Compose de `analisys/` já repassa essas variáveis ao único serviço existente.

`.env.example` contém somente nomes e valores não secretos de configuração. `.env`/`.env.*` locais são ignorados pelo Git e `.dockerignore` exclui arquivos de ambiente; a imagem usa apenas código, dependências e fontes autorizadas. Nenhum segredo foi criado, copiado ou embutido na imagem nesta implementação.

| Variável | Padrão | Limite |
| --- | --- | --- |
| `METEOMATICS_USERNAME` | vazio | Credencial obrigatória para consultar |
| `METEOMATICS_PASSWORD` | vazio | Credencial obrigatória para consultar |
| `METEOMATICS_TIMEOUT_SECONDS` | 30 | 1–120 |
| `METEOMATICS_MAX_RETRIES` | 1 | 0–2 |
| `METEOMATICS_CACHE_TTL_SECONDS` | 300 | 0–3600; zero desativa |
| `METEOMATICS_CACHE_ENTRIES` | 64 | 1–512 |
| `METEOMATICS_MAX_FORECAST_DAYS` | 7 | 1–16; limite da aplicação, não promessa do provedor |

Com o ambiente configurado, a partir da raiz:

```sh
docker compose -f analisys/compose.yaml up -d --build --wait --wait-timeout 60
```

Recrie o container após alterar o ambiente; uma imagem existente não recebe variáveis novas apenas por mudar o terminal. O serviço fica em `127.0.0.1:8001`. Em uma rede Docker compartilhada, consumidores usam `http://agrion-data:8000`, sem alterar a aplicação principal neste trabalho. Para execução local, o Python lê o ambiente do processo; não carrega automaticamente um `.env`.

TLS permanece verificado e redirects e proxies herdados do ambiente HTTP são desabilitados no cliente de produção. Autenticação fica apenas no header enviado ao host fixo. Corpos de erro do provedor, seu campo JSON `user` e headers de autenticação não são retornados nem registrados pelo código do conector. O erro do AGRION usa mensagens estáticas; não expõe stacktrace ou detalhes da conta.

## Consumo sem credenciais no cliente AGRION

Exemplo Python com horários calculados no momento da consulta, sem segredo no request:

```python
from datetime import datetime, timedelta, timezone
import httpx

start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
payload = {
    "location": {"latitude": -16.5, "longitude": -49.3},
    "start_time": start.isoformat(),
    "end_time": (start + timedelta(hours=6)).isoformat(),
    "step_hours": 1,
    "parameters": ["temperature", "temperature_min", "temperature_max", "precipitation",
                   "relative_humidity", "wind_speed", "solar_radiation"],
    "source": "mix",
    "require_complete": False,
}
response = httpx.post("http://127.0.0.1:8001/v1/data/meteomatics/forecast", json=payload, timeout=120)
response.raise_for_status()
forecast = response.json()
```

O exemplo é uma requisição ilustrativa. Os valores meteorológicos virão do provedor autenticado; não existe resposta fixa ou fixture de produção. Se salvar esse JSON como `forecast-request.json`, pode usar:

```sh
curl -X POST "http://127.0.0.1:8001/v1/data/meteomatics/forecast" -H "Content-Type: application/json" --data-binary @forecast-request.json
```

O envelope tipado contém `contract_version`, `operation`, `status`, `result.series`, metadados/unidades por variável, `method`, `provenance`, `quality`, `limitations`, cache e hashes. `provenance.kind=operational_forecast`; `provider_generated_at` preserva `dateGenerated` da resposta. **Não é tratado como horário de inicialização do modelo**; `forecast_reference_time=null`, pois não foi feita consulta adicional a `get_init_date`. `source_requested` distingue a seleção de fonte da identificação de um modelo real, especialmente em `mix`.

## Cache e erros

Cache em memória por coordenada exata, fonte, parâmetros ordenados, horários e passo. É limitado por TTL/capacidade, não arredonda coordenadas, não persiste credenciais e nunca devolve cache expirado como fallback de previsão. `accessed_at` permanece o da fonte em hits; `generated_at` e request ID mudam. A validade futura é conferida também antes de retornar cache.

| HTTP AGRION | Código | Motivo |
| --- | --- | --- |
| 503 | `METEOMATICS_CREDENTIALS_MISSING` | Ambiente sem usuário/senha completos; nenhuma chamada upstream |
| 503 | `UPSTREAM_AUTHENTICATION_FAILED` | Meteomatics retornou 401; revisar credenciais do serviço |
| 503 | `UPSTREAM_ACCESS_DENIED` | Meteomatics retornou 402/403; revisar plano/permissões |
| 429 | `UPSTREAM_RATE_LIMITED` | Cota/limite; não há repetição imediata |
| 404 | `DATA_UNAVAILABLE` / `DATA_INCOMPLETE` | Sem dados ou incompleto quando exigida cobertura total |
| 422 | `VALIDATION_ERROR` / `FORECAST_PERIOD_INVALID` | Entrada, período futuro ou limite da aplicação inválido |
| 502 | `UPSTREAM_INVALID_RESPONSE` / `UPSTREAM_REJECTED` | Formato, unidades/códigos, coordenadas ou consulta incompatíveis |
| 502/503/504 | erro transitório/timeout | Falha de provedor/rede ou tempo limite |

Apenas GETs com falhas de rede, timeout, HTTP 408 ou 5xx têm retentativas limitadas. Login, permissões e cota não são repetidos automaticamente. Não há fallback para NASA, valores zero ou respostas sintéticas.

## Validação e limitações reais

Verificados sem revelar valores: as variáveis Meteomatics estavam ausentes no processo, usuário e máquina, e nenhum arquivo de credenciais foi localizado em `analisys/`. Portanto **não é possível aprovar previsões autenticadas, cobertura, plano ou licença de redistribuição nesta etapa**.

Na prova real:

- Container saudável e endpoint presente no mesmo OpenAPI.
- Chamada ao endpoint AGRION retornou 503 `METEOMATICS_CREDENTIALS_MISSING`.
- Uma única chamada sem autenticação ao endpoint oficial retornou **401**, confirmando a dependência de acesso. Isso não foi declarado como previsão validada.
- A regressão real NASA → I01/I02 continuou retornando 200 nas provas brasileira, internacional e recente, com valores equivalentes entre rotas agrupada e legadas.

**45 testes aprovados em 32,333 s**, sendo 31 regressões existentes e 14 novos de Meteomatics. Os testes meteorológicos usam somente fixtures sintéticas identificadas, cobrindo Basic Auth, sigilo, JSON, parâmetros/unidades, instantes e intervalos, UTC, ausências, HTTP 206, horizonte, cache, permissões/cota, erros e schema/catálogo. A verificação real foi feita separadamente e não substituída pelos mocks.

Reprodução a partir de `analisys/`:

```sh
python -B -m unittest discover -s tests -v
python -B tools/verify_meteomatics.py
```

O segundo comando tenta consultar o serviço real conforme a configuração do container. Opcionalmente, `--probe-unauthenticated` confirma somente a exigência de login, sem segredo. O relatório normalizado fica em `.runtime/meteomatics-live-check.json`, ignorado pelo Git, e informa `weather_data_validated=false` enquanto a consulta real não for bem-sucedida.

## Arquivos e pendências

Criados: `src/meteomatics_schemas.py`, `src/meteomatics.py`, `src/meteomatics_routes.py`, `tests/test_meteomatics.py`, `tools/verify_meteomatics.py`, `.env.example` e este relatório. Atualizados: `src/main.py`, `src/nasa_routes.py` (somente catálogo), `compose.yaml`, `.gitignore`, README e documentação de consumo. Não foram alterados o conector NASA, suas fórmulas de indicadores, os arquivos originais ou a aplicação principal. Não foram adicionadas dependências.

Pendências: configurar conta válida no ambiente do serviço, confirmar acesso a cada parâmetro/fonte e horizonte do plano e repetir as consultas reais autenticadas. Integração dessas previsões em modelos/indicadores futuros, agregação diária para AquaCrop e ETo não foram presumidas como concluídas nem implementadas fora do pedido atual.

Não houve commit, push, merge ou publicação remota nesta continuação. As alterações anteriores pendentes em `analisys/` foram preservadas.
