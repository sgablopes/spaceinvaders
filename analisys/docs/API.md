# API de dados agronômicos — v1

## Execução isolada

Na raiz do repositório:

```sh
docker compose -f analisys/compose.yaml up -d --build
docker compose -f analisys/compose.yaml ps
```

A porta 8001 do host precisa estar livre. `ANALISYS_PORT` permite escolher outra porta, preservando 8000 para a aplicação principal. A publicação é restrita a `127.0.0.1`; o container executa como usuário sem privilégios, com sistema de arquivos somente para leitura e volume próprio para o índice. Apenas uma instância/worker deve construir esse índice por volume.

- Saúde: `http://127.0.0.1:8001/health`
- Documentação interativa: `http://127.0.0.1:8001/docs`
- OpenAPI: `http://127.0.0.1:8001/openapi.json`
- Catálogo: `http://127.0.0.1:8001/api/v1/datasets`

Outros containers podem acessar `http://agrion-data:8000` quando estiverem conectados à rede `agrion-analisys-data`. O desenvolvedor principal deve configurar essa rede e a URL no seu próprio Compose; nenhum arquivo da aplicação foi alterado. O `localhost` de outro container não aponta para este serviço. O consumo previsto é servidor a servidor; não há configuração de CORS ou autenticação para publicação externa nesta entrega.

Alternativa local com Python 3.12, a partir de `analisys/`:

```sh
python -m venv .venv
# Ative .venv conforme o sistema.
python -m pip install -r requirements.txt
python -B -m uvicorn src.main:app --host 127.0.0.1 --port 8001
```

## O que está disponível

| Prefixo | Conteúdo real |
| --- | --- |
| `/api/v1/ecocrop` | 2.568 culturas, requisitos, alertas, 15.760 nomes/sinônimos, originais e dicionário |
| `/api/v1/fao56` | Tabelas de Kc/Kcb, água, GDD, salinidade, Ky, 3.097 parâmetros atômicos, auditorias e limitações |
| `/api/v1/conhecimento` | Biblioteca v0.4: 45 culturas, 149 fontes, 249 evidências, 75 sequências, 42 calendários, 48 registros fitossanitários, 20 registros de manejo e tabelas de associação |
| `/api/v1/aquacrop` | Dicionário de 62 campos e estrutura das entradas; as cinco abas de entrada estão vazias |
| `/api/v1/gaez` | Descoberta de camadas na API externa oficial e consulta do pixel remoto por coordenada |
| `POST /v1/data/nasa-power/daily` | Temperaturas média/mínima/máxima, precipitação, umidade e radiação NASA POWER sob demanda |
| `POST /v1/data/meteomatics/forecast` | Previsão UTC autenticada Meteomatics, dependente de credenciais e permissões |
| `POST /v1/analysis/climate` | GDD e chuva acumulada, usando séries próprias ou NASA automaticamente |
| `POST /v1/analysis/water`, `/agronomy`, `/economics` | Contratos dos demais grupos originais; métodos pendentes, com 501 explícito |

HWSD tem somente um README nesta pasta; raster e MDB não estão disponíveis. O Parquet ECOCROP e o contrato climático mencionado anteriormente também não estão no disco. Cálculo FAO-56 de ETo, motor AquaCrop e recomendações agronômicas não foram implementados por esta API de consulta. A consulta NASA POWER foi acrescentada sem alterar os caminhos anteriores.

## NASA POWER diário

`POST /v1/data/nasa-power/daily`, operationId `get_nasa_power_daily_weather`, disponibiliza dados históricos/quase tempo real. O contrato completo, exemplos Python/curl, erros, proveniência e auditoria do consumidor estão em [DELIVERY_S01.md](DELIVERY_S01.md). A documentação técnica continua centralizada no mesmo `/docs` e `/openapi.json`; `/v1/capabilities` lista a operação INT e aponta para o catálogo das outras fontes.

```json
{
  "location": {"latitude": -16.5, "longitude": -49.3},
  "start_date": "2025-10-01",
  "end_date": "2025-10-03",
  "parameters": ["T2M_MAX", "T2M_MIN", "PRECTOTCORR"],
  "time_standard": "UTC",
  "require_complete": true
}
```

