# Motor Agrion — núcleo textual

O núcleo em `app/services/engine.py` é uma interface Python reutilizável. Ele recebe uma tarefa textual, um objeto JSON de contexto, histórico opcional e idioma (`pt-BR`, `en-US` ou `es-US`) e devolve texto, modelo e a lista de ferramentas chamadas. O chamador é responsável por montar o contexto e persistir qualquer histórico.

```python
from app.services.engine import AgrionEngine

result = AgrionEngine().run(
    task='Resuma as informações disponíveis.',
    context={'property_name': 'Sítio Exemplo'},
    history=[],
    language='pt-BR',
)
print(result.text)
```

O motor usa Vertex AI, Application Default Credentials da service account da VM e o SDK Google Gen AI. Configure `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_ENGINE_LOCATION` (padrão `us`) e `GEMINI_ENGINE_MODEL` (padrão `gemini-3.8-flash`). Para `us` e `eu` o endpoint é o multirregional `aiplatform.<região>.rep.googleapis.com`. Cada chamada ao modelo tem timeout de 30 segundos; mensagens e contexto têm limites de tamanho. Não registre contexto ou conversas em logs.

## Contexto da propriedade

No navegador, `AgrionContext.load()` lê o cadastro atual e o perfil agrícola correspondente e produz o objeto JSON enviado ao motor pelo chat. `AgrionContext.build(property, profile)` também aceita os registros diretamente e rejeita perfis de outra propriedade. O contexto contém nome, propriedade, localidade, geometria, ponto central, área, dados agrícolas e estados, origem e confiança. Campos ausentes permanecem `pending`; as transcrições e trechos de evidência não são copiados para o contexto. O cadastro geográfico é a fonte atual de nomes e geometria.

## Chat textual

O botão Assistente Agrion abre a conversa textual. `POST /api/assistant/message` recebe `message`, `context`, `history` e `language` e encaminha ao motor; não há credenciais no navegador. O histórico fica no `localStorage`, separado por identificador de propriedade e limitado a 40 mensagens. O endpoint valida origem, tamanho e formato e aplica limite em memória por processo (`AGRION_ASSISTANT_MESSAGES_PER_HOUR`, padrão 60); não há conta nem sincronização entre dispositivos. Validação real com Vertex AI e a API de análises na VM continua necessária.

## Dashboard inicial

`POST /api/dashboard/bootstrap` recebe o contexto da propriedade e usa o mesmo Core em modo `dashboard`, com instrução e resposta JSON estruturada próprias; o modo padrão `chat` mantém suas instruções. O Core seleciona até três identificadores do perfil informado, sem consultar ferramentas nem gerar valores. O backend valida o schema e filtra identificadores que não correspondam a campos confirmados; a interface exibe os valores diretamente do contexto local. A tela mantém o carregamento durante a chamada e apresenta os dados locais com erro e opção de repetir se o Core estiver indisponível.

Após o bootstrap, `POST /api/dashboard/forecast`, `/rainfall`, `/stage` e `/daily` atualizam as seções independentemente. Forecast solicita as próximas 24 horas com seleção automática Meteomatics/Open-Meteo, indicando que são previsões; chuva consulta I02 NASA com referência em UTC dois dias antes e mostra as janelas disponíveis, não chuva desde o plantio. A fase estimada usa o Core no modo `dashboard_stage` e exige cultura confirmada e URL presente no resultado de uma ferramenta. Graus-dia são exibidos somente se o modelo efetuar a consulta ao indicador com o ponto e data de plantio corretos, temperatura-base explícita e referência encontrada em outra ferramenta; caso contrário ficam indisponíveis.

