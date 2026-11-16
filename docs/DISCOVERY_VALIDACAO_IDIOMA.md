# Discovery: duas safras, informações opcionais e idioma

## Contrato ativo

O perfil novo usa versão 1.2.0. `current_crop` representa somente o cultivo atual; `last_crop` representa a cultura imediatamente anterior (ou a última encerrada quando não há cultivo atual). `previous_crop` deixou de fazer parte dos campos ativos do formulário, extração e checklist. Registros antigos permanecem no IndexedDB, sem limpeza ou troca de versão do banco. O campo legado é filtrado dos contextos de análise e não aparece no histórico da dashboard. Não há inferência nem cópia automática entre safras antigas.

Ausências explícitas são fatos: `current_crop={crop:null,not_planted:true}` e `planting_date={not_planted:true}` indicam ausência de plantio atual. `last_crop={crop:null,no_previous_cultivation:true}` indica ausência de cultivo anterior, resolvendo o resultado anterior como `not_applicable`. O formato legado `never_cultivated=true` continua aceito. Ausência de cultivo anterior não implica ausência de cultivo atual.

O resultado qualitativo da colheita é suficiente. Quantidade e valor são complementos opcionais e não entram na regra de conclusão, no progresso nem na auditoria direcionada do backend. Valores efetivamente fornecidos ainda precisam ser interpretáveis: quantidade exige unidade, e valor manual exige tipo. O formulário oferece Continuar sem quantidade e valor; Não sei informar também ignora detalhes numéricos incompletos. Números negativos ou não finitos são rejeitados no formulário.

## Formulário e voz

Salvar e continuar para análise registra as respostas presentes e marca pendências não respondidas como `unknown`, motivo `declined` (a pessoa escolheu seguir sem fornecê-las). Não apaga respostas existentes. Incertezas já registradas são mantidas e podem acompanhar uma análise preliminar. Salvar para continuar depois mantém a entrevista manual aberta e preserva pendências.

O formulário compara as respostas com a representação inicial. Campos não editados não sobrescrevem evidências, incertezas ou detalhes extras recebidos pela voz. A edição explícita continua gerando revisão de origem `user_edit`. A transição de voz para manual permite que a fila de extração existente termine dentro do limite já existente de quatro segundos, antes de trocar a tela. A validação de evidência literal, revisão do perfil, confirmação de incerteza e protocolo de conclusão do Live foram mantidos.

## Idioma

`discovery-language.js` prioriza a preferência salva em `agrion-interview-language-v1`, depois os idiomas suportados de `navigator.languages` / `navigator.language`; português usa `pt-BR`, inglês usa `en-US`, demais idiomas usam inglês. Um perfil com respostas preserva o idioma registrado no perfil ou na sessão anterior quando suportado.

O seletor oferece português e inglês na entrevista de voz e no formulário. Fica bloqueado na primeira transcrição/resposta ou alteração de campo manual, incluindo antes de salvar. É uma escolha de idioma da entrevista; não traduz a dashboard inteira. Traduções não alteram IDs, categorias, unidades ou valores digitados. Valores financeiros do formulário continuam explicitamente em BRL.

Antes da primeira resposta, a troca encerra a sessão anterior como parcial (`language_changed`), interrompe microfone e áudio, limpa o estado transitório e cria nova sessão. Callbacks capturam a identidade da conexão e da entrevista para ignorar eventos atrasados. A captura de microfone também verifica se a sessão ainda é atual após conceder permissão. O seletor fica temporariamente desabilitado durante a troca.

O modelo Live configurado em `GEMINI_LIVE_MODEL` permanece o mesmo. O backend define a voz: português usa Orus; inglês omite `voiceConfig`, usando a voz padrão do provedor. O cliente não pode escolher outro modelo ou voz. Espanhol não é oferecido nem aceito para novas conexões.

## Validação e limites

Testes Python verificam paridade dos campos JS/Python, configuração de voz, ausência de cultivo atual, colheita qualitativa sem exigência numérica, extração, recuperação de respostas e evidências. `python tests/discovery_browser_smoke.py <arquivo.html>` gera uma fixture isolada que simula WebSocket, áudio, extração e armazenamento. Verifica troca durante conexão/fala, descarte de eventos antigos, bloqueio após resposta, idioma do formulário, transição voz/manual, dados opcionais, salvamento parcial e preservação do legado.

Fixtures não comprovam pronúncia, escolha efetiva da voz padrão nem comportamento do modelo em conversas reais. Validar na VM HTTPS uma entrevista curta em cada idioma, a troca antes da primeira resposta e o fluxo manual sem números. Reinícios por idioma contam como novas conexões no limite existente de oito sessões por hora. Não houve alteração de IAM, credenciais, transporte de áudio ou implantação remota.
