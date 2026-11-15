# Plano de implementação: Planejamento de Cultivos

Estado: implementação local concluída; chamadas reais e implantação na VM pendentes. Consulte `PLANEJAMENTO_CULTIVOS.md` para o contrato implementado e as verificações.

## Experiência e referência visual

Entrada pelo item Planejamento do menu. Abrir tela própria, substituindo a visão atual, com cabeçalho padrão Agrion, identificação da propriedade e botão Voltar. Nunca renderizar o fluxo dentro do painel do menu.

A imagem enviada pelo usuário nesta conversa é a referência visual principal: fundo marfim, verde escuro, destaques verde-claro, cartões arredondados com bordas finas, miniaturas agrícolas, ícones simples, botões largos e cronograma vertical. Ela ilustra quatro telas de um fluxo, não quatro telefones a serem reproduzidos na página. Em dispositivos maiores, aproveitar colunas para comparação. Preservar HTML, JavaScript, CSS/Tailwind existentes.

O template de Planejar em `app/templates/index.html` e `references/agrion_tailwind.html` serve como base estrutural. Seus exemplos demonstrativos não serão usados como respostas reais. A imagem original ainda não está disponível como arquivo no workspace; o registro visual detalhado está em `references/planejamento-cultivos-referencia.md`. Copiar o arquivo original para references quando seu caminho estiver disponível.

## Fluxo

1. Culturas sugeridas: lista priorizada com motivo curto, benefício esperado e ressalva principal. Abrir ficha de uma cultura com imagem, abas Visão geral, Condições, Manejo e Mercado. Permitir selecionar culturas de interesse. A lista é necessária antes da ficha de milho exemplificada na imagem.
2. Comparar culturas e rotações: chips das culturas selecionadas; até três estratégias compatíveis com o contexto, com sequência de culturas/coberturas, solo, água, trabalho, mecanização e custo. Nomes e sequências vêm da análise, não de exemplos fixos.
3. Comparar estratégias: duas estratégias lado a lado, visão comparativa e detalhes expansíveis. Indicadores de conservação do solo, pressão sobre água, risco, custo e esforço operacional, cada um com justificativa. Preferir escalas qualitativas; barras numéricas somente com método e base explícitos, nunca percentuais fictícios de recuperação do solo.
4. Plano de cultivo: estratégia escolhida, abas Cronograma, Resumo e Premissas, ciclos em linha do tempo, ações editáveis e checklist. Datas aproximadas identificadas como tal; sem janela regional fundamentada, mostrar ordem relativa dos ciclos. Salvar o plano no navegador por propriedade. Acompanhamento inicial significa checklist e estado dos ciclos; não prometer automação agrícola ou alertas ainda inexistentes.

## Contexto e fontes

Reutilizar AgrionContext: localização, área, culturas atuais e anteriores, objetivo, irrigação, mecanização e informações de trabalho declaradas. Permitir complementar solo, disponibilidade efetiva de água, mão de obra e equipamentos sem obrigar preenchimento para receber uma sugestão preliminar.

- ECOCROP: requisitos das culturas e compatibilidade ambiental.
- Biblioteca de rotações, evidências e fontes: diversidade, coberturas, recuperação e ciclagem de nutrientes; conferir a procedência e as limitações dos registros.
- GAEZ: listar as camadas antes de escolher e consultar. Usar apenas variáveis realmente disponíveis, respeitando escala, unidade e ausência de dados. Não converter aptidão regional em análise química do terreno.
- FAO-56: parâmetros hídricos com suas referências e auditorias. Sem entradas suficientes, comparar qualitativamente, sem inventar irrigação em mm.
- NASA POWER: histórico climático e sazonalidade. Previsão Meteomatics/Open-Meteo apenas para o horizonte coberto.
- FAOSTAT: referência histórica nacional, não preço local garantido ou lucro projetado.
- Pesquisa Google via Vertex AI: complementar referências agronômicas e regionais quando as ferramentas internas forem insuficientes. Registrar URLs recuperadas, datas quando presentes e metadados exigidos pelo provedor.

Não considerar chuva detectada pela mini estação como volume precipitado ou água disponível. O vínculo por ID não comprova localização da estação; sua leitura não entra automaticamente na análise daquela propriedade.

Sem laudo, não afirmar níveis atuais de N/P/K, pH, matéria orgânica ou correções necessárias. Distinguir reciclagem de nutrientes, possível fixação biológica e reposição por insumos; não atribuir quantidade reposta sem base. Trabalho e mecanização são avaliados conforme dados declarados e referências, sem inventar máquinas disponíveis.

## Core e contrato

Criar modo dedicado `planning`, isolado do chat e da dashboard, com ferramentas e pesquisa habilitadas. Gerar dados JSON; HTML permanece em templates controlados pela aplicação.

