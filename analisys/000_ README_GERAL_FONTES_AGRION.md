# AGRION — Inventário geral de fontes e plano de integração

**Projeto:** Agrion — NASA Space Apps Challenge 2026 / *Field Shift: Adapting Farms with NASA Data*  
**Atualização:** 15/11/2026  
**Objetivo deste arquivo:** explicar quais fontes já foram selecionadas/reunidas, a função de cada uma e como se conectam à aplicação. **Selecionar, baixar e integrar são etapas diferentes.**

## 1. Visão geral

O Agrion compara alternativas de cultivo e rotação considerando a **localização e as prioridades do agricultor**, as **exigências das culturas**, as **condições agroecológicas**, o **solo**, o **clima**, **evidências científicas** e **cenários econômicos**. O AquaCrop é o motor de simulação para culturas compatíveis; não é a única fonte de decisão.

```text
Localização + cultura(s) + histórico e preferências do agricultor
                         |
       +-----------------+--------------------+
       |                 |                    |
  ECOCROP + GAEZ    HWSD v2.2             NASA POWER
  requisitos e      atributos do solo     clima diário
  aptidão regional       |                    |
       |            estimativa FC/PWP/       |-- FAO-56 (ETo)
       |            SAT/Ksat                |
       |                 +---------+----------+
       |                           |
       |                    AquaCrop 7.3
       |               produtividade por cenário
       |                           |
       +---------------------------+--------------------+
                                   |                    |
                 Base científica Agrion v0.4       CONAB / FAOSTAT
                 rotação, manejo, pragas           preços e custos
                                   |                    |
                                   +---------+----------+
                                             |
                             Comparador Agrion (MVP)
                       alternativas + riscos + evidências
                        + produtividade + economia
```

O esquema mostra a **arquitetura prevista**, não uma integração concluída. Efeitos de rotação não são calculados automaticamente pelo GAEZ ou pelo AquaCrop: precisam de evidência específica e condições locais.

## 2. Fontes principais da pasta

| Fonte | Papel exclusivo ou principal | Material reunido/selecionado | Estado real |
|---|---|---|---|
| **AquaCrop 7.3** | Simular crescimento, balanço hídrico e produtividade para culturas parametrizadas | Referência do Git/aplicação e `Modelo_Entrada_App Git - AquaCrop.xlsx` | Modelo e planilha reunidos; execução ponta a ponta ainda deve ser validada |
| **ECOCROP** | Verificar requisitos ambientais gerais de espécies; gerar candidatas para análise | `ecocrop.parquet` e `Requisitos por Cultura - ECOCROP - 2568 Espécies.xlsx` | Arquivos reunidos; integração ao motor de decisão pendente |
| **FAO-56** | Método para evapotranspiração de referência (ETo), coeficientes e necessidades hídricas | Manual PDF e planilha de apoio | Documentação reunida; cálculo deve ser implementado/testado; não é API climática |
| **HWSD v2.2 (FAO/IIASA)** | Consultar propriedades físicas e químicas do solo por profundidade e estimar os parâmetros hidráulicos do AquaCrop | `hwsd2.2_db.zip` + `hwsd2.2_raster.zip`; `README_HWSD_v2.2_Agrion.md` | Downloads feitos; consulta raster inicial realizada; conexão com atributos `.mdb` e perfil hidráulico ainda pendentes |
| **Base científica Agrion** | Evidências sobre rotação, sucessão, manejo, pragas, doenças e calendários | Biblioteca consolidada `agrion-knowledge-base-v0.4.0.zip` (na organização atual, item 4) | Base documental para MVP; revisão agronômica pendente; existe uma relação mandioca → milho a revisar |
| **GAEZ v5 (FAO/IIASA)** | Aptidão agrícola, produtividade potencial, calendários e limitações agroecológicas | `README_GAEZ_v5_Agrion.md` e links oficiais | **Fonte selecionada; dados por coordenada/cultura ainda não foram extraídos e integrados** |

### Diferenças importantes

