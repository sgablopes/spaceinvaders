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

A API está implementada em FastAPI, com índice SQLite das fontes locais, consulta GAEZ v5 externa, NASA POWER → GDD/chuva automática e conector Meteomatics de previsão autenticada. Leia o [contrato completo e os exemplos de consumo](docs/API.md).

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
| `POST /v1/analysis/climate` | GDD e chuva, com série manual ou NASA automática; seleção por I01/I02 |
| `POST /v1/analysis/water`, `/agronomy`, `/economics` | Contratos previstos; métodos ainda pendentes (501) |
| `/v1/capabilities` | Descoberta de NASA/Meteomatics INT, dos quatro grupos IND e ligação ao catálogo das outras fontes |

Cada fonte local tem `/tables` para descobrir todas as tabelas e colunas; consultas aceitam `limit`, `offset`, `q` e `filtros` (objeto JSON de igualdade exata). Os originais são preservados e sua SHA-256 acompanha as respostas. Configuração, dependências, testes e Docker ficam exclusivamente nesta pasta.

NASA POWER foi adicionado após auditoria do projeto anterior `agrion-intelligence`, sem alterar seus arquivos ou fórmulas. Consulte a [entrega S01](docs/DELIVERY_S01.md) para a auditoria, o contrato de dados, exemplos e a prova de consumo pelos indicadores existentes. São suportadas temperaturas média/mínima/máxima, chuva corrigida, umidade e radiação. O histórico foi validado em duas coordenadas e há consulta real recente com disponibilidade parcial explícita.

A [entrega de integração automática](docs/DELIVERY_AUTOMATIC_INDICATORS.md) conclui o uso dessas séries nos indicadores existentes dentro deste mesmo container. O núcleo anterior está empacotado e identificado por hashes em `src/vendor/intelligence/`; nenhuma fórmula foi duplicada na ponte. Não é necessário executar o projeto da Área de Trabalho.

Meteomatics foi acrescentado no mesmo serviço, com autenticação Basic HTTPS exclusivamente no servidor. Configure `METEOMATICS_USERNAME` e `METEOMATICS_PASSWORD` no ambiente do serviço e recrie o container. Não há credenciais disponíveis no ambiente desta entrega: o endpoint responde 503 explícito, e a chamada real sem autenticação ao provedor confirmou 401. **Previsões reais autenticadas ainda não foram validadas.** Consulte [a entrega Meteomatics](docs/DELIVERY_METEOMATICS.md) para acesso, parâmetros e exemplos sem segredos.

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

- API de consulta, índice local, container isolado e 45 testes aprovados, incluindo fontes locais, NASA, indicadores e conector Meteomatics.
- Container saudável em `127.0.0.1:8001`; consultas HTTP locais e GAEZ real para milho e soja validadas. Veja [o registro de validação](docs/VALIDACAO.md).
- Unidades/classes GAEZ exigem interpretação específica quando ausentes do GeoTIFF.
- Série diária NASA POWER disponível por consulta sob demanda. Conector de forecast Meteomatics implementado, com validação real autenticada pendente de credenciais/permissões.
- Cálculo de ETo, HWSD raster/MDB, simulação AquaCrop e recomendações permanecem pendentes.
- I01/I02 automáticos concluídos na API única, reutilizando o núcleo anterior. Consultas reais no Brasil, EUA e período recente passaram, com resultados equivalentes nas rotas agrupada e legadas. O projeto anterior permanece intacto.
- Os nove indicadores que não estavam implementados, a conexão do Flask e as integrações dependentes de fontes/métodos ausentes continuam explicitamente pendentes, sem resultados fictícios.
- Revisão agronômica da biblioteca e da relação mandioca → milho continua pendente.
- Nenhuma alteração na aplicação principal ou publicação remota foi realizada. O consumo pelo Flask cabe ao desenvolvedor principal.
- As instruções orientam os agentes; não existe bloqueio técnico de escrita fora desta pasta.