O Core disponibiliza `pesquisar_internet` ao chat, à estimativa de safra e às notícias. A ferramenta realiza chamada separada ao Vertex AI com Google Search, mantém referências retornadas e exibe as sugestões de busca do Google em quadro isolado. A pesquisa envia a consulta gerada pelo modelo ao provedor, pode gerar custos por consulta e depende da disponibilidade do modelo, Search e credenciais do projeto; não altera IAM ou faturamento. Fontes externas são dados não confiáveis. `POST /api/dashboard/news` solicita notícias com fonte, data e sugestões, reutilizadas por seis horas no armazenamento local; resultados sem referência ou sem data identificável na pesquisa são descartados.

Fase e colheita aceitam percentuais independentes de confiança subjetiva da IA (0–100), com justificativa de até cinco palavras. Esses números não são precisão estatística calibrada. A fase pode ser estimada com cultura confirmada e data exata de plantio ou fase informada pelo agricultor; datas e referências não são inventadas. Fontes e sugestões de busca são exibidas junto da análise; GDD continua condicionado a entradas e referência rastreáveis.

O modo `dashboard_daily` produz resumo, observações e recomendações em JSON validado. Pode usar dados confirmados fornecidos pelo agricultor quando fontes externas estiverem indisponíveis; sugestões sem fonte externa devem ser gerais e prudentes. URLs, quando citadas, devem aparecer em resultados de ferramentas. A validação não comprova que a fonte sustente a afirmação nem que o texto gerado corresponda aos dados: o conteúdo continua identificado como gerado por IA. Falhas não viram zero. A chamada real na VM precisa ser validada.

Snapshots ficam no IndexedDB separado `agrion-dashboard`, por propriedade, seção e assinatura do contexto. Bootstrap e análise diária são reutilizados no dia e fuso locais do navegador; previsão vale uma hora, chuva seis horas e fase 24 horas. Alterar o contexto invalida a reutilização. Se uma atualização falhar, o último resultado do mesmo contexto é exibido como antigo com horário. Chamadas simultâneas duplicadas são compartilhadas na mesma aba; não há coordenação entre abas, usuários ou dispositivos. A consulta no primeiro acesso mantém o carregamento.

## Monitoramento experimental

O monitoramento começa desligado e, nesta etapa, aceita somente amostras explicitamente simuladas de vento e chuva, acionadas pelo usuário na dashboard. `POST /api/dashboard/monitor` envia a amostra e o contexto ao Core em modo próprio, com ferramentas e resposta estruturada; não altera as instruções do chat. O servidor valida horário, medidas e referências presentes nos resultados das ferramentas. Essa presença não comprova que a fonte sustente a conclusão. Uma análise indisponível não é apresentada como condição segura.

Alertas simulados, reconhecimento e histórico ficam no IndexedDB local, por propriedade. Eventos repetidos são agrupados; uma resolução exige avaliação explícita com novas leituras das variáveis que originaram o alerta. Enquanto a simulação está ativa, a interface verifica a cada cinco segundos se há amostra pendente, sem chamar o servidor quando não há dados novos. Ao sair da tela ou interromper a simulação, o processamento no navegador é interrompido. Não há coleta de sensores reais, serviço em segundo plano nem sincronização entre dispositivos; a conexão da futura estação depende de implementação posterior.

O cadastro salva `centerPoint` como GeoJSON Point, em `[longitude, latitude]`, com `method` e `inside_polygon`. O método é o centroide planar por área do anel exterior em coordenadas WGS84, com longitudes ajustadas na mudança de antimeridiano; é uma aproximação e não considera anéis interiores. A geometria atual do cadastro é um único perímetro sem furos. O centroide de um polígono côncavo pode ficar fora da área, indicado por `inside_polygon: false`; não substituí-lo silenciosamente. Registros anteriores sem ponto recebem o cálculo ao serem lidos e a edição da geometria o recalcula. Um resultado de consulta nesse ponto não representa necessariamente toda a propriedade.

Dados do contexto e do histórico são enviados ao modelo como conteúdo, não como instruções de sistema. Essa separação não garante que o modelo ignore instruções maliciosas inseridas nos dados; ferramentas futuras precisarão validar e limitar cada execução no servidor. A configuração e a chamada real na VM dependem de teste posterior com credenciais e acesso ao modelo.

