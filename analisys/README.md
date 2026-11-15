# Análises do Agrion

Espaço independente para desenvolver e validar as análises do Agrion, na branch `analisys`.

**Leia e siga [AGENTS.md](AGENTS.md) antes de trabalhar. Todas as alterações deste trabalho devem ficar em `analisys/`.** A aplicação principal pode ser consultada, mas não modificada.

## Estrutura

Os diretórios serão criados conforme houver conteúdo:

| Caminho | Finalidade |
| --- | --- |
| `docs/` | Métodos, fontes, decisões e propostas de integração |
| `src/` | Implementação modular das análises |
| `tests/` | Testes das funcionalidades |
| `data/` | Entradas autorizadas e documentação de origem |
| `outputs/` | Resultados e relatórios |

## Execução e consumo

A API está implementada em FastAPI, com SQLite das fontes locais, FAOSTAT de preços indexado, GAEZ v5 externa, NASA POWER e previsões Meteomatics/Open-Meteo. Leia o [contrato completo e os exemplos de consumo](docs/API.md).

O build usa `data/faostat.sqlite3.gz` e seu manifesto, distribuídos pelo Git (25,95 MiB compactados). Não é necessário transferir o CSV para a VM: ao iniciar, o serviço valida e instala o banco no volume existente. A planilha de países e as demais bases também estão versionadas. Configure `analisys/.env` na VM e reconstrua somente o Compose de análises após o pull. O CSV original permanece preservado localmente para futuras atualizações; procedimento em [DELIVERY_FAOSTAT.md](docs/DELIVERY_FAOSTAT.md).

Na raiz do repositório:

```sh
docker compose -f analisys/compose.yaml up -d --build
```

Acesse `http://127.0.0.1:8001/docs` para testar os endpoints, `/health` para verificar o serviço e `/api/v1/datasets` para descobrir as fontes. A porta é configurável por `ANALISYS_PORT`; 8000 continua reservada à aplicação principal.

| Endpoint | Dados |
| --- | --- |
| `/api/v1/ecocrop/requisitos` | Requisitos ambientais de 2.568 espécies |
| `/api/v1/fao56/indice_atomico` | 3.097 parâmetros, com tabelas e auditorias complementares |
| `/api/v1/conhecimento/evidencias` | 249 evidências com origem, condições e status de validação |
| `/api/v1/conhecimento/rotacoes` | 75 sequências documentadas |
| `/api/v1/aquacrop/dicionario` | Contrato de entrada; abas de dados ainda vazias |
| `/api/v1/gaez/layers` | Descoberta de camadas na API externa FAO |
| `/api/v1/gaez/point` | Pixel do GeoTIFF remoto por coordenada e camada selecionada |
| `POST /v1/data/nasa-power/daily` | Clima diário histórico NASA POWER, com seleção de variáveis, UTC/LST e lacunas explícitas |
| `POST /v1/data/meteomatics/forecast` | Previsão de temperatura, chuva, umidade, vento e radiação; exige credenciais do serviço e permissão do plano |
| `POST /v1/data/weather/forecast` | Previsão automática: prefere Meteomatics, usa Open-Meteo na indisponibilidade, sem misturar valores; permite selecionar o provedor |
| `GET /v1/data/faostat/metadata`, `/countries`, `/items`, `/prices` | Preços e índices FAOSTAT por país/produto/período; unidades, flags e cobertura preservadas |
| `POST /v1/simulations/aquacrop` | Executa AquaCrop-OSPy 3.0.12: Maize de sequeiro, produtividade simulada e balanço diário; clima NASA/FAO-56 ou série própria |
| `POST /v1/analysis/climate` | I01 GDD, I02 chuva, I03 sequência seca e I05 triagem de exposição térmica; séries próprias ou NASA |
| `POST /v1/analysis/water` | I07 ETc padrão e I08 variação hídrica; ETo/Kc e fluxos explícitos |
| `POST /v1/analysis/economics` | I14 margem com preço próprio ou observação histórica FAOSTAT USD/t explicitamente selecionada; custos obrigatórios; I13 pendente |
| `POST /v1/analysis/agronomy` | I09 aptidão, I10 sucessão e I11 risco ainda pendentes (501) |
| `/v1/capabilities` | Descoberta de NASA/Meteomatics INT, dos quatro grupos IND e ligação ao catálogo das outras fontes |