Até 366 dias inclusivos, sem datas futuras; não fornece forecast. `result.series` contém valores diários, `result.parameters` declara unidades, `quality.missing_dates` identifica lacunas, `provenance` e hashes identificam fonte e versão consultadas. Sem `require_complete`, lacunas geram status `partial` e null; com ele, erro 404. Zero de chuva não é lacuna. UTC e LST não são convertidos nem equiparados.

O cache em memória tem TTL padrão 300 segundos e capacidade 128, configuráveis. São preservadas a data de acesso da fonte e a expiração; não existe fallback para cache vencido. Os parâmetros `NASA_POWER_TIMEOUT_SECONDS`, `NASA_POWER_MAX_RETRIES`, `NASA_POWER_CACHE_TTL_SECONDS` e `NASA_POWER_CACHE_ENTRIES` podem ser passados pelo ambiente ao processo/container. O Compose do serviço de dados já repassa essas quatro variáveis do host, mantendo os padrões quando ausentes.

## Indicadores com consulta automática

`POST /v1/analysis/climate` recebe `include` e `inputs` tipados. I01/I02 reutilizam as fórmulas anteriores; omitir a série seleciona NASA automaticamente. Exemplo ilustrativo de GDD, com Tbase informada como hipótese explícita:

```json
{
  "include": ["I01"],
  "inputs": {
    "gdd": {
      "location": {"latitude": -16.5, "longitude": -49.3},
      "crop_id": "maize", "base_temperature_c": 10,
      "start_date": "2025-10-01", "end_date": "2025-10-03", "timezone": "UTC"
    }
  }
}
```

Para chuva, selecione `include=["I02"]` e `inputs.rainfall` com `location`, `reference_date` e `day_basis` (`UTC` ou `LST`); não exige Tbase. Consulta os 90 dias até a referência e devolve as quatro somas retrospectivas. Ambos podem ser selecionados na mesma requisição, com períodos próprios. Não há conversão de LST para UTC nem substituição de lacunas por zero. GDD automático admite até 366 dias e somente UTC; períodos maiores continuam possíveis no modo manual conforme o contrato anterior.

Fornecer `daily_temperatures`/`daily_precipitation` preserva o modo manual sem rede. Em automático a procedência é `NASA POWER`/`modeled_estimate`; em manual é `caller_supplied`. Sucesso parcial identifica cada ID indisponível sem valor substituto. `/v1/capabilities` inclui a operação INT existente e as quatro operações IND com seus estados; rotas legadas permanecem ocultas do OpenAPI. Os demais nove cálculos seguem 501.

Métodos, schemas estendidos de saída, erros, exemplo completo I01/I02 e validação estão em [DELIVERY_AUTOMATIC_INDICATORS.md](DELIVERY_AUTOMATIC_INDICATORS.md). A API usa o núcleo versionado internamente, sem depender de arquivos da Área de Trabalho.

## Previsão Meteomatics

`POST /v1/data/meteomatics/forecast`, operationId `get_meteomatics_forecast`, é uma operação INT separada do histórico NASA, no mesmo Swagger/container. Recebe `location`, `start_time`, `end_time`, `step_hours` (1/3/6/24), `parameters`, `source` e `require_complete`. Timestamps têm fuso explícito e são normalizados para UTC; instantes e primeiros intervalos devem estar inteiramente no futuro. Por padrão o serviço limita o fim a 7 dias a partir de agora, sem garantir o horizonte autorizado pelo plano.

Variáveis selecionáveis: `temperature`, `temperature_mean`, `temperature_min`, `temperature_max`, `precipitation`, `relative_humidity`, `wind_speed` e `solar_radiation`. Acumulados/extremos/médias abrangem o intervalo anterior encerrado em `valid_time`, com duração igual a `step_hours`. Vento é instantâneo a 10 m e radiação é fluxo instantâneo em W/m²; não se presume uma série diária pronta para AquaCrop. A previsão não alimenta automaticamente os indicadores retrospectivos NASA nesta entrega.

As credenciais `METEOMATICS_USERNAME` e `METEOMATICS_PASSWORD` são lidas apenas do ambiente do serviço. O cliente AGRION não as envia no request; a API usa Basic Auth em HTTPS com host fixo, sem segredo na URL e sem repassar o campo `user` do provedor. Quando faltam, retorna 503 `METEOMATICS_CREDENTIALS_MISSING`; a NASA e as fontes locais continuam disponíveis. `/v1/capabilities` informa presença de configuração, sem atestar que a conta tem acesso.