## Ferramentas de análises

### Ferramentas climáticas

`app/services/climate_tools.py` disponibiliza `ClimateTools.nasa_daily`, `rainfall` e `gdd` para consumidores Python. Os métodos fazem POST somente para `/v1/data/nasa-power/daily` ou `/v1/analysis/climate`, validam dados e retornam `{'ok': True, 'data': ...}` com o envelope e a procedência originais. Erros HTTP retornam `ok: false` com código, status e indicação de repetição quando fornecidos; indisponibilidade e timeout são explícitos. Entrada inválida gera `ValueError` antes da chamada. Timeout padrão é 120 segundos. O catálogo do modelo registra `nasa_clima_diario`, `chuva_acumulada` e `graus_dia_acumulados`, com limite de 120.000 caracteres por resultado; respostas maiores exigem um período menor.

NASA retorna dados históricos estimados regionalmente, não medição local nem previsão. `nasa_daily` aceita até 366 dias, variáveis explícitas e UTC ou LST. `rainfall` calcula janelas retrospectivas de 7/15/30/90 dias. `gdd` exige cultura, datas e temperatura-base explícita; a referência da temperatura é opcional e nunca é inventada. Não converte graus-dia em fase fenológica. Dados parciais, ausência e zero permanecem distintos. O consumidor deve fornecer coordenadas WGS84 e avaliar se o ponto central é apropriado.

Teste: `python -B -m unittest discover -s tests -p test_climate_tools.py -v` e `python -B -m unittest discover -s tests -p test_analysis_tools.py -v`. A validação das chamadas externas exige a API atualizada e acesso aos provedores.

### Previsão e indicadores adicionais

O adaptador `ClimateTools.forecast` consulta `/v1/data/weather/forecast`; seu padrão Python permanece `meteomatics`. A ferramenta `previsao_tempo` e a dashboard solicitam `auto`: o Analysis prefere Meteomatics e pode usar Open-Meteo sem misturar fontes. O serviço preserva provedor efetivo, fallback, unidades e limitações; o acesso da Open-Meteo pública tem restrição de uso não comercial e requer atribuição. Os timestamps exigem fuso e intervalos futuros. A conta Meteomatics e suas permissões precisam estar configuradas no container de análises.

`ClimateTools.indicator` encaminha apenas I03, I05, I07, I08 e I14 às rotas agrupadas correspondentes, com entradas explícitas. O motor os expõe como `sequencia_seca`, `exposicao_termica`, `evapotranspiracao_cultura`, `variacao_hidrica` e `margem_cenario`. A validação completa de séries, unidades e referências é feita pela API de análises; erros são retornados sem inventar resultados. I05 não estima dano, I07 não calcula ETo, I08 não estima estoque no solo ou irrigação recomendada e I14 representa apenas o cenário declarado. Integração real do modelo e da API atualizada continua necessitando validação na VM.

O registro em `app/services/tools.py` disponibiliza busca de nomes e requisitos ECOCROP, parâmetros e alertas FAO-56, evidências, fontes e rotações da biblioteca, dicionário AquaCrop, camadas e consulta pontual GAEZ. Cada ferramenta usa um caminho fixo, valida parâmetros e preserva o conteúdo e as fontes retornadas. Consultas locais usam páginas de até 30 registros, com `offset` e filtros exatos; uma página não representa automaticamente toda a base. A API GAEZ pode precisar de paginação própria. Unidades e classes ausentes não devem ser presumidas. Dados e evidências exigem interpretação de seus avisos e status de validação.

### FAOSTAT e simulação AquaCrop

O motor expõe `faostat_paises`, `faostat_produtos` e `faostat_precos`, com paginação limitada e seleção explícita do país e produto. A API mantém ano, unidade, flag e procedência: preços FAOSTAT são referências históricas nacionais, não cotações locais atuais. `margem_cenario` aceita preço declarado ou seleção FAOSTAT histórica exata em USD/t, com custos em USD e demais entradas explícitas. Não há câmbio, projeção ou preenchimento automático de dados ausentes. Os códigos de cultura ECOCROP e FAOSTAT não são intercambiáveis.