- **GAEZ ≠ HWSD:** o GAEZ disponibiliza avaliações agroecológicas *derivadas*; a HWSD permite consultar atributos de solo necessários à preparação do AquaCrop. Usar os dois **não aumenta por si só a resolução** (~1 km em muitos produtos; varia por camada).
- **ECOCROP ≠ GAEZ:** o ECOCROP registra *exigências gerais da espécie*; o GAEZ avalia *adequação geográfica e cenários de produtividade*. São complementares, não duas previsões equivalentes.
- **FAO-56 ≠ NASA POWER:** FAO-56 é **metodologia**; NASA POWER fornece **observações/estimativas meteorológicas** que podem alimentar os cálculos e a simulação.
- **AquaCrop ≠ base de rotações:** o AquaCrop simula culturas sob clima, solo e manejo; os efeitos específicos da **sequência entre culturas** dependem da biblioteca científica e de validação contextual.
- **Base científica ≠ autorização automática de recomendação:** uma sequência documentada em certa região não é garantia de benefício para outro talhão.

## 3. Fontes externas já mapeadas, mas não necessariamente baixadas

| Fonte | Para quê | Quando integrar | Situação |
|---|---|---|---|
| **NASA POWER** | Série meteorológica diária (temperaturas, precipitação e variáveis auxiliares) | Entrada de clima do AquaCrop; prioridade MVP | Selecionada; testar API, unidades, lacunas e intervalo por coordenada |
| **CONAB** | Preços e custos de produção no Brasil | Módulo financeiro do MVP brasileiro | Pesquisa/integração em frente separada; verificar cobertura, datas, formatos e termos de uso |
| **FAOSTAT** | Preços ao produtor e estatísticas agrícolas internacionais | Complementar CONAB; expansão global | Mapeada; disponibilidade e granularidade variam por país/cultura |
| **CEPEA** | Indicadores e histórico de preços brasileiros | Complemento financeiro | Opcional; conferir licença e acesso automatizado |
| **EPPO / CABI** | Hospedeiros de pragas, sintomas e prevenção | Enriquecimento fitossanitário | Partes já alimentaram a biblioteca v0.4; não interpretar como previsão de infestação |
| **Embrapa Alice / Infoteca-e; FAO AGRIS** | Publicações originais e evidências agrícolas | Atualizar base científica quando surgirem lacunas | Já usadas no trabalho de catalogação; artigos pendentes podem ficar na fila |
| **FAO Crop Calendar / ZARC** | Janelas regionais de plantio, colheita e risco | Só onde GAEZ e dados locais forem insuficientes | Complementares; ZARC é referência normativa brasileira específica |
| **SoilGrids** | Estimativas globais de propriedades do solo a 250 m | Comparar com HWSD se precisar de mais detalhe espacial | **Opcional**, não requisito inicial; 250 m é resolução, não precisão de campo |
| **MapBiomas / NASA HLS** | Uso anterior da terra e histórico de cobertura vegetal | Mapa, talhões e contexto de rotação | Etapa posterior; classificações orbitais não provam a cultura exata em cada safra |
| **NASA GPM, SMAP, SRTM, ECOSTRESS** | Chuva por satélite, umidade superficial, relevo, estresse térmico | Complementos quando houver necessidade específica | Não baixar antecipadamente |
| **PronaSolos / WoSIS / INMET / IBGE** | Refinamento de solos, estações meteorológicas e dados nacionais | Adaptação brasileira e validação | Fontes candidatas, não integrações concluídas |

**Princípio de seleção:** acrescentar uma fonte somente quando ela trouxer uma variável, resolução, cobertura regional ou validação que as já adotadas não oferecem. Não baixar bases globais completas sem necessidade.

## 4. Como cada fonte chega à aplicação

1. **O agricultor informa** localização (ponto ou talhão), histórico das culturas, área, disponibilidade de irrigação, prioridades e, quando houver, medições reais de solo.
2. **ECOCROP + GAEZ** identificam culturas ambientalmente candidatas e aptidão/limitações da região. Gravar produto exato, período, cenário, resolução e unidade.
3. **HWSD** usa a coordenada no raster para identificar uma unidade de mapeamento; o banco `.mdb` fornece componentes e atributos por camada. Um cálculo documentado estima **FC, PWP, SAT e Ksat**. Não tratar esses valores como medidos.
4. **NASA POWER + FAO-56** fornecem/preparam o clima e a evapotranspiração necessários ao simulador, verificando resolução temporal e unidades.
5. **AquaCrop** simula produtividade e balanço hídrico de culturas compatíveis, com parâmetros da cultura, clima, solo e manejo consistentes. Não atribuir efeitos de rotação que o motor não modela explicitamente.
6. **Biblioteca científica v0.4** recupera relações entre culturas, evidências, riscos, limites regionais e referências originais. Relações inconsistentes não entram no ranqueamento.
7. **CONAB/FAOSTAT** acrescentam preços e custos com seus períodos e regiões para calcular **cenários financeiros**, não lucro garantido.
8. **Agrion apresenta alternativas** com justificativas, fontes e incertezas, pedindo dados do produtor quando a evidência for insuficiente.

