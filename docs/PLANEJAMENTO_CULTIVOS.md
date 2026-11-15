# Planejamento de Cultivos

Planejamento abre pelo menu em tela inteira com cabeçalho padrão e Voltar. O fluxo possui culturas/fichas com abas, estratégias selecionáveis, comparação qualitativa de até duas estratégias e plano com cronograma, edição das janelas e checklist. O visual usa as cores e os componentes Agrion e segue a composição da referência registrada em `references/planejamento-cultivos-referencia.md`. As fotos são paisagens já existentes no app e os ícones representam culturas; ainda não há catálogo de fotos específicas por espécie. O anexo original não estava disponível como arquivo para cópia.

## Contrato

`POST /api/planning/analyze`, JSON `{context, inputs}`. Contexto é produzido por AgrionContext. Inputs opcionais: `soil`, `water`, `labor`, `equipment`, `objective` (textos até 600 caracteres), `selected_crops` (até oito nomes). Limite de corpo: 45 KB; contexto combinado: 32 mil caracteres. A proteção existente de origem e limite inicial de 12 requisições/hora por processo é reutilizada; não representa controle global entre workers.

Resposta: `{property_id, result}`. Resultado inclui `schema_version`, `generated_at`, `context_signature`, `status` (`ready`, `partial`, `unavailable`), título, premissas, lacunas, culturas, estratégias e sugestões de pesquisa do provedor. O esquema Pydantic está em `app/services/planning.py` e também instrui o modelo. Item inválido não elimina irmãos válidos. URLs são aceitas somente quando recuperadas nas evidências; presença da URL não comprova sustentação da afirmação. Sem referências, a alternativa é marcada como condicional de baixa confiança; janelas sem referência viram “Janela a confirmar”. Ciclos precisam apontar para culturas existentes na resposta.

## Pesquisa e limites

O modo `planning` do Core usa um ciclo próprio: pesquisa inicial regional, ferramentas internas pertinentes, nova pesquisa quando uma ferramenta falha ou não traz dados e síntese final sem ferramentas ao atingir o orçamento. São até oito turnos e 12 chamadas de ferramentas/pesquisas, com orçamento de investigação de 150 segundos. Uma chamada já iniciada pode concluir após esse prazo; a síntese final tem timeout de 30 segundos. ClimateTools usa timeout de 15 segundos e demais ferramentas GET usam 20 segundos. A interface aborta a espera HTTP em 235 segundos. O servidor pode terminar uma consulta após o cliente sair; a resposta tardia não altera a tela de outra propriedade.

Baixa confiança não bloqueia sugestões. Dados químicos do terreno, doses de reposição, custos, equipamentos e datas não podem ser inventados. O modelo recebe instruções para explicitar premissas e recuperar referências. Não há avaliação determinística que garanta a correção agronômica de cada frase gerada; esta continua sendo uma análise preliminar por IA. A mini estação demo não entra automaticamente no contexto geográfico da propriedade.

## Persistência e indisponibilidade

Análise, complementos, seleção e plano usam um registro versionado por propriedade no IndexedDB `agrion-dashboard`, chave `<property_id>:planning-v1`, separado dos dados demonstrativos. O cache é considerado anterior após 24 horas ou mudança de contexto/complementos. Atualização é explícita quando existe resultado anterior. O plano escolhido preserva ciclos, estratégia, premissas e assinatura para indicar revisão após mudança de contexto. Andamento, janelas definidas pelo usuário e checklist são locais, sem sincronização ou execução automática de operações.

A tela abre antes da IA. Falhas mantêm resultado anterior ou uma tela útil com contexto e opção de nova tentativa. Esperas de contexto/cache e gravação local são limitadas. Sair cancela a requisição HTTP e invalida callbacks antigos.

## Verificações

Testes de servidor cobrem resposta de baixa confiança, pesquisa após falha interna, referências não recuperadas, itens inválidos, falha total e validação de entradas. Suíte completa: 87 testes passando no Docker. `python tests/planning_browser_smoke.py .planning-smoke.html .planning-smoke-mobile.html` gera páginas isoladas de teste para o Chrome; incluem somente fixtures fictícias e simulam o armazenamento e a API para verificar navegação, comparação, plano, persistência pelo adaptador, contexto alterado e falhas. Verificação de layout feita em viewport móvel de 390px e desktop de 1280px, sem transbordamento horizontal.

Ainda é necessário validar respostas reais do Vertex e da API de análises na VM. Nenhum deploy foi executado nesta etapa. O PostgreSQL não é necessário para este fluxo local.
