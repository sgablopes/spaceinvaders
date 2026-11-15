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

HWSD tem somente um README nesta pasta; raster e MDB não estão disponíveis. O Parquet ECOCROP e o contrato climático mencionado anteriormente também não estão no disco. NASA POWER, cálculo FAO-56 de ETo, motor AquaCrop e recomendações agronômicas não foram implementados por esta API de consulta.

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

As respostas de erro usam `detail`, conforme FastAPI:

- 404: tabela/documento/camada inexistente ou coordenada fora da cobertura.
- 422: parâmetros, filtros ou identificador de camada inválidos.
- 502: falha da fonte externa ou da leitura remota GAEZ.
- 504: timeout da consulta HTTP de catálogo/metadados GAEZ. Falhas de leitura GDAL são reportadas como 502.

`/health` verifica o serviço e o índice local, sem fazer chamadas GAEZ. Indisponibilidade externa não impede a consulta das bases locais. Não são gerados valores fictícios como fallback.

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

O primeiro comando roda 12 testes determinísticos: fontes reais, contagens, nulos/zero, relações, exclusão da quarentena, paginação, filtros inválidos/injeção, reuso do índice, esquema OpenAPI e falhas externas. O teste de pixel utiliza raster **sintético**, cobrindo escala, NoData e limites espaciais. Os hashes dos arquivos originais são comparados antes e depois dos testes.

O segundo comando é opcional e acessa a rede real. Grava `.runtime/gaez-live-check.json`, identificando expressamente que são consultas externas reais. Esse relatório não é uma recomendação agronômica.

Com o serviço já iniciado, `python -B tools/verify_running.py` valida o acesso HTTP em `127.0.0.1:8001`, incluindo pixels GAEZ reais de milho (`MZE`) e soja (`SOY`). Pode receber outra URL local como argumento. O relatório fica em `.runtime/http-check.json`. Consulte [VALIDACAO.md](VALIDACAO.md) para os resultados desta entrega.