Cada fonte local tem `/tables` para descobrir todas as tabelas e colunas; consultas aceitam `limit`, `offset`, `q` e `filtros` (objeto JSON de igualdade exata). Os originais são preservados e sua SHA-256 acompanha as respostas. Configuração, dependências, testes e Docker ficam exclusivamente nesta pasta.

NASA POWER foi adicionado após auditoria do projeto anterior `agrion-intelligence`, sem alterar seus arquivos ou fórmulas. Consulte a [entrega S01](docs/DELIVERY_S01.md) para a auditoria, o contrato de dados, exemplos e a prova de consumo pelos indicadores existentes. São suportadas temperaturas média/mínima/máxima, chuva corrigida, umidade e radiação. O histórico foi validado em duas coordenadas e há consulta real recente com disponibilidade parcial explícita.

A [entrega de integração automática](docs/DELIVERY_AUTOMATIC_INDICATORS.md) conclui o uso dessas séries nos indicadores existentes dentro deste mesmo container. O núcleo anterior está empacotado e identificado por hashes em `src/vendor/intelligence/`; nenhuma fórmula foi duplicada na ponte. Não é necessário executar o projeto da Área de Trabalho.

A [entrega dos indicadores](docs/DELIVERY_INDICATORS.md) acrescenta I03, triagem limitada I05, I07, I08 e I14, com métodos, parâmetros obrigatórios e exemplos. NASA alimenta sequências secas, temperaturas e chuva do balanço; ECOCROP oferece envelope geral da espécie e FAO fornece Kc escalar selecionado explicitamente. A [entrega meteorológica](docs/DELIVERY_WEATHER.md) valida a ponte forecast com dados reais. Exposição térmica não estima dano, e balanço não estima estoque de água no solo.

Meteomatics usa autenticação Basic HTTPS exclusivamente no servidor. As credenciais fornecidas foram validadas e configuradas no ambiente do container local, sem arquivos ou segredos versionados. Oito parâmetros horários e produtos diários passaram em consultas reais. Ao recriar o serviço, forneça `METEOMATICS_USERNAME` e `METEOMATICS_PASSWORD` pelo ambiente/gestor de segredos.

Use `/v1/data/weather/forecast` para seleção automática e procedência explícita; I03/I05 e chuva forecast do I08 compartilham esse seletor. Open-Meteo foi validada em consultas reais e como alternativa mediante falha controlada. Sua API pública é não comercial, exige atribuição e tem cotas. Extremos térmicos são produtos diários UTC; não se presume equivalência aos extremos Meteomatics. A disponibilidade de ambas pode falhar. Consulte [DELIVERY_WEATHER.md](docs/DELIVERY_WEATHER.md) para métodos, diferenças, exemplos e avaliação GEOS-FP. O GEOS-FP teve acesso real por célula comprovado, mas ainda não integra o fallback operacional.

O motor de simulação agora executa uma safra real de **AquaCrop-OSPy 3.0.12**, com NASA POWER e ETo FAO-56 calculada ou clima diário fornecido. O cenário Maize genérico foi concluído, com produtividade simulada e balanço hídrico fechado. Solo, profundidade, água inicial, CO₂ e manejo exigem hipóteses/referências explícitas. A distribuição oficial FAO 7.3 apresentou erros internos e continua pendente; não é confundida com o motor executado. Veja [DELIVERY_AQUACROP.md](docs/DELIVERY_AQUACROP.md) para o JSON de consumo, resultados, fontes e limitações. As abas originais da planilha continuam vazias e preservadas.