O conector tem cache limitado, retentativas controladas, resposta tipada com procedência/hashes e ausência representada por null/partial. Não há fallback para NASA ou valores fictícios. Configuração completa, tabela de unidades, fontes oficiais, tratamento de erros e exemplo Python que calcula os horários no momento da requisição estão em [DELIVERY_METEOMATICS.md](DELIVERY_METEOMATICS.md).

## Contrato das fontes locais

Para cada prefixo local:

| Método e sufixo | Retorno |
| --- | --- |
| `GET /tables` | Nomes de tabelas, colunas originais, total e localizador da origem |
| `GET /tables/{table}` | Metadados da tabela específica |
| `GET /{table}` | Página de registros da tabela |

Nomes de tabela são os nomes das abas em minúsculas ou o nome do CSV sem extensão. Os nomes das colunas conservam maiúsculas e unidades originais. Use `/tables` para descobri-los; não há SQL arbitrário pela API.

Parâmetros de consulta:

- `limit`: 1–500, padrão 50.
- `offset`: posição inicial, padrão 0. A ordem é a linha da fonte.
- `q`: trecho de texto, sem distinção de caixa ou acentos, buscado em todos os valores da linha. Busca em sinônimos deve usar `ecocrop/nomes_sinonimos`; a busca em culturas não faz junção automática.
- `filtros`: objeto JSON de igualdades exatas combinadas com AND. Aceita colunas existentes e valores escalares ou `null`. Os tipos seguem a fonte: números Excel são números JSON, mas números e IDs dos CSVs continuam texto para preservar a representação. `null` seleciona valores ausentes; zero continua zero.

Resposta de página:

```json
{
  "dataset": "ecocrop",
  "table": "requisitos",
  "total": 1,
  "limit": 50,
  "offset": 0,
  "source": {"file": "...", "sha256": "...", "sheet": "REQUISITOS", "warnings": []},
  "items": [{"source_row": 2, "data": {"crop_id": "ECO_289", "temp_abs_min_C": 12}}]
}
```

O exemplo mostra apenas parte dos campos. `total` conta o resultado filtrado antes da paginação. `source_row` é a linha física da planilha/registro CSV, incluindo o cabeçalho como linha 1; use IDs da fonte para relações persistentes. A SHA-256 identifica a versão exata do arquivo consultado. Dados em `data` mantêm a estrutura da tabela; o dicionário da própria fonte define unidades e formatos. Datas Excel são serializadas em ISO 8601; datas que já eram texto permanecem texto. Vazios são `null`.

Exemplos com `curl` (no PowerShell, use `curl.exe`):

```sh
curl "http://127.0.0.1:8001/api/v1/ecocrop/tables"
curl -G "http://127.0.0.1:8001/api/v1/ecocrop/nomes_sinonimos" --data-urlencode "q=quiabo"
curl -G "http://127.0.0.1:8001/api/v1/ecocrop/requisitos" --data-urlencode 'filtros={"crop_id":"ECO_289"}'
curl -G "http://127.0.0.1:8001/api/v1/fao56/indice_atomico" --data-urlencode 'filtros={"Parametro":"kc_ini"}' --data-urlencode "limit=10"
curl -G "http://127.0.0.1:8001/api/v1/conhecimento/rotacoes" --data-urlencode 'filtros={"sucessora_id":"feijao"}'
curl "http://127.0.0.1:8001/api/v1/conhecimento/documentos/manifesto.json"
curl "http://127.0.0.1:8001/api/v1/aquacrop/tables/clima_diario"
```

Exemplo Python para o desenvolvedor principal:

```python
import json
import httpx

with httpx.Client(base_url="http://127.0.0.1:8001", timeout=30) as client:
    response = client.get("/api/v1/ecocrop/requisitos", params={
        "filtros": json.dumps({"crop_id": "ECO_289"}),
        "limit": 50,
    })
    response.raise_for_status()
    page = response.json()
    requisitos = [item["data"] for item in page["items"]]
```

Para obter todas as páginas, aumente `offset` pelo número de itens retornados até atingir `total`. Não presuma que a primeira página é toda a base.

## Evidências, auditorias e limitações

