# Validação da entrega — 15/11/2026

## Escopo

Implementação executada na branch `analisys`, com alterações restritas a essa pasta. Os quatro arquivos de origem foram usados em leitura; os testes compararam suas SHA-256 antes e depois da carga e das consultas. O manifesto da biblioteca foi verificado antes da importação. Nenhum arquivo da aplicação principal foi alterado. Commit e push desta entrega foram solicitados pelo usuário; consulte o histórico Git para seus identificadores. Não houve merge ou deploy remoto.

## Testes automatizados

Comando, executado a partir de `analisys/`:

```sh
.venv/Scripts/python.exe -B -m unittest discover -s tests -v
```

Resultado final: **12 testes aprovados**, em 8,238 segundos no ambiente local. A suíte cobre contagens, valores de referência, ausência versus zero, filtros/paginação, entradas inválidas e injeção, chaves relacionais, quarentena, preservação dos originais e reaproveitamento do índice. Também cobre contrato OpenAPI, falhas externas e consulta de raster sintético com escala, NoData e limites espaciais. Os casos externos da suíte usam mocks identificados; a verificação real é separada.

Versões diretas exercitadas: Python 3.12, FastAPI 0.163.1, Uvicorn 0.54.0, HTTPX 0.28.1, openpyxl 3.1.5 e Rasterio 1.5.2. A Starlette emite aviso de depreciação do transporte HTTPX no cliente de testes; os testes continuam aprovados. Não afeta o cliente HTTPX usado na integração GAEZ.

## Container e HTTP

Build e inicialização concluídos com:

```sh
docker compose -f analisys/compose.yaml up -d --build --wait --wait-timeout 60
```

O healthcheck reportou **healthy**. O serviço ficou disponível apenas em `127.0.0.1:8001`, com a porta interna 8000 do container. A imagem inclui `libexpat1`, necessária ao Rasterio no Linux, e certificados TLS. O container executa com usuário não privilegiado e volume próprio para o SQLite.

`tools/verify_running.py` confirmou respostas HTTP 200 e conteúdos esperados:

| Consulta | Conferência |
| --- | --- |
| `/health` | `status=ok` |
| `/api/v1/ecocrop/culturas` | 2.568 registros |
| `/api/v1/ecocrop/requisitos`, filtro `crop_id=ECO_289` | 1 registro |
| `/api/v1/fao56/indice_atomico` | 3.097 registros |
| `/api/v1/conhecimento/evidencias` | 249 registros |
| `/api/v1/aquacrop/clima_diario` | 0 registros, coerente com a planilha vazia |
| `/openapi.json` | Rota GAEZ pontual presente |

As seis consultas locais levaram entre 6,72 e 26,91 ms nesta execução, incluindo HTTP ao container. São observações de um smoke test, sem garantia de desempenho ou teste de carga.

## GAEZ externo real

Consultas feitas pelo endpoint HTTP da API, dentro do container Linux, para latitude -16,5 e longitude -49,3:

| Produto e cenário | Cultura | Resultado do transporte/leitura |
| --- | --- | --- |
| `RES05-SIX.HP0120.AGERA5.HIST.MZE.HRLM` | Milho | HTTP 200, `status=ok`, bruto 3 |
| `RES05-SIX.HP0120.AGERA5.HIST.SOY.HRLM` | Soja | HTTP 200, `status=ok`, bruto 3 |

As duas camadas declararam CRS EPSG:4326, resolução de 0,083333° por célula, escala 1 e offset 0. Não declararam unidade na banda, portanto `unit=null`. Os valores não foram convertidos em percentual, produtividade ou recomendação. Datas de acesso e metadados dos objetos estão no relatório local `.runtime/http-check.json`.

A consulta de catálogo também foi validada diretamente contra a API pública Google Cloud Storage do bucket FAO. Os códigos publicados incluem `MZE` para o exemplo de milho e `SOY` para soja; os identificadores devem ser descobertos no catálogo, sem presumir equivalência com códigos ECOCROP.

## Limitações e próximos passos

- Validar unidades, classes e fatores específicos dos produtos GAEZ antes de interpretação agronômica; o endpoint expõe pixel e metadados, sem interpretação automática.
- HWSD raster/MDB, Parquet ECOCROP e contrato climático citado não estão presentes no disco. As planilhas e os CSVs existentes foram priorizados.
- Não há cálculo de ETo, execução AquaCrop, ingestão NASA POWER, banco financeiro ou recomendação automática nesta entrega.
- A biblioteca científica requer revisão agronômica; a relação mandioca → milho continua marcada como pendência e a quarentena não entra nas tabelas ativas.
- O SQLite é um índice derivado com buscas por tabela; volumes maiores e concorrência precisam de medição antes de ampliar a arquitetura. O índice local observado ocupa aproximadamente 25,7 MB.
- Consumo pelo Flask, rede compartilhada com a aplicação principal e eventual publicação devem ser implementados pelo desenvolvedor principal, conforme [API.md](API.md).