FAOSTAT disponibiliza 1.319.583 registros, 182 países/áreas e 235 produtos em índice SQLite tipado próprio, no mesmo volume. O CSV não é varrido por consulta. Preços LCU/SLC/USD e índices são distintos; não há custo de produção, câmbio ou previsão de preço inferidos. O I14 reutiliza seu cálculo e aceita uma observação USD/t exata como hipótese histórica explícita, mantendo custo/rendimento fornecidos. Consulte [DELIVERY_FAOSTAT.md](docs/DELIVERY_FAOSTAT.md) para filtros, exemplos e cobertura, inclusive ambiguidades de códigos ISO históricos.

Testes a partir de `analisys/`, com as dependências instaladas:

```sh
python -B -m unittest discover -s tests -v
```

## Colaboração

A disponibilização é feita por **uma única API FastAPI**, com endpoints diferentes por tipo de dado e container Docker próprio. O serviço publica somente no loopback, na porta 8001 por padrão. Para acesso entre containers, o desenvolvedor principal deve conectar seu serviço à rede `agrion-analisys-data` e consumir `http://agrion-data:8000`.

As planilhas e os CSVs normalizados do ZIP alimentam um índice SQLite na inicialização, sem leitura de Excel por requisição. O GAEZ é consultado na fonte externa e não é importado para o índice. Mudanças futuras de armazenamento devem preservar o contrato HTTP da API.

O fluxo de desenvolvimento, revisão e integração está em [docs/COLABORACAO.md](docs/COLABORACAO.md). Entregue cada análise pela API, com contrato documentado e testes; o desenvolvedor principal conecta a aplicação aos endpoints após a revisão.

Antes de editar, confirme `git branch --show-current` e `git status --short`. A branch esperada é `analisys`.

Para trabalho simultâneo com o desenvolvedor principal, use um checkout ou worktree próprio: alternar branches em uma pasta compartilhada afeta todos que usam essa pasta. Inicie futuras sessões neste diretório para carregar as instruções locais.

## Estado e pendências

- API de consulta, índices locais, container isolado e 101 testes aprovados, incluindo distribuição do banco FAOSTAT sem CSV, fontes agronômicas, economia, NASA, indicadores, meteorologia e AquaCrop-OSPy.
- Container saudável em `127.0.0.1:8001`; consultas HTTP locais e GAEZ real para milho e soja validadas. Veja [o registro de validação](docs/VALIDACAO.md).
- Unidades/classes GAEZ exigem interpretação específica quando ausentes do GeoTIFF.
- NASA POWER preservada. Meteomatics autenticada e Open-Meteo validadas por HTTP no Brasil/EUA; fallback sem mistura de provedores, também nos indicadores forecast.
- ETo NASA/FAO-56 e simulação AquaCrop-OSPy funcionais para Maize de biblioteca. HWSD/solo validado, FAO oficial 7.3, calibração local e recomendações continuam pendentes.
- I01/I02 automáticos concluídos na API única, reutilizando o núcleo anterior. Consultas reais no Brasil, EUA e período recente passaram, com resultados equivalentes nas rotas agrupada e legadas. O projeto anterior permanece intacto.
- I03/I05 com NASA real e I07/I08/I14 com entradas controladas validados por HTTP. I07/I08 exigem ETo fornecida; I05 permanece triagem geral, sem modelo de dano por estádio.
- I03/I05 validados também com forecast real; I08 com chuva prevista real e demais entradas controladas. GEOS-FP: transporte pontual viável, normalização e validação de ciclos/variáveis ainda pendentes.
- I09, I10, I11 e I13, a conexão do Flask e as integrações dependentes de fontes/métodos ausentes continuam explicitamente pendentes, sem resultados fictícios.
- Revisão agronômica da biblioteca e da relação mandioca → milho continua pendente.
- FAOSTAT e seleção de preço histórico no I14 validados com dados reais. Custos de produção, câmbio/inflação e previsão de preço permanecem pendentes.
- Nenhuma alteração na aplicação principal ou publicação remota foi realizada. O consumo pelo Flask cabe ao desenvolvedor principal.
- As instruções orientam os agentes; não existe bloqueio técnico de escrita fora desta pasta.
