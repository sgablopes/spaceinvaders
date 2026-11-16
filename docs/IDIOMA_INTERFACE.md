# Idioma da interface

A preferência global usa `agrion-ui-language-v1` no `localStorage`. Uma escolha explícita tem prioridade; sem ela, somente o idioma principal do navegador igual a `pt-BR` seleciona português. Todos os demais valores, incluindo `pt-PT`, selecionam `en-US`. O seletor fixo no topo atualiza a preferência e o atributo `lang` do documento.

O idioma de uma entrevista com respostas registradas continua fixo conforme o contrato do Discovery.

A etapa 2 traduz a entrada, a identificação da pessoa e o cadastro/edição geográfica da propriedade. Os textos usam chaves estáveis no módulo de propriedade e na tela de entrada. O controle de busca do MapTiler recebe o idioma de interface, mantendo a restrição de país existente. A troca de idioma redesenha a tela de propriedade e recria o mapa sem alterar o registro salvo.

A etapa 3 usa o idioma global para iniciar novas entrevistas do Discovery. O idioma da voz continua fixo depois da primeira resposta; nesse caso, o seletor global atualiza apenas os textos da entrevista e exibe o idioma de voz mantido. Formulário, progresso, estados e erros usam o idioma da interface, enquanto IDs e valores salvos continuam canônicos.

Verificação de navegador: `python tests/locale_browser_smoke.py <arquivo.html>` gera um arquivo de teste isolado para abrir no Chrome. Ele cobre detecção, fallback, seleção, persistência e atributo `lang`.

A etapa 4 traduz a visão geral e as seções de clima, cultura, análises, medições, mercado e propriedade. Textos locais, estados de carregamento e falha usam o idioma da interface. Datas e números seguem o locale. O idioma também é enviado no contexto das consultas do dashboard, separando os caches por idioma e orientando as respostas geradas pelo modelo. IDs, valores canônicos e registros salvos não são traduzidos.

Verificação da etapa 4: `python tests/dashboard_locale_browser.py <arquivo.html>` gera um cenário isolado com dados presentes e indisponíveis, para executar no Chrome. O teste de unidade em `tests/test_engine.py` cobre a instrução de idioma das consultas do dashboard.

A etapa 5 traduz Planejamento de Cultivos, Mini Estação Meteorológica e chat do Assistente. O planejamento envia `ui_language` ao modelo e atualiza a análise quando o idioma muda; campos, estados dos ciclos e demais valores persistidos continuam canônicos. Textos livres já salvos, inclusive respostas do modelo e planos anteriores, preservam o idioma em que foram criados. O chat abre com o idioma global selecionado e conserva seu seletor próprio de idioma da conversa. O protótipo legado não integra esta etapa, conforme orientação do projeto. A verificação de navegador está em `tests/tools_locale_browser.py`.

## Revisão final (etapa 6)

O título, a descrição e o atributo `lang` do documento acompanham a preferência global. A data de plantio exibida na visão geral usa o locale; a fase canônica `fallow` aparece como **Pousio** ou **Fallow**. A revisão de acessibilidade incluiu controles visíveis sem nome e campos sem rótulo; os campos complementares de equipamentos e objetivo no formulário manual receberam nomes acessíveis.

Executar a suíte com `python -m unittest discover -s tests -v`. A navegação completa usa `python tests/full_locale_e2e.py`: o script renderiza a página pelo cliente de testes do Flask, abre o HTML e os recursos reais no Chrome headless e percorre entrada, propriedade, Discovery por voz e formulário, visão geral, seis seções do menu, planejamento, estação e chat em `pt-BR` e `en-US`. Verifica textos selecionados, metadados, data de plantio, campos sem rótulo, botões sem nome e largura horizontal. As respostas das APIs externas nesse roteiro são **simuladas**. Ele não valida a qualidade das traduções produzidas pela IA, serviços externos, mapa com chave real, áudio Live, nem o comportamento em uma VM HTTPS. O Chrome headless deste ambiente aplicou viewport CSS de 498 px à configuração móvel; outras larguras e dispositivos reais ainda precisam de conferência visual.

Resultado da revisão local: 93 testes Python passaram e o roteiro completo passou nos dois idiomas. A navegação foi executada como arquivo local porque este ambiente bloqueou a porta HTTP de loopback.