Entrada do endpoint proposto `POST /api/planning/analyze`: contexto da propriedade, complementos declarados, culturas selecionadas e objetivo. Resposta versionada: status, generated_at, context_signature, headline, assumptions, missing_inputs, crops, strategies, sources e limitações.

Cada cultura terá ID estável, nome, prioridade, motivo, condições, manejo, água, trabalho, mecanização, mercado, confiança qualitativa e referências. Cada estratégia terá ID, nome, headline, ciclos com cultura e propósito, benefícios, restrições, avaliações por critério, confiança, justificativa e fontes. Confiança representa julgamento do modelo, não precisão medida.

Instruções centrais: consultar as ferramentas pertinentes; pesquisar para preencher lacunas; sempre devolver uma análise útil mesmo com evidência parcial e confiança baixa. Não descartar sugestões apenas por baixa confiança. Quando não houver base suficiente para recomendar uma cultura específica, devolver caminhos condicionais e próximos dados a confirmar, sem criar compatibilidade agronômica falsa. Falha total do modelo não pode ser mascarada como resposta da IA: preservar o último resultado válido e oferecer nova tentativa.

Separar falhas internas dos textos publicáveis. Títulos curtos e resumos com detalhes expansíveis, sem URLs embutidas ou relatos de consultas malsucedidas; fontes estruturadas continuam disponíveis nos detalhes/metadados apropriados. Validar tipos, limites, IDs, referências retornadas e campos numéricos no servidor. Uma fonte presente não prova, sozinha, que sustenta a afirmação.

### Continuidade obrigatória da análise e da tela

A tela inteira de Planejamento deve abrir imediatamente, sem depender da conclusão da IA. Cabeçalho, Voltar, etapas, contexto conhecido e estados de carregamento são renderizados pela aplicação.

Para cada informação relevante ausente ou consulta sem resultado, o Core deve buscar uma alternativa: consultar outra ferramenta pertinente, pesquisar na internet e adaptar a consulta para cultura, região e objetivo. Falha de uma fonte não encerra a tarefa. Dentro de um orçamento finito de chamadas e tempo, consolidar o que foi obtido e responder, mesmo com confiança baixa. As etapas devem ter limites próprios para evitar carregamento infinito.

Se a pesquisa também não recuperar evidência suficiente, manter as partes fundamentadas e apresentar alternativas condicionais com premissas e dados a confirmar. Ausência de evidência não autoriza inventar nutrientes, aptidão, disponibilidade hídrica, custos ou calendários. Não transformar um item incompleto em indisponibilidade de toda a página.

Se houver falha total do Core ou JSON irrecuperável, a aplicação continua exibindo a tela: último plano/análise salvo, identificado como anterior; sem histórico, resumo dos dados declarados, informações necessárias e ação de nova tentativa. Nenhuma resposta padrão será identificada como recomendação gerada pela IA. Todos os caminhos devem encerrar o carregamento e manter a navegação utilizável.

Critérios de aceite: fonte interna indisponível aciona pesquisa; pesquisa sem resultado preserva resposta parcial; baixa confiança não remove sugestões; falha total sem cache mantém a tela funcional; nenhum desses casos termina em página vazia ou spinner permanente.

Evitar repetir consultas por cultura: recuperar primeiro o contexto ambiental compartilhado, depois requisitos e rotações candidatas. Limites de chamadas e tempo próprios para o planejamento, com retorno parcial e cache por assinatura do contexto; seleção e comparação usam o resultado já recebido.

## Organização e persistência

Proposta: `app/api/planning.py`, `app/services/planning.py`, `app/static/agrion-planning.js` e CSS específico reutilizando os componentes existentes. Integrar à navegação de tela inteira e reutilizar o cabeçalho. Persistir análise e plano selecionado por propriedade no IndexedDB, separados dos dados demonstrativos e da telemetria. Mudança no contexto invalida a análise; plano salvo mantém versão, premissas e aviso de revisão necessária.

## Etapas e validação

1. Guardar referência original, completar inventário de campos disponíveis na API de análises e definir contrato JSON.
2. Implementar serviço de análise, ferramentas, validação, resposta parcial e testes com ferramentas simuladas de teste.
3. Construir fluxo visual, navegação, seleção e comparação próximas da referência.
4. Persistir plano, checklist e edição; integrar atualização e estado de resultado antigo.
5. Testar baixa confiança, fontes indisponíveis, laudo ausente, JSON inválido, URLs inventadas, troca de propriedade e resultados antigos. Testar ida/volta, seleção e persistência no navegador, além do layout em celular e desktop.
6. Validar na VM chamadas reais e aparência antes de concluir a integração. Publicação depende de autorização; não faz parte desta etapa de planejamento.