`GET /api/v1/conhecimento/documentos` lista manifesto, dicionário e relatórios JSON/Markdown preservados dentro do ZIP; `GET /api/v1/conhecimento/documentos/{name}` retorna seu conteúdo. Os históricos CSV e a quarentena não entram nas tabelas ativas. A carga verifica os checksums do manifesto antes de disponibilizar a biblioteca.

Recupere `evidencias` por `evidencia_id` e `fontes` por `fonte_id` ao consumir uma rotação, calendário ou prática. Os vínculos multicultura estão em `evidencia_culturas` e `fonte_culturas`. Não há correspondência automática entre IDs da biblioteca, ECOCROP e códigos GAEZ. Use `estudo_id` para evitar contar tratamentos do mesmo estudo como evidências independentes.

Os status de conferência documental, suficiência e validação agronômica são preservados. A API permite consultar registros condicionados para revisão, sem promovê-los a recomendações. A relação mandioca → milho está explicitamente sinalizada como pendência. Para FAO-56, consulte `auditoria_registros`, `alertas_revisao` e `limitacoes_metodologicas` antes de usar números: células multivalor, faixas e variantes permanecem na forma original. O índice atômico não substitui essa auditoria.

## GAEZ v5 externo

A integração consulta a [API JSON de objetos do Google Cloud Storage](https://docs.cloud.google.com/storage/docs/json_api/v1/objects/list) no bucket público FAO `fao-gismgr-gaez-v5-data`, apontado pelo [guia oficial GAEZ](https://github.com/un-fao/gaezv5/wiki/21.-GAEZ-v5-Platform-User-Guide). A [ferramenta oficial de acesso](https://github.com/un-fao/gaezv5/tree/main/GAEZ-v5-Platform/Data-Access-Notebooks) também usa os GeoTIFFs desse bucket. O Rasterio lê o arquivo remoto por HTTP; a base global não é importada para o SQLite nem baixada integralmente pelo serviço.

1. `GET /api/v1/gaez/layers?variable=RES05-SIX&filename_prefix=GAEZ-V5.RES05-SIX.HP0120&limit=500` consulta as camadas. `variable` é o código da pasta; `filename_prefix` é opcional e exige `variable`. O catálogo sem variável também pode ser consultado.
2. Se houver `next_page_token`, envie-o como `page_token` na próxima consulta, mantendo os demais filtros. A página externa pode não ter GeoTIFFs e ainda conter token de continuação. Não interprete página vazia como fim se houver token.
3. Escolha `items[].layer` da cultura, manejo, período e modelo desejados e envie-o para `GET /api/v1/gaez/point`, junto de `latitude` e `longitude` em graus WGS84.

Exemplo real de camada consultada nesta implementação:

```python
import httpx

layer = "DATA/GAEZ-V5/MAPSET/RES05-SIX/GAEZ-V5.RES05-SIX.HP0120.AGERA5.HIST.SOY.HRLM.tif"
response = httpx.get("http://127.0.0.1:8001/api/v1/gaez/point", params={
    "layer": layer, "latitude": -16.5, "longitude": -49.3,
}, timeout=90)
response.raise_for_status()
pixel = response.json()
```

A resposta inclui `raw_value`, `value` após escala/offset declarados na banda, `status` (`ok` ou `nodata`), `unit` quando declarada, resolução nas unidades do CRS, tags, dimensões codificadas no nome, metadados do objeto externo, URL e data de consulta. O nome é preservado para verificar produto e cenário; interpretar os códigos exige a documentação do produto. Em NoData, os valores são `null`. Fora da cobertura retorna 404.

**Não assumir escala ou unidade científica quando faltarem no GeoTIFF.** Na consulta real de soja feita nesta etapa, o GeoTIFF retornou valor bruto 3, escala 1, offset 0 e unidade ausente. Isso não foi transformado em porcentagem ou produtividade. A resolução retornada foi 0,083333°; não atribua resolução de 1 km automaticamente. O transporte externo e a leitura pontual estão validados; interpretação agronômica dos códigos/classes de cada produto ainda depende de validação específica. Latência e quantidade de blocos lidos dependem da organização do raster remoto.

## Erros

As respostas de erro das rotas anteriores `/api/v1/...` usam `detail`, conforme FastAPI. A nova rota NASA `/v1/data/...` preserva seu contrato próprio com `error.code`, `message`, `retryable` e `details`, conforme [DELIVERY_S01.md](DELIVERY_S01.md).

- 404: tabela/documento/camada inexistente ou coordenada fora da cobertura.
- 422: parâmetros, filtros ou identificador de camada inválidos.
- 502: falha da fonte externa ou da leitura remota GAEZ.
- 504: timeout da consulta HTTP de catálogo/metadados GAEZ. Falhas de leitura GDAL são reportadas como 502.

`/health` verifica o serviço e o índice local, sem fazer chamadas GAEZ, NASA ou Meteomatics. Indisponibilidade externa e credenciais Meteomatics ausentes não impedem a consulta das bases locais. Não são gerados valores fictícios como fallback.

## Armazenamento e atualização

SQLite foi escolhido como índice local, sem servidor de banco adicional, pois as fontes presentes totalizam aproximadamente 2,4 MB e são essencialmente estáticas. As tabelas normalizadas das planilhas e CSVs são a origem prioritária; tabelas originais e auditorias também ficam disponíveis para rastreabilidade. Nenhuma inferência, conversão de unidade agronômica ou correção dos arquivos é aplicada na carga.

O índice fica em `.runtime/catalog.sqlite3` no modo local, ou no volume `catalog` do projeto Compose. A carga ocorre no início, e as consultas usam conexões somente de leitura. As tabelas são particionadas logicamente por fonte/aba e indexadas por fonte, tabela e linha; buscas textuais e filtros JSON percorrem a tabela selecionada. Não é uma promessa de desempenho para bases muito maiores.

No início do serviço, SHA-256 dos quatro arquivos e versão do esquema são comparados ao índice. Se mudarem, a carga reconstrói um arquivo temporário e o substitui somente após sucesso. Se uma fonte estiver ausente ou o manifesto falhar, a inicialização falha explicitamente. Não há atualização automática durante requisições.

Para atualizar, entregue uma nova edição autorizada dos arquivos preservando a anterior no fluxo de dados da equipe e execute novamente `docker compose -f analisys/compose.yaml up -d --build`. Os arquivos de origem são copiados para a imagem; reiniciar sem rebuild não atualiza esses arquivos. A compatibilidade do contrato deve ser revisada quando cabeçalhos ou IDs mudarem.

## Testes

A partir de `analisys/`, com as dependências instaladas:

```sh
python -B -m unittest discover -s tests -v
python -B tools/verify_external.py
```

O primeiro comando roda 45 testes determinísticos: os 12 iniciais, 11 da entrega NASA, 8 da conexão automática aos indicadores e 14 do conector Meteomatics. As fontes locais reais são verificadas por contagens, nulos/zero, relações, quarentena, paginação, filtros, reuso do índice e hashes antes/depois. Mocks meteorológicos e raster de teste são **sintéticos**, cobrindo unidades, falhas externas, NoData, autenticação segura, cache e contrato HTTP, sem chamadas externas nos testes automatizados.

O segundo comando é opcional e acessa a rede real. Grava `.runtime/gaez-live-check.json`, identificando expressamente que são consultas externas reais. Esse relatório não é uma recomendação agronômica.

Com o serviço já iniciado, `python -B tools/verify_running.py` valida o acesso HTTP em `127.0.0.1:8001`, incluindo pixels GAEZ reais de milho (`MZE`) e soja (`SOY`). Pode receber outra URL local como argumento. O relatório fica em `.runtime/http-check.json`. Consulte [VALIDACAO.md](VALIDACAO.md) para os resultados desta entrega.

`python -B tools/verify_nasa.py` faz consultas NASA reais no Brasil, no exterior e em intervalo recente, verifica o cache e salva `.runtime/nasa-live-check.json`. A prova de reaproveitamento do consumidor original está descrita em [DELIVERY_S01.md](DELIVERY_S01.md); ela preserva seus arquivos e não cria novas operações de análise.

`python -B tools/verify_automatic_indicators.py` valida o fluxo NASA → GDD/chuva diretamente por HTTP no container único, sem o consumidor externo; compara rotas agrupada e legadas e salva `.runtime/automatic-indicators-check.json`.

`python -B tools/verify_meteomatics.py` tenta a consulta forecast real usando apenas as credenciais configuradas no servidor. Sem elas, registra a indisponibilidade; `--probe-unauthenticated` verifica somente a exigência de login no provedor. A evidência em `.runtime/meteomatics-live-check.json` não declara previsão validada enquanto não houver consulta autenticada bem-sucedida.
