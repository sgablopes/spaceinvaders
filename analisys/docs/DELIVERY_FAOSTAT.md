# FAOSTAT PP — preços e cenários econômicos, API 1.6.0

Entrega na branch `analisys`, exclusivamente nessa pasta. Mantidos a FastAPI/container existentes, os quatro grupos de indicadores, NASA POWER, previsões e AquaCrop. Não houve mudança na aplicação principal nem nos arquivos de entrada.

## Arquivos e cobertura verificados

| Fonte recebida | Estrutura verificada |
| --- | --- |
| `Prices_E_All_Data_(Normalized).csv` | UTF-8, 15 colunas, 214.286.652 bytes, **1.319.583 observações**, 182 países/áreas e 235 produtos |
| `Agrion_Codigos_Paises_FAOSTAT.xlsx` | Aba `Países`, 182 registros, códigos FAOSTAT/M49, nomes inglês/português, gid MapTiler e códigos ISO fornecidos |

SHA-256 do CSV: `976728a369cfe38c143681f826d73cec5612c7cdc11da35aef3a703501cdb37f`. SHA-256 da planilha: `69f5b4e729cf0a88f3bb28f385764279878e42558f68ab23dd7f26754b831fbc`. As respostas expõem ambos, data da indexação e número da observação original para rastreabilidade. Essa data é da carga local, não publicação/extração FAO, que não consta no arquivo recebido.

| Elemento FAOSTAT | Registros | Unidade original `Unit` | Interpretação |
| --- | ---: | --- | --- |
| 5530 | 547.350 | LCU | Preço por tonelada em moeda local, sem código monetário ISO identificado |
| 5531 | 171.178 | SLC | Preço por tonelada em moeda local padronizada; não presumir equivalência à LCU |
| 5532 | 167.589 | USD | Preço recebido pelo produtor em USD/tonelada |
| 5539 | 433.466 | vazia | Índice de preços, base 2014–2016=100; não é preço monetário |

