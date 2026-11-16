# Organização da visão geral

A dashboard mostra o mapa e quatro informações da propriedade, o resumo do dia com até três títulos de recomendações e indicadores compactos de clima e safra. Os botões Ver detalhes levam às telas completas. Planejamento e Mini Estação conservam seus módulos e telas.

Destinos do menu:

- Clima: previsão e chuva acumulada.
- Minha safra: desenvolvimento, estimativas, graus-dia e histórico informado na entrevista.
- Análises do Agrion: análise diária, recomendações e notícias/pesquisas.
- Mercado agrícola: análise e preços históricos existentes.
- Medições de campo: informações declaradas de manejo, adubação e cobertura, quando disponíveis. Ainda não há laudos ou medições de solo conectados. A estação tem acesso separado.
- Minha propriedade: cadastro, dados da entrevista e edição do mapa existente.

As telas mantêm cabeçalho e Voltar. A entrada carrega daily, forecast e stage; rainfall, news e market são consultados em seus destinos. O bootstrap de seleção de destaques não bloqueia mais a abertura. O cache por propriedade e assinatura é reutilizado, com indicação de resultados antigos. Callbacks de telas anteriores são invalidados ao navegar. Sugestões de pesquisa do provedor continuam junto ao conteúdo correspondente.

Não há dados inventados para preencher cartões. O estado sem medições fica na tela específica. Estimativas continuam identificadas como IA; períodos e justificativas completos ficam nos detalhes. Não houve mudança no contrato de análise nem nas consultas do servidor.

Teste de navegador: `python tests/dashboard_browser_smoke.py <arquivo.html>` gera uma fixture isolada para navegação, consultas por tela, cache, falhas e acessos ao planejamento e à estação. A fixture usa dados fictícios, sem chamadas de produção. O teste de planejamento existente verifica também o fluxo interno completo.

Limitações: não inclui cadastro de medições, sincronização de planos ou nova integração de fontes. A geração diária e demais endpoints existentes continuam sujeitos à disponibilidade e aos limites de tempo atuais. Validação real e deploy na VM são etapas separadas.

## Indicadores e miniestação

A dashboard inclui Minha estação após o resumo da propriedade, usando o ID salvo em `agrion-station-id-v1` ou `agrion-demo-001`. A estação padrão é identificada como demonstração, sem associação presumida à localização do terreno. Temperatura, umidade relativa do ar, vento estimado e detecção de chuva vêm exclusivamente da API de telemetria. A previsão continua separada e rotulada.

O mesmo componente atende a dashboard e a tela da estação. Consulta imediatamente e repete cinco segundos após cada resposta, sem sobreposição; timeout de dez segundos. Navegar cancela a consulta e o agendamento. Abas ocultas pausam consultas e retomam quando visíveis. Leituras acima de sessenta segundos são antigas; falhas preservam os últimos valores com indicação de atualização indisponível. Sem leitura, não se exibem zeros artificiais. Zero e chuva não detectada são valores válidos.

`agrion-indicators.js` reúne valores com ícones, gauge de umidade com escala real 0–100 e etapas de referência do cultivo. A fase estimada só destaca uma etapa quando corresponde explicitamente a um nome reconhecido; texto ambíguo fica como texto, sem inferir avanço. A fase declarada pode ser usada quando não há estimativa, identificada como informação da entrevista. Etapas anteriores não são marcadas como concluídas. Não há percentual fictício de avanço. As referências de etapas não representam um calendário específico por espécie.

A chuva usa barras apenas para acumulados em períodos de mesma duração e unidade. As janelas atuais de 7, 15, 30 e 90 dias continuam em cartões numéricos. Valores, períodos e origem permanecem disponíveis, com explicações em Veja mais.

## Espaço das pesquisas

Dashboard, telas por assunto e mercado usam o modo compacto de `AgrionSearchSuggestions.append`. Esse modo elimina entradas HTML idênticas dentro do mesmo bloco e mede o conteúdo para ajustar a altura do iframe. Não altera cores, fontes, HTML ou links fornecidos pelo Google. Sugestões continuam visíveis junto à resposta baseada na pesquisa; somente explicações e fontes comuns ficam em expansíveis. Requisitos consultados: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search#requirements_for_search_suggestions

O iframe compacto permite leitura de tamanho pelo documento pai (`allow-same-origin`) e mantém execução de scripts desabilitada; nunca combinar com `allow-scripts`. ResizeObserver acompanha mudanças no conteúdo, e observadores são desconectados na remoção da tela. O modo padrão usado pelo planejamento não foi alterado.

Teste adicional: `python tests/indicators_browser_smoke.py <arquivo.html>` gera verificações de zeros, ausência e envelhecimento das leituras, falhas, polling, pausa de aba, navegação, troca de ID, respostas atrasadas, fases ambíguas, gauge inválido, períodos de chuva e redimensionamento das pesquisas. Fixtures não usam serviços reais.
