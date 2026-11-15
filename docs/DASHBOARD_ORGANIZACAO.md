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