Os significados são os do [domínio oficial FAOSTAT PP](https://www.fao.org/faostat/en/#data/PP) e da [metodologia FAO](https://files-faostat.fao.org/production/PP/PP_e.pdf). Os dados se referem a preços recebidos pelo produtor em nível nacional, com as particularidades de compilação da fonte. **Não são custos de produção, preço de varejo, oferta de compra ou cotação atual do talhão.** [Catálogo oficial FAO](https://data.fao.org/catalog/dataset/47c17894-8ca1-4bd0-ba4d-6078e919e9b1)

A cobertura global é 1991–2025, com **943.447 valores anuais** (`Months Code=7021`) e **376.136 valores mensais**, estes somente no elemento 5530 neste snapshot, desde 2010. Janeiro chega a 2025; os demais meses chegam globalmente a 2024. USD/SLC vão de 1991 a 2024. Isso **não garante cada combinação de país/produto/ano/mês**. Por exemplo, a consulta de milho Brasil, dezembro de 2024, LCU mensal não encontrou observação; não foi preenchida com o preço anual. Consulte `/metadata` e o resultado exato.

Não foram encontrados valores ausentes ou chaves de observação duplicadas neste arquivo. Flags preservadas literalmente: A=881.156, E=433.451, X=4.649, I=147 e B=180 registros. Não se traduzem esses códigos nem se eleva sua qualidade sem uma legenda de referência; não se elimina estimativa, imputação ou quebra de série silenciosamente. O carregador também suporta futuros valores vazios como null, distinguindo-os de zero.

## Armazenamento e desempenho

Foi reutilizado **SQLite**, sem servidor/banco adicional ou nova dependência. FAOSTAT usa o índice especializado `.runtime/faostat.sqlite3`, no mesmo volume já utilizado pelo serviço, separado do índice genérico das quatro bases pequenas. O modelo genérico com JSON e filtros `json_extract` não foi aplicado a 1,3 milhão de linhas.

O CSV é percorrido em fluxo, com lotes de 10.000 observações. Dimensões de país, produto/CPC, elemento e período ficam normalizadas; observações têm colunas tipadas e índice B-tree `(area_code, item_code, year, months_code, element_code, source_row)`. Consultas exigem país e produto, usam parâmetros SQL e paginação limitada. Texto só é pesquisado nos catálogos pequenos, sem varrer descrições repetidas no CSV. Não se lê CSV/Excel, calcula hash ou importa dados em cada request.

A carga valida cabeçalhos, códigos, anos, números finitos e consistência de rótulos por código. O valor textual original permanece junto ao valor numérico, evitando perder a representação/precisão da fonte. A coluna `raw` da resposta reconstitui os 15 campos originais; os apóstrofos de proteção de códigos e os zeros iniciais de M49/CPC permanecem nela. Fora de `raw`, remove-se somente o apóstrofo inicial dos campos de código, mantendo o tipo texto.

Na inicialização com os dois arquivos originais presentes, compara-se a impressão digital SHA-256/versão com o índice. Sem alteração, reutiliza-o; quando muda, constrói outro arquivo temporário e só substitui o índice após sucesso e nova verificação dos hashes. Sem os originais, instala o snapshot compactado descrito abaixo. Uma falha não publica carga parcial nem destrói o índice anterior. O serviço utiliza um worker, como já configurado. Sem originais nem snapshot, as outras fontes continuam disponíveis e as consultas FAOSTAT retornam 503 explícito.

Medição local desta entrega: carga completa aproximadamente **33,3 s**, índice **119.517.184 bytes** (cerca de 114 MiB). Em 50 consultas locais Brasil/milho/USD, 2020–2024: mediana **1,20 ms**, p95 **1,61 ms**. Em 30 consultas HTTP no container: mediana **7,63 ms**. São medições do ambiente desta sessão, sem promessa de SLA ou concorrência alta. Evidências em `.runtime/faostat-performance.json` e `.runtime/faostat-http-check.json`.

### Distribuição e atualização

O CSV de cerca de 204 MiB permanece original, fora do Git, como fonte de atualização local. A distribuição para a VM usa **`analisys/data/faostat.sqlite3.gz` (27.210.136 bytes; 25,95 MiB)** e **`faostat.manifest.json`**, preparados somente a partir do índice FAOSTAT validado. Esses dois arquivos são destinados ao versionamento Git, com a planilha de países já versionada. Não contêm credenciais nem dados da aplicação principal. Não exigem Git LFS ou transferência manual de CSV. O Dockerfile inclui o snapshot e a planilha, sem copiar o CSV.

Na ausência dos dois originais, o serviço lê o manifesto, confere versão do esquema, hashes SHA-256 do pacote e banco, tamanho descompactado limitado, `PRAGMA quick_check`, procedência das fontes registrada no banco e hash da planilha quando presente. A instalação no volume `.runtime` é atômica. Um banco válido é reutilizado; uma nova edição versionada substitui somente o índice FAOSTAT após validação, sem remover o volume. Corrupção/incompatibilidade aborta a inicialização com erro explícito, preservando o banco anterior; não continua silenciosamente com outra edição. Os hashes do manifesto verificam integridade, não substituem confiança e revisão do repositório.

**Deploy na VM:** depois que esta entrega estiver commitada e enviada, obtenha a branch/versão que a contém em um checkout próprio de análises. Não troque a branch de um checkout em uso pelo desenvolvedor principal. `git pull` traz o pacote, mas não reconstrói o container. A partir da raiz desse checkout:

```sh
git pull --ff-only
docker compose --env-file analisys/.env -f analisys/compose.yaml up -d --build --wait --wait-timeout 120
curl -f http://127.0.0.1:8001/v1/data/faostat/metadata
```

O `.env` continua configurado separadamente na VM; não há variáveis novas. Excel/ZIP das outras bases já acompanham o Git, e `catalog.sqlite3` é reconstruído automaticamente. Nenhuma alteração no Compose principal ou no banco da aplicação é necessária.

**Atualização da base pelo desenvolvedor de análises:** forneça CSV e planilha originais autorizados em `analisys/`, guarde as versões anteriores no fluxo da equipe e execute, a partir de `analisys/`:

```sh
python -B tools/package_faostat.py
```

O comando valida/reutiliza a carga original e usa backup consistente SQLite antes de gerar o pacote e seu manifesto. Revise/teste os dois arquivos juntos e versione-os mediante autorização, incluindo a planilha se mudou. Então siga o deploy acima. Não há recarga durante requisições. Não remova o volume para atualizar. O CSV original não é modificado ou substituído. A compactação versionada é do banco derivado, sem perder campos brutos, precisão textual ou procedência.

## Países e produtos

As 182 correspondências FAOSTAT/M49 da planilha conferem com as 182 áreas do CSV. Os nomes traduzidos e gids vêm **da planilha fornecida**, não de uma nova consulta MapTiler. Gid ausente continua ausente.

Há ISO2 compartilhado por territórios históricos: **ET**, **SD** e **CS**. Exemplos: Etiópia/Antiga Etiópia e Sudão/Antigo Sudão. A API preserva ambas as linhas e recusa uma seleção ISO ambígua. Selecione `area_code` explicitamente nesses casos; não substitui um território antigo pelo atual. As formas ISO históricas com um terceiro código da planilha são preservadas em `raw`.

O produto deve ser identificado pelo **Item Code FAOSTAT**, por exemplo `56` para `Maize (corn)`. O CPC `0112` é um campo distinto. Não se inventou correspondência automática entre código FAOSTAT, ECOCROP, biblioteca ou nomes internos do AGRION. O catálogo de produtos conserva os nomes ingleses da fonte; `q=Maize` funciona, sem presumir tradução de `q=milho`.

## Endpoints de consulta

Base local `http://127.0.0.1:8001`; na rede Docker existente, `http://agrion-data:8000`. Tudo pertence à mesma API. O `/docs` apresenta os schemas, e `/v1/capabilities` inclui `get_faostat_producer_prices`. A fonte também aparece em `/api/v1/datasets`.

| GET | Finalidade |
| --- | --- |
| `/v1/data/faostat/metadata` | Contagens, anos por elemento/período, unidades, flags, ambiguidades ISO e hashes |
| `/v1/data/faostat/countries?q=Brasil` | Correspondências FAOSTAT, M49, ISO e gid; dados brutos e presença de preços |
| `/v1/data/faostat/items?country_iso2=BR&q=Maize` | Produtos disponíveis no país e respectivos códigos; filtro de país opcional |
| `/v1/data/faostat/prices` | Séries de observações por país/produto/período |

Exemplos reais:

```sh
curl "http://127.0.0.1:8001/v1/data/faostat/prices?country_iso2=BR&item_code=56&start_year=2020&end_year=2024&element_code=5532"
curl "http://127.0.0.1:8001/v1/data/faostat/prices?area_code=101&item_code=56&start_year=2024&end_year=2024&frequency=monthly&month=1&element_code=5530"
```

Informe `country_iso2` **ou** `area_code`, exclusivamente. `item_code` é obrigatório. `start_year`/`end_year` são inclusivos (padrões 1991/2100 consultam somente o que existe); `frequency` aceita `annual` (padrão), `monthly` e `all`. `month` de 1 a 12 só se aplica a `monthly`. `element_code` pode selecionar qualquer código disponível; omitido, os elementos são retornados separadamente, sem agregação. `limit`=1–500 (padrão 100), `offset`=0–100.000; ordenação estável por ano, mês/código, elemento e observação original.

A resposta contém `total`, `limit`, `offset`, `items` e `source`. Cada observação traz país/produto/códigos, `year`, `months_code`, `months`, `element_code`, `element`, **`value_kind`**, `unit` original, `value`, `value_text`, `flag`, `source_row` e `raw`. `currency_iso3` só identifica USD quando o elemento/unidade/rótulo confirmam USD por tonelada; não inventa BRL, IDR ou moedas históricas a partir de LCU/SLC. Uma unidade vazia do índice permanece `""`, sem ser transformada em USD.

Não há média anual calculada a partir dos meses, interpolação, agregação de índices/preços, deflacionamento ou conversão cambial. Ausência de observações retorna HTTP 200 com `total=0`/`items=[]`; um valor observado zero retorna uma observação com `value=0`. A cobertura global não autoriza preencher lacunas locais.

## Integração com I14 existente

`POST /v1/analysis/economics` mantém os quatro grupos e reutiliza integralmente a aritmética do I14. O modo anterior com `price_per_t` continua funcional. Alternativa aditiva: omitir esse campo e enviar `faostat_price`, selecionando **uma observação exata USD/tonelada**, com país, produto, ano e referência explícita do uso histórico no cenário. A seleção mensal exige `frequency=monthly` e `month`, mas **não há USD mensal neste snapshot**; ausência retorna 404, sem recorrer ao preço anual.

Exemplo: **preço FAOSTAT real**, com área, rendimento e custo controlados somente para testar o contrato:

```json
{
  "include": ["I14"],
  "inputs": {
    "crop_margin": {
      "crop_id": "maize",
      "start_date": "2026-01-01", "end_date": "2026-12-31",
      "area_ha": 2, "expected_yield_t_per_ha": 3,
      "cost_per_ha": 200, "currency": "USD",
      "assumptions_reference": "Rendimento e custo CONTROLADOS; preço histórico não representa previsão",
      "faostat_price": {
        "country_iso2": "BR", "item_code": "56", "year": 2024,
        "reference": "Observação nacional de 2024 usada explicitamente como hipótese deste cenário"
      }
    }
  }
}
```

O exemplo usa **142,20 USD/t** (Brasil/milho/2024), calcula receita **853,20 USD**, custos declarados **400 USD** e margem **453,20 USD**. Os custos de 200 USD/ha e o rendimento de 3 t/ha são hipóteses controladas, não dados FAOSTAT. O ano do preço pode diferir do ano do cenário somente como hipótese explícita, sem declarar previsão ou reajuste automático.

`faostat_price` aceita `area_code` em lugar do ISO, e somente elemento `5532`. Moeda do cenário/custos deve ser `USD`; LCU, SLC e índices não são convertidos. Não envie `price_per_t` e `faostat_price` juntos. `cost_per_ha` continua obrigatório: **o preço nunca é usado como custo de produção**. Não há inferência de rendimento ou associação automática entre `crop_id` e produto FAOSTAT. A escolha de produto compatível é explícita do consumidor.

A resposta I14 acrescenta `price_per_t_used`, `faostat_price_record` e `price_data_sha256`, além da procedência FAOSTAT, flag, referência do cenário e hashes de ambas as fontes. O cálculo manual anterior não muda; nenhum caminho alternativo de cálculo financeiro foi criado. A rota legada `/v1/indicators/crop-margin` também aceita a extensão. Não se escolhe o último ano disponível, outro país ou produto quando a seleção exata falta; duplicidade impede seleção automática.

## Validação e limitações

Registros reais conferidos por HTTP no container:

| Consulta | Valor original | Interpretação |
| --- | ---: | --- |
| Brasil, milho, anual 2024, 5532 | 142.200000 | USD/tonelada; observação CSV 150.422 |
| EUA, milho, anual 2024, 5532 | 171.300000 | USD/tonelada |
| Brasil, milho, anual 2024, 5539 | 149.490000 | Índice, unidade original vazia, flag E; não é preço monetário |
| Indonésia, milho, janeiro 2024, 5530 | 6221737.300000 | LCU/tonelada; sem deduzir código monetário ISO |

Foi comparada a observação brasileira completa com o CSV por leitura independente, inclusive os 15 campos brutos. Hashes dos dois arquivos permaneceram iguais. O fluxo I14 com o preço real passou; a ausência em 2030 retornou lista vazia, sem inventar dado.

Erros: 422 filtros incompatíveis, ISO ambíguo ou moeda/elemento financeiro incompatível; 404 país não identificado/seleção financeira ausente; 503 fontes ausentes, ambiguidade de observação ou índice indisponível. As rotas de consulta usam `error` para falhas do serviço e validação padrão FastAPI para erros estruturais de query; a análise mantém seu contrato de erro anterior. A leitura do preço não autoriza margem bruta ou lucro líquido quando os custos declarados não justificam essas definições.

Reprodução a partir de `analisys/`, com ambos os originais disponíveis:

```sh
python -B -m unittest discover -s tests -q
python -B tools/verify_faostat.py
```

**101 testes aprovados**: os 82 anteriores, 13 de FAOSTAT e seis de distribuição do snapshot, incluindo fixtures explicitamente sintéticas, códigos/zeros iniciais, unidades, flags, zero/null/ausência, períodos, ambiguidades históricas, paginação, plano de consulta indexado, reuso/atualização atômica, preservação de fontes reais e integração I14/legado. Os novos testes verificam primeira instalação sem CSV, reuso, atualização sobre volume existente, pacote corrompido preservando o banco anterior, tamanho/hash/esquema, divergência da planilha e recuperação de índice danificado. Sem o CSV original, somente a comparação independente da linha original é ignorada.

Foi validado também o banco completo na imagem Docker, com raiz somente leitura e volume temporário vazio: CSV ausente, instalação automática de 1.319.583 registros e consulta Brasil/milho/2024 = 142,20 USD/t. O Compose de análises ficou saudável e o script HTTP confirmou Brasil, EUA, Indonésia, índice distinto de preço e I14 com custo/rendimento controlados. O script HTTP gera `.runtime/faostat-http-check.json`, sem credenciais e fora do Git.

Persistem: custos de produção e câmbio/inflação não integrados; preço atual/futuro não previsto; qualidade e representatividade locais não comprovadas; tradução/mapeamento de produtos não automatizados. A aplicação principal não foi modificada. O desenvolvedor principal deve consumir estes contratos, manter a unidade e o ano do preço visíveis e distinguir referências históricas de hipóteses financeiras.