`simular_aquacrop` usa `/v1/simulations/aquacrop`: AquaCrop-OSPy 3.0.12 para milho de sequeiro, com clima e hipóteses explícitos; não é a distribuição oficial FAO 7.3 nem resultado observado. O serviço valida o cenário. Para caber no limite de resposta do motor, as séries diárias de clima e balanço são omitidas; totais, parâmetros, referências e limitações permanecem. A resposta completa está na API de análises. O adaptador permite até 120 segundos por chamada; a disponibilidade efetiva também depende de limites de proxy e cliente. A dashboard não estima preço ou produtividade automaticamente sem identificação confiável de país/cultura e dados de cenário.

Na dashboard, `POST /api/dashboard/market-analysis` usa o modo `dashboard_market` do Core para consultar países, candidatos de cultura e último preço histórico. A IA escolhe um candidato, ainda não revisado; o servidor só apresenta preço quando o código aparece nos candidatos e a consulta retorna uma observação única. A seção mostra preço, produto, país, ano e fonte, identificando a correspondência como estimativa. O parecer qualitativo pode aparecer mesmo sem preço. O resultado é armazenado localmente por propriedade e contexto por 24 horas. O endpoint anterior de consulta explícita permanece disponível; o formulário deixou de ser exibido. Notícias, sensores e medições georreferenciadas permanecem sem fonte conectada. Mapa e histórico usam exclusivamente o cadastro e o perfil local existentes.

O motor mantém o conteúdo completo retornado pelo modelo para preservar assinaturas do Gemini e executa no máximo cinco chamadas por tarefa. Consultas GET têm timeout de 20 segundos; os adaptadores POST usam 120 segundos e limites de resposta. Falhas retornam ao modelo como erro explícito, sem dados fictícios. Novas ferramentas exigem revisão e registro explícitos.

Na VM, inicie primeiro `docker compose -f analisys/compose.yaml up -d --build` para criar a rede externa `agrion-analisys-data`; em seguida inicie ou recrie o Compose principal. O container do Agrion participa das redes padrão e de análises e usa `AGRION_ANALYSIS_URL=http://agrion-data:8000`. A rede é obrigatória para subir o Compose principal; não expõe a API de análises publicamente. O acesso ao Vertex AI e à API real ainda precisa ser validado no ambiente da VM.

Teste isolado: `python -B -m unittest discover -s tests -p test_engine.py -v`.

## Revisão das seções da dashboard

Os modos `dashboard_daily` e `dashboard_market` agora podem usar `pesquisar_internet` além das ferramentas do Analysis. O limite de chamadas desses modos foi ampliado para comportar consulta de catálogos, preço histórico e pesquisa. A análise diária aceita o contexto confirmado mesmo quando uma fonte externa falha, mas não cria fatos externos sem referência.

O preço exibido em Produção e mercado é uma estimativa da IA para a safra, baseada em uma observação histórica FAOSTAT validada pelo servidor e, quando houver, em pesquisa complementar. Mantém a unidade e moeda do histórico, exibe confiança subjetiva e não representa cotação atual. O texto curto descreve a expectativa de mercado; não compara a produção declarada pelo agricultor com o mercado.

A estimativa de colheita pode usar referências de ciclo pesquisadas mesmo sem graus-dia calculáveis. Notícias exigem URL recuperada; quando a data não está confirmada no resultado da pesquisa, o cartão omite a data. Falhas nas seções retornam `reason_code` (`engine_unavailable` ou `invalid_result`) e registram somente o tipo do erro nos logs, sem dados do agricultor. Os caches das seções alteradas foram versionados para evitar reutilizar respostas antigas. A validação real das consultas Vertex AI na VM continua necessária.