### Registro mínimo de proveniência por valor

`fonte | conjunto/versao | URL | cultura | localizacao | periodo | resolucao | unidade | metodo/transformacao | data_acesso | status_qualidade | limitacoes`

Para evidências de rotação, preservar ainda `rotacao_id`, `evidencia_id`, `fonte_id`, `estudo_id`, localizador (página/tabela), cultura antecessora/sucessora, condições e validação agronômica. Não contar resultados do mesmo estudo como experimentos independentes.

## 5. Situação e próximas tarefas

- [x] Reunir arquivos do ECOCROP, materiais FAO-56 e referências AquaCrop.
- [x] Construir a biblioteca científica inicial (v0.4) e testar três sequências de rotação em nível documental.
- [x] Baixar HWSD v2.2 (raster + banco de atributos).
- [x] Documentar GAEZ v5 e HWSD v2.2.
- [ ] **HWSD:** ler as tabelas do `.mdb`, testar chave raster ↔ banco, obter perfil de solo real e validar conversão FC/PWP/SAT/Ksat.
- [ ] **GAEZ:** extrair um resultado de aptidão e produtividade para uma coordenada e duas culturas; registrar metadados.
- [ ] **NASA POWER + FAO-56:** preencher uma série climática de teste e conferir ETo e unidades.
- [ ] **AquaCrop:** executar uma simulação ponta a ponta com entradas reais e hipóteses explícitas.
- [ ] **Base científica:** corrigir/revisar a associação mandioca → milho antes de permitir que vire recomendação.
- [ ] **Financeiro:** testar uma série de preços/custos e harmonizar cultura, unidade comercial, região e ano.
- [ ] **Integração final:** cruzar as camadas em três cenários, documentando resultados e lacunas.

**Observação:** dados com resolução de 1 km ou 250 m são estimativas geoespaciais; não substituem amostras de solo, dados do talhão nem acompanhamento agronômico profissional.

## 6. Links de referência

- AquaCrop (FAO): https://www.fao.org/aquacrop/
- ECOCROP (FAO): https://ecocrop.apps.fao.org/
- FAO-56 (publicação): https://www.fao.org/4/X0490E/X0490E00.htm
- GAEZ v5: https://data.apps.fao.org/gaez/?lang=en
- GAEZ v5 (documentação técnica): https://github.com/un-fao/gaezv5
- HWSD v2.2 (catálogo): https://data.apps.fao.org/catalog/iso/ff5c613c-75bb-46a9-a162-bc728059b465
- NASA POWER: https://power.larc.nasa.gov/
- Embrapa Alice: https://www.alice.cnptia.embrapa.br/
- Embrapa Infoteca-e: https://www.infoteca.cnptia.embrapa.br/infoteca/
- FAO AGRIS: https://www.fao.org/agris/
- EPPO: https://gd.eppo.int/
- CABI PlantwisePlus: https://www.cabi.org/plantwiseplus/
- CONAB: https://www.gov.br/conab/pt-br
- FAOSTAT: https://www.fao.org/faostat/
- SoilGrids: https://soilgrids.org/
- MapBiomas: https://brasil.mapbiomas.org/
- NASA HLS: https://hls.gsfc.nasa.gov/

---

**Resumo:** o núcleo planejado é **ECOCROP + GAEZ + HWSD + NASA POWER/FAO-56 + AquaCrop + biblioteca científica + dados financeiros + entradas do agricultor**. Não é necessário integrar todas as fontes opcionais para entregar o MVP. Este documento registra a arquitetura e o andamento; não comprova que as APIs e os motores já estejam funcionando juntos.
