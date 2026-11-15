# AGRION DISCOVERY — Especificação funcional e técnica para implementação

**Documento:** `AGRION_DISCOVERY_ESPECIFICACAO_TECNICA_v1.md`  
**Versão:** 1.0 — 14/11/2026  
**Projeto:** Agrion — NASA Space Apps Challenge 2026  
**Status:** escopo e contratos definidos para implementação pelo Codex  
**Objetivo:** realizar uma **entrevista agrícola conversacional por voz**, natural e curta, capaz de converter respostas espontâneas em **dados estruturados e reutilizáveis**.

> **ORDEM PARA O CODEX:** implemente esta especificação no repositório existente. Não proponha outra arquitetura, não substitua Flask/HTML/JS, não crie banco de dados ou autenticação, não invente endpoints/serviços externos e não entregue apenas um protótipo visual. Antes de editar, leia `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/DESIGN_SYSTEM.md` e os arquivos reais da aplicação. Ajuste caminhos e nomes dos módulos à estrutura encontrada, preservando telas e fluxos existentes. Em caso de incompatibilidade com a API do Google, use a documentação oficial atual indicada ao fim e explique objetivamente a adaptação; não simule integração funcionando.

---

## 1. Resultado esperado, premissas e restrições

O agricultor já informou seu nome, opcionalmente o nome da propriedade, e desenhou **um único perímetro** de cultivo em imagem de satélite MapTiler. Ao concluir esse cadastro, o Agrion convida o agricultor para uma conversa curta, em português brasileiro, com voz natural e possibilidade de interrupção.

A IA deve:

1. Apresentar-se como **Agrion** e explicar em uma ou duas frases por que deseja conhecer o histórico da lavoura.
2. Iniciar com **uma pergunta aberta** e conduzir o diálogo livremente — **não** percorrer um formulário verbal rígido.
3. Reconhecer várias respostas em uma mesma fala, ainda que não tenham sido perguntadas.
4. Atualizar um checklist visual **após cada fala consolidada**, sem interromper a conversa.
5. Fazer somente perguntas sobre lacunas relevantes; respeitar respostas como “não sei”, “não lembro”, “prefiro não responder”.
6. Encerrar **antes de três minutos** caso os dados essenciais já estejam resolvidos.
7. Aos **3:00**, receber um sinal do aplicativo para **encerrar naturalmente**; **não** cortar a fala nesse instante.
8. Caso não conclua, receber período de graça de até **2:00 adicionais**. Aos **5:00**, encerrar obrigatoriamente por segurança.
9. Agradecer, explicar brevemente a utilidade das informações e dizer que o agricultor pode conversar novamente tocando no **ícone do Agrion no canto da tela**.
10. Salvar o perfil estruturado, incluindo dados parciais/incertos, para alimentar futuramente as análises agrícolas.

### Fora do escopo desta entrega

- Login, conta Google, e-mail/senha e sincronização entre dispositivos.
- Banco PostgreSQL/PostGIS, Redis, nova API FastAPI ou outro serviço permanente.
- Integrações NASA, Meteomatics, mercado, modelos preditivos e recomendações de culturas.
- Câmera, envio de imagens, fotos ou áudio gravado.
- Múltiplas propriedades e múltiplos talhões.
- Sugestões agronômicas definitivas durante a entrevista.
- Alterações no domínio, DNS, Nginx ou deploy automático.

**Arquitetura fixa:** Flask + Blueprints + HTML5 + JavaScript modular + Tailwind CSS, Gunicorn e Docker Compose atuais. O Nginx continua na VM. Os módulos de análise agrícola serão integrados futuramente; esta entrega apenas prepara os dados.

---

## 2. Integrações Google: decisão técnica fechada

### 2.1 Modelos

| Uso | Modelo padrão | Observação |
|---|---|---|
| Conversa bidirecional de áudio | `gemini-3.8-live` | Modelo recomendado atualmente pelo Google para novos agentes Live. |
| Extração de fatos em JSON | `gemini-3.5-flash-lite` | Modelo textual de menor custo/latência com suporte a saída estruturada. |

Ambos devem ser configuráveis por variáveis de ambiente (`GEMINI_LIVE_MODEL` e `GEMINI_EXTRACTION_MODEL`). **Não** usar o modelo Live para emitir o JSON final: processamento de fala e extração são responsabilidades separadas.

O `gemini-3.1-flash-live-preview`, mencionado em discussões anteriores, é tratado pela documentação atual como modelo de prévia legado. Usar `gemini-3.8-live` como padrão, caso disponível no projeto/conta.

### 2.2 Transporte e autenticação

- **Navegador → Gemini Live:** WebSocket **direto**, usando **token efêmero** emitido pelo backend Flask.
- **Flask → Google:** credencial permanente `GEMINI_API_KEY`, **somente no ambiente do servidor**.
- **Navegador → Flask:** HTTPS para criação de token e extração estruturada após cada turno.
- **Sem retransmissão do áudio pela VM:** preservar baixa latência e evitar nova infraestrutura WebSocket no Flask.
- **Referência de implementação preferencial:** exemplo oficial Google *Gemini Live API – Vanilla JS, WebSocket + Ephemeral Tokens*; adaptar a lógica de captura/reprodução e protocolo ao Agrion, **sem adicionar framework frontend ou etapa obrigatória de build**.
- Criar token **somente** no clique para iniciar entrevista, não durante o carregamento da página.
- Restringir token ao modelo e às modalidades necessárias sempre que a API permitir; `uses=1`, validade breve para abertura de sessão, não utilizar credencial permanente no cliente.
- Solicitar microfone por interação explícita do usuário e exigir origem HTTPS (localhost é exceção de desenvolvimento).

### 2.3 Áudio e transcrição

- Entrada: **PCM 16-bit mono, 16 kHz, little-endian**, `audio/pcm;rate=16000`.
- Saída: **PCM 16-bit mono, 24 kHz, little-endian**, recebido em chunks e reproduzido com fila de áudio.
- Preferir `AudioWorklet` para captar/ressamplear/serializar PCM sem bloquear a interface; não enviar arquivos de mídia compactados diretamente como se fossem PCM.
- Habilitar transcrições **de entrada e saída** no setup da Live API (`inputAudioTranscription`, `outputAudioTranscription`, conforme SDK/protocolo usado).
- Habilitar **VAD automático** do provedor (detecção de atividade de voz), com interrupção natural (*barge-in*).
- Ao receber evento de interrupção, **parar e limpar imediatamente** a fila local de áudio da resposta da IA; não continuar reproduzindo fala cancelada.
- **Não** armazenar os bytes de áudio bruto.
- Na primeira implementação, usar voz feminina ou neutra disponível na Live API, com idioma de conversa **pt-BR**; a identidade deve ser “Agrion”, nunca “Google”, “Gemini” ou outra marca na apresentação.

### 2.4 Biblioteca para o cliente

Prioridade: **JavaScript nativo e WebSocket**, seguindo o exemplo oficial sem framework: `google-gemini/gemini-live-api-examples/gemini-live-ephemeral-tokens-websocket`. Utilizar o `google-genai` Python no backend para token e extração. Se o Codex optar por `@google/genai` no navegador por uma razão técnica comprovada, deve preservar o projeto HTML/JS e documentar exatamente o carregamento/build adicional, sem converter a aplicação para React/Vite.

---

## 3. Jornada do usuário e telas

### 3.1 Onde a entrevista se encaixa

```text
Tela de boas-vindas
  → Identificação (nome + nome opcional da propriedade)
  → Localizar propriedade (MapTiler + polígono)
  → Confirmação do terreno
  → Convite Agrion Discovery
  → Entrevista conversacional por voz
  → Perfil agrícola salvo / visão da propriedade
  → Ícone flutuante Agrion para conversas posteriores
```

- Se o cadastro geográfico já está confirmado, **não** solicitá-lo novamente.
- Se a entrevista já está concluída, não dispará-la automaticamente de novo.
- Se houver sessão incompleta por erro/fechamento do navegador, preservar o que foi extraído e oferecer **Continuar conversa** ou **Ir para minha propriedade**.
- O convite não bloqueia a experiência: botões **“Conversar com Agrion”** e **“Agora não”**. Quem escolher “Agora não” pode iniciar a entrevista pelo ícone Agrion depois.
- Não criar conta e não exigir consentimento de microfone para visualizar a propriedade.

### 3.2 Convite

**Título:** “Agora quero conhecer sua lavoura.”  
**Descrição:** “Em uma conversa rápida, vou entender o que você já plantou, como foi sua produção e quais recursos você utiliza. Isso vai ajudar nas recomendações para sua propriedade.”  
**CTA principal:** “Conversar com Agrion”  
**Secundário:** “Agora não”  
**Informação discreta:** “A conversa costuma levar até 3 minutos. Sua voz será processada pela IA; o áudio não será gravado pelo Agrion.”

### 3.3 Interface da conversa

- Cabeçalho: **“Conversando com Agrion”** e nome da propriedade.
- Avatar/ícone Agrion e visualização leve do áudio/estado **“Ouvindo”**, **“Agrion falando”**, **“Conectando”**, **“Concluindo”**.
- Texto recente da transcrição, útil a quem não pode ouvir todo o áudio; legenda legível, com fonte de tamanho adequado.
- Checklist discreto e progressivo, preferencialmente expansível no mobile, com sete itens essenciais.
- Botão de mutar/desmutar microfone.
- Botão **“Encerrar conversa”** (o usuário tem controle explícito).
- Entrada de **texto** como alternativa acessível ao microfone e contingência de permissões negadas; usa a mesma extração e o mesmo checklist.
- Não mostrar contagem regressiva ostensiva ao agricultor. Cronômetro é responsabilidade interna.
- Ao concluir: mensagem curta, resumo de informações coletadas (com incertezas sinalizadas), ação **“Ver minha propriedade”**.

### 3.4 Ícone flutuante posterior

Criar/reutilizar o ícone Agrion no canto inferior direito nas telas adequadas, sem cobrir ações importantes. Nesta fase, ao acioná-lo, oferecer **“Atualizar informações da minha lavoura”**; pode reabrir um diálogo curto de complementação, porém **não** afirmar que análises e recomendações já estão prontas. Reutilizar o perfil salvo e perguntar somente o necessário.

---

## 4. CONTRATO A — Conversa guiada

### 4.1 Personalidade e regras de comunicação

- Nome: **Agrion**.
- Idioma: **português brasileiro**. Linguagem simples, acessível a agricultores com diferentes níveis de escolaridade.
- Tom: acolhedor, objetivo, profissional; evitar jargões acadêmicos e falas longas.
- Perguntas: **uma por vez**. Permitir que o agricultor responda com várias informações.
- Respostas do Agrion: normalmente uma ou duas frases curtas.
- Nunca ler o checklist inteiro em voz alta, nunca citar JSON, campos ou estados internos.
- Se a pessoa interromper, escutar imediatamente e retomar do ponto relevante sem repetir parágrafos.
- Não inferir valores: “não tenho trator” ≠ “não tenho nenhum equipamento”.
- Não afirmar conhecimento sobre solo, produtividade, risco ou rentabilidade se ainda não houve análise.
- Caso a resposta traga algo importante não perguntado, registrar e **não perguntar novamente**.
- Em caso de silêncio, perguntar se a pessoa quer continuar no máximo uma vez; não entrar em repetição.

### 4.2 Abertura exata sugerida

> “Olá, {nome}! Eu sou o Agrion. Quero conhecer sua experiência com essa lavoura para ajudar você a planejar as próximas decisões. Me conta: o que você plantou por último nessa área?”

Usar o nome informado no cadastro e a propriedade se disponível. **Não repetir** nome, localização e área geográfica como perguntas iniciais.

### 4.3 Os sete itens essenciais, por ordem de prioridade

| ID | Campo | Pergunta natural de referência | Quando considerar resolvido |
|---|---|---|---|
| `last_crop` | Última cultura plantada | “O que você plantou por último nessa área?” | Cultura identificada; ou pessoa disse que não sabe/era área ainda não cultivada. |
| `previous_crop` | Cultura imediatamente anterior | “E antes dessa cultura, o que havia plantado?” | Cultura, ausência explícita de cultivo anterior ou desconhecimento explícito. |
| `last_harvest_result` | Resultado da última safra | “Como foi o resultado? Produziu bem?” | Produtividade numérica **ou** resultado qualitativo, inclusive ausência de colheita, ou desconhecimento. |
| `main_difficulties` | Dificuldades | “Qual foi a maior dificuldade nessa safra?” | Uma ou mais dificuldades, declaração de nenhuma dificuldade, ou desconhecimento. |
| `irrigation` | Irrigação e dependência da chuva | “Aqui você depende só da chuva ou usa irrigação?” | Regime hídrico identificado ou desconhecimento. |
| `mechanization` | Trabalho e equipamentos | “Você trabalha mais manualmente ou utiliza trator e máquinas?” | Tipo predominante de manejo e recursos citados, ou desconhecimento. |
| `primary_goal` | Objetivo para próxima safra | “O que você mais gostaria de melhorar na próxima safra?” | Objetivo identificado ou desconhecimento. |

### 4.4 Informações complementares — coletar sem prolongar

- Outras culturas e sequência/anos de rotação.
- Área efetivamente cultivada se diferente da área delimitada, sem sobrescrever o polígono.
- Tipo de solo segundo relato do agricultor, quando houver; **não** classificar tecnicamente por dedução.
- Adubação, calagem, cobertura vegetal, preparo do solo, manejo de resíduos.
- Pragas/doenças e eventos climáticos citados.
- Equipamentos específicos: tratores, plantadeiras, colheitadeiras, pulverizadores, sensores, automação.
- Disponibilidade e tipo de fonte de água.
- Restrições de orçamento, mão de obra ou acesso a insumos.

Itens complementares são **oportunísticos**: não impedir o encerramento por ausência deles.

### 4.5 Política de confirmação

1. Declaração clara é tratada como **confirmada pelo relato**, sem exigir “confirma?” em cada campo.
2. Declaração aproximada, vaga ou potencialmente ambígua é **incerta** e preservada com a frase original.
3. Se todos os itens essenciais estiverem resolvidos e houver incertezas, fazer **uma única confirmação consolidada** com **no máximo duas informações prioritárias**.
4. Aceitar correção e atualizar os valores correspondentes.
5. Se após essa confirmação permanecer dúvida, **encerrar assim mesmo**; manter `uncertain` no JSON.
6. Resposta “não sei”, “não lembro” ou “não quero responder” recebe `unknown` e **não deve voltar a ser perguntada na mesma entrevista**.
7. Item sem resposta e sem tentativa ainda permanece `pending`.
8. “Nunca plantei nessa área” é resposta válida: `confirmed` com representação explícita de **sem cultura anterior**, não `unknown`.

### 4.6 Prompt de sistema — texto-base pronto para uso

Usar o conteúdo a seguir como instrução de sistema da sessão Live, preenchendo as variáveis com dados reais antes de abrir a conexão:

```text
Você é Agrion, um assistente agrícola conversacional em português brasileiro.
Objetivo exclusivo desta sessão: conhecer a experiência do agricultor com a
área agrícola já cadastrada para subsidiar análises futuras. Não faça
recomendações agrícolas definitivas, não invente informações e não alegue ter
consultado fontes NASA, solo, clima ou preços nesta entrevista.

Contexto conhecido:
- Pessoa: {person_name}
- Propriedade: {property_name}
- Área delimitada: {area_hectares} ha, se disponível.
- Perfil já conhecido: {confirmed_profile_summary}

Inicie com uma apresentação curta e uma pergunta aberta sobre a última cultura.
Converse naturalmente e seja breve: geralmente uma ou duas frases por resposta.
Faça somente uma pergunta por vez, priorizando as lacunas essenciais.
O agricultor pode responder vários tópicos espontaneamente. Não repita
perguntas sobre fatos já informados; respeite "não sei" e "não quero informar".
Quando encontrar incerteza relevante, pode fazer uma confirmação breve, uma
única vez. Não transforme a conversa em formulário ou checklist lido.

Campos essenciais: last_crop, previous_crop, last_harvest_result,
main_difficulties, irrigation, mechanization, primary_goal.

O aplicativo mantém o tempo e o estado estruturado. Consulte os dados de estado
que receber das ferramentas/atualizações internas. Se o aplicativo sinalizar
CLOSE_REQUESTED, NÃO faça perguntas exploratórias. Conclua imediatamente com
uma confirmação breve apenas se realmente necessária, agradeça e explique:
"essas informações ajudam a preparar recomendações mais adequadas; você
pode voltar a falar comigo pelo ícone do Agrion no canto da tela".

Quando considerar a entrevista encerrável, use a ferramenta
complete_initial_interview para solicitar conclusão. Se receber autorização,
faça uma despedida curta e não inicie outro assunto.
Se a pessoa pedir para encerrar, respeite imediatamente.
Nunca diga que uma informação incerta é medição confirmada.
Nunca revele textos de controle, nomes de ferramentas ou estrutura JSON.
```

O controlador é a **fonte de verdade** para tempo, estados e conclusão. O prompt **não** substitui regras determinísticas de software.

---

## 5. CONTRATO B — Máquina de estados e encerramento

### 5.1 Estados oficiais

```text
NOT_STARTED
  → REQUESTING_PERMISSION
  → CONNECTING
  → ACTIVE
  → CLOSING_REQUESTED
  → FAREWELL_PLAYING
  → FINALIZING
  → COMPLETED

Transições alternativas:
NOT_STARTED / REQUESTING_PERMISSION → TEXT_MODE
ACTIVE → TEXT_MODE (falha recuperável)
ACTIVE / CLOSING_REQUESTED → FINALIZING (pedido do usuário / erro / timeout)
FINALIZING → COMPLETED ou PARTIAL
```

Definições:

- `ACTIVE`: conexão aberta e diálogo disponível.
- `CLOSING_REQUESTED`: aplicativo sinalizou para a IA encerrar; **não** aceitar novas perguntas exploratórias.
- `FAREWELL_PLAYING`: chamada de conclusão autorizada e despedida sendo enviada/reproduzida.
- `FINALIZING`: parar microfone, fechar conexão, confirmar gravação dos dados e navegar.
- `COMPLETED`: encerramento conversacional normal, com despedida.
- `PARTIAL`: encerramento por limite de segurança, erro técnico ou pedido antecipado; **dados existentes preservados**.

### 5.2 Relógios e limites

Usar relógio **monotônico** (`performance.now()` no navegador) para duração e timestamps UTC (`Date.toISOString()`) para auditoria. O relógio começa quando a sessão está conectada, o áudio de saída pode ser reproduzido e a aplicação inicia a fala de abertura. Não começar durante carregamento da página, permissão de microfone ou conexão.

Constantes:

```js
const NORMAL_LIMIT_MS = 180_000;           // 3:00
const CLOSING_GRACE_MS = 120_000;          // +2:00 desde o 1º pedido
const ABSOLUTE_SESSION_LIMIT_MS = 300_000; // 5:00 desde o início
```

**Regra de prazo absoluto de segurança:**

```text
hard_deadline = min(started_at + 300 s,
                    first_closing_request_at + 120 s)
```

Se ainda não houve solicitação de encerramento, o prazo absoluto é `started_at + 300 s`. A contagem extra é a partir do **primeiro** sinal e **não reinicia** se a IA continuar falando.

### 5.3 Condições exatas

| Condição | Comportamento |
|---|---|
| Todos os 7 essenciais estão `confirmed` ou `unknown` | Solicitar encerramento antecipado imediatamente. |
| Todos resolvidos, mas existem `uncertain` | Realizar até **uma** confirmação breve consolidada; em seguida solicitar encerramento, mesmo se persistir incerteza. |
| Faltam itens essenciais e tempo < 180 s | Priorizar uma lacuna por vez; nenhuma ordem fixa de perguntas. |
| Tempo >= 180 s | `requestClose('time_limit')`, bloquear novas explorações, concluir naturalmente. |
| Pessoa diz “não sei” | Marcar `unknown`, não repetir a pergunta. |
| Pessoa pede para sair | `requestClose('user_request')`; despedida curta se possível; não prolongar. |
| IA chama a ferramenta de conclusão | Validar se conclusão está autorizada; se sim, retornar autorização. |
| IA conclui e a **fila de áudio de despedida terminou** | Persistir, encerrar e navegar. |
| Agora >= `hard_deadline` | Encerramento forçado; interromper áudio/conexão, preservar dados e registrar motivo verdadeiro. |
| Falha de rede/API após início | Salvar imediatamente os dados extraídos; permitir modo texto ou encerrar como parcial. |

`unknown` significa resposta explicitamente impossível/não fornecida pelo usuário, não “foi ignorado pelo modelo”; item `pending` impede encerramento por completude, mas **nunca** impede encerramento por tempo.

### 5.4 Sinal de encerramento: contrato INTERNO Agrion

O evento abaixo é **do aplicativo Agrion**, não um evento nativo da API Gemini:

```json
{
  "type": "AGRION_CLOSE_REQUEST",
  "interview_id": "uuid-da-entrevista",
  "reason": "time_limit",
  "elapsed_ms": 180000,
  "pending_fields": ["previous_crop"],
  "uncertain_fields": ["last_harvest_result"],
  "instructions": "Não abra novos assuntos. Conclua e agradeça brevemente."
}
```

Processamento:

1. `InterviewController` emite `AGRION_CLOSE_REQUEST` uma única vez e grava `closingRequestedAt`.
2. `LiveConversationManager` o converte em uma **atualização textual de contexto compatível** com a versão da Gemini Live. Preferir enviar quando o agricultor concluir a fala atual, sem cortar uma frase em andamento. **Não** usar `sendClientContent({turnComplete:true})` durante geração: isso pode interromper a saída. Para `gemini-3.8-live`, é possível usar atualizações textuais/cliente da sessão conforme documentação; validar comportamento real. **Não inventar comando `updateSystemInstruction()` inexistente**.
3. Caso não haja resposta do modelo em ~20 s, reenviar **no máximo uma** instrução de encerramento durante pausa; não repetir em loop.
4. `complete_initial_interview` sinaliza que o modelo está pronto; o aplicativo autoriza a despedida quando a condição de fechamento for válida.
5. Esperar o final do turno de despedida **e** a fila de áudio local esvaziar; `turnComplete` sozinho não garante que o som já terminou no navegador.
6. Se atingir `hard_deadline`, interromper e finalizar. Exibir na UI um encerramento neutro se não houve despedida falada.

### 5.5 Tool de conclusão

Disponibilizar à sessão Live uma declaração de função chamada exatamente:

`complete_initial_interview`

Argumentos esperados:

```json
{
  "reason": "essential_fields_complete",
  "short_summary": "Última cultura milho; produção prejudicada por falta de chuva."
}
```

**Valores permitidos para `reason`:** `essential_fields_complete`, `time_limit`, `user_request`, `uncertainties_reviewed`.

**Resposta da aplicação à chamada:**

```json
{
  "accepted": true,
  "next_action": "say_short_farewell",
  "message": "Agradeça de forma breve e informe que o usuário pode conversar pelo ícone Agrion."
}
```

Se a IA pedir conclusão cedo demais e ainda houver pendências sem prazo expirado, responder:

```json
{
  "accepted": false,
  "next_action": "ask_one_missing_essential_question",
  "missing_fields": ["irrigation", "primary_goal"]
}
```

**Importante:** function calling da Live exige responder à chamada com a resposta da ferramenta; não confundir com endpoint HTTP Flask. Trata-se de função local do cliente. Para a simplicidade desta fase, usar execução **bloqueante/síncrona** dessa ferramenta, quando configurável. Não depender dela para o corte de segurança aos 5 minutos.

### 5.6 Ferramenta opcional de estado, recomendada

`get_interview_state` — sem argumentos, devolve `{elapsed_seconds, essential_fields, pending_fields, uncertain_fields, close_requested}`. O modelo pode chamá-la para identificar lacunas. O aplicativo pode também fornecer uma atualização textual curta de estado **entre turnos** depois de extrações relevantes. Não mandar o JSON inteiro a cada segundo.

### 5.7 Implementação de referência — controlador (pseudocódigo)

```js
function tick(now) {
  if (isTerminal(interview.status)) return;

  const elapsed = now - interview.monotonicStartedAt;
  const graceExceeded = interview.firstCloseAt !== null &&
    now - interview.firstCloseAt >= CLOSING_GRACE_MS;

  if (elapsed >= ABSOLUTE_SESSION_LIMIT_MS || graceExceeded) {
    forceFinalize('safety_timeout');
    return;
  }

  if (interview.status === 'ACTIVE') {
    if (allEssentialResolved() && !needsOneTimeConfirmation()) {
      requestClose('essential_fields_complete');
    } else if (elapsed >= NORMAL_LIMIT_MS) {
      requestClose('time_limit');
    }
  }
}

function requestClose(reason) {
  if (interview.firstCloseAt !== null) return; // idempotente
  interview.firstCloseAt = performance.now();
  interview.status = 'CLOSING_REQUESTED';
  persistSessionCheckpoint();
  liveManager.queueCloseSignalAtSafeBoundary(reason);
}
```

O `tick` pode ser chamado por um temporizador de 200–500 ms **e** em eventos relevantes (mudança de estado, nova extração, fim de turno). `setInterval` pode atrasar quando a aba estiver em segundo plano: ao retomar foco, recalcular imediatamente pelo relógio monotônico e finalizar se houver vencimento.

---

## 6. CONTRATO C — Dados agrícolas e significados

### 6.1 Quatro estados de campo

| Estado | Significado | `value` |
|---|---|---|
| `pending` | Não houve resposta suficiente | `null` |
| `confirmed` | Declaração clara **do agricultor**, ou correção explícita | Valor normalizado; pode representar `none` de forma explícita |
| `uncertain` | Estimativa, ambiguidade, conflito ou resposta parcial | Valor possível ou `null`, com evidência |
| `unknown` | Pessoa expressamente não sabe/não lembra/não deseja informar | `null`, com motivo e evidência |

**`confirmed` não significa dado medido, auditado, ou comprovado cientificamente.** Significa apenas que o relato foi claro. A proveniência continua `farmer_report`.

### 6.2 Envelope padronizado para TODOS os campos

Cada campo `fields.<field_id>` usa exatamente este contrato lógico:

```json
{
  "value": null,
  "status": "pending",
  "source": "farmer_report",
  "evidence": [],
  "confidence": null,
  "unknown_reason": null,
  "updated_at": null,
  "revision": 0
}
```

- `value`: formato específico por campo, descrito abaixo.
- `status`: enum acima.
- `source`: `farmer_report`, `user_edit` ou `existing_profile` (não inventar origem NASA).
- `evidence`: array de `{turn_id, excerpt}`; guardar trecho **estritamente necessário**, não transcrição integral por padrão.
- `confidence`: `high`, `medium`, `low` ou `null`; indicação da qualidade da extração, **não** probabilidade agronômica.
- `unknown_reason`: `does_not_know`, `does_not_remember`, `declined` ou `null`.
- `updated_at`: timestamp UTC ISO 8601.
- `revision`: número inteiro incremental por campo.

### 6.3 Tipos aceitos para `value` por item

**`last_crop` e `previous_crop`:**

```json
{ "crop": "milho", "period_label": "2025/26", "no_previous_cultivation": false }
```

- `crop`: nome popular normalizado em pt-BR, preservar termo original se for ambíguo.
- `period_label`: opcional (ex.: “safra passada”, “2025/26”), **não inventar ano**.
- No campo `previous_crop`, se o agricultor disser que nunca houve plantio anterior: `crop: null`, `no_previous_cultivation: true`, `status: confirmed`.
- A cultura anterior significa **imediatamente antes da última cultura**, não outra cultura qualquer da propriedade.

**`last_harvest_result`:**

```json
{
  "crop": "milho",
  "quantity": 80,
  "unit": "sacas/ha",
  "bag_weight_kg": null,
  "qualitative_result": "poor",
  "notes": "perda por falta de chuva"
}
```

- `quantity` e `unit` podem ser `null` se a pessoa só disser “rendeu pouco”.
- `qualitative_result`: `good`, `average`, `poor`, `no_harvest` ou `null`.
- Não converter saca para kg sem saber o peso aplicável; não transformar “80 sacas” em “80 sacas/ha” sem unidade explicitamente dita.
- Não comparar produtividade entre culturas distintas sem normalização posterior.

**`main_difficulties`:**

```json
{
  "categories": ["drought"],
  "free_text": ["faltou chuva no período de enchimento de grãos"],
  "explicit_none": false
}
```

Categorias permitidas: `drought`, `excess_rain`, `pests`, `diseases`, `soil`, `input_costs`, `labor`, `machinery`, `market`, `other`. Se “não tive dificuldades”, usar lista vazia, `explicit_none: true`, `confirmed`.

**`irrigation`:**

```json
{
  "water_regime": "rainfed",
  "irrigation_method": "none",
  "automated": false,
  "notes": null
}
```

`water_regime`: `rainfed`, `irrigated`, `mixed`, `unknown`.  
`irrigation_method`: `none`, `manual`, `drip`, `sprinkler`, `center_pivot`, `furrow`, `other`, `unknown`.  
`automated`: `true`, `false` ou `null` (não inferir ausência de automação se não mencionada, exceto quando afirma não possuir irrigação).

**`mechanization`:**

```json
{
  "work_mode": "mixed",
  "equipment": ["trator pequeno"],
  "automation_level": "unknown",
  "notes": null
}
```

`work_mode`: `manual`, `mixed`, `mechanized`, `automated`, `unknown`; `automation_level`: `none`, `partial`, `high`, `unknown`. Preservar nomes específicos de equipamentos em `equipment`.

**`primary_goal`:**

```json
{
  "category": "reduce_risk",
  "description": "não perder outra safra por falta de chuva"
}
```

Categorias: `maximize_profit`, `increase_yield`, `restore_soil`, `reduce_risk`, `reduce_costs`, `diversify`, `other`.

**Complementares** em `additional_fields`: `fertilization`, `soil_management`, `cover_crops`, `other_crops`, `water_access`, `budget_constraints`, `technical_resources`. Usar o mesmo envelope; não incluir na regra de completude.

### 6.4 Documento final do perfil — estrutura canônica

```json
{
  "schema_version": "1.0.0",
  "profile_id": "uuid-perfil",
  "property_id": "id-real-gerado-pelo-cadastro-de-terreno",
  "person": { "display_name": "João" },
  "property": {
    "name": "Sítio Boa Vista",
    "area_hectares": 12.4,
    "geometry_source": "existing_property_registration"
  },
  "fields": {
    "last_crop": {
      "value": { "crop": "milho", "period_label": "ano passado", "no_previous_cultivation": false },
      "status": "confirmed",
      "source": "farmer_report",
      "evidence": [{ "turn_id": "t001", "excerpt": "ano passado plantei milho" }],
      "confidence": "high",
      "unknown_reason": null,
      "updated_at": "2026-11-14T20:00:35Z",
      "revision": 1
    },
    "previous_crop": {
      "value": null,
      "status": "pending",
      "source": "farmer_report",
      "evidence": [],
      "confidence": null,
      "unknown_reason": null,
      "updated_at": null,
      "revision": 0
    },
    "last_harvest_result": {
      "value": {
        "crop": "milho", "quantity": 80, "unit": "sacas/ha",
        "bag_weight_kg": null, "qualitative_result": "poor",
        "notes": "estimativa; safra prejudicada pela seca"
      },
      "status": "uncertain",
      "source": "farmer_report",
      "evidence": [{ "turn_id": "t001", "excerpt": "acho que foram umas 80 sacas por hectare" }],
      "confidence": "medium",
      "unknown_reason": null,
      "updated_at": "2026-11-14T20:00:35Z",
      "revision": 1
    },
    "main_difficulties": {
      "value": { "categories": ["drought"], "free_text": ["faltou chuva"], "explicit_none": false },
      "status": "confirmed", "source": "farmer_report",
      "evidence": [{ "turn_id": "t001", "excerpt": "faltou chuva" }],
      "confidence": "high", "unknown_reason": null,
      "updated_at": "2026-11-14T20:00:35Z", "revision": 1
    },
    "irrigation": {
      "value": { "water_regime": "rainfed", "irrigation_method": "none", "automated": false, "notes": null },
      "status": "confirmed", "source": "farmer_report",
      "evidence": [{ "turn_id": "t001", "excerpt": "não tenho irrigação" }],
      "confidence": "high", "unknown_reason": null,
      "updated_at": "2026-11-14T20:00:35Z", "revision": 1
    },
    "mechanization": {
      "value": { "work_mode": "unknown", "equipment": ["trator pequeno"], "automation_level": "unknown", "notes": null },
      "status": "uncertain", "source": "farmer_report",
      "evidence": [{ "turn_id": "t001", "excerpt": "tenho um trator pequeno" }],
      "confidence": "medium", "unknown_reason": null,
      "updated_at": "2026-11-14T20:00:35Z", "revision": 1
    },
    "primary_goal": {
      "value": null, "status": "pending", "source": "farmer_report", "evidence": [],
      "confidence": null, "unknown_reason": null, "updated_at": null, "revision": 0
    }
  },
  "additional_fields": {},
  "interview_history": ["uuid-entrevista"],
  "updated_at": "2026-11-14T20:00:35Z"
}
```

**Observação sobre o exemplo:** `mechanization` está **incerto**, porque dizer “tenho um trator” não demonstra por si só que o manejo é misto; a IA deve preservar equipamento conhecido e evitar inferir regime de trabalho. O exemplo é ilustrativo, não um perfil real.

### 6.5 Contrato de entrevista / auditoria

```json
{
  "schema_version": "1.0.0",
  "interview_id": "uuid-entrevista",
  "profile_id": "uuid-perfil",
  "property_id": "uuid-propriedade",
  "status": "completed",
  "mode": "voice",
  "started_at": "2026-11-14T20:00:00Z",
  "closing_requested_at": "2026-11-14T20:02:20Z",
  "finished_at": "2026-11-14T20:02:34Z",
  "duration_seconds": 154,
  "completion_reason": "essential_fields_complete",
  "farewell_delivered": true,
  "confirmation_attempted": true,
  "essential_field_counts": {
    "confirmed": 5, "uncertain": 1, "unknown": 1, "pending": 0
  },
  "processed_turn_ids": ["t001", "t002", "t003"],
  "pending_extraction_turn_ids": [],
  "errors": []
}
```

- `status`: `in_progress`, `completed`, `partial`, `cancelled`, `technical_error`.
- `completion_reason`: `essential_fields_complete`, `uncertainties_reviewed`, `time_limit`, `user_request`, `safety_timeout`, `technical_error`.
- `farewell_delivered`: só é `true` quando o áudio/texto da despedida realmente foi concluído.
- `mode`: `voice`, `text` ou `mixed`.
- Não marcar sessão interrompida abruptamente como `completed`.
- Adicionar `created_at` e `updated_at` reais à implementação, mesmo quando omitidos dos exemplos.

---

## 7. CONTRATO D — Extração estruturada independente

### 7.1 Princípio

**Gemini Live conversa; um modelo textual separado extrai; o aplicativo valida e persiste.** A extração não é pergunta nem fala do assistente. O checklist reflete **dados validados**, jamais hipóteses de transcrição parcial.

### 7.2 Fronteira de turno e deduplicação

- Receber eventos Live de `inputTranscription` e concatenar fragmentos referentes à fala do agricultor.
- **Não** assumir que cada evento recebido é uma fala completa nem que todos chegam como um único objeto.
- Consolidar fala usando eventos de atividade/limite de turno e a referência oficial do protocolo. Se ainda houver ambiguidade, aguardar estabilização do texto antes de mandar para extração.
- Atribuir `turn_id` único e `sequence` crescente para cada fala **finalizada**.
- Somente finalizar a transcrição de fato depois de obter uma fronteira confiável; evitar transmitir frases cortadas.
- Enviar para extração **uma vez por turno**, com fila sequencial. Mudanças não podem chegar fora da ordem.
- Fala corrigida gera novo turno/revisão, não sobrescreve sem histórico.
- Texto digitado também gera `turn_id` e passa pela mesma rotina.

### 7.3 Endpoint Flask de extração

`POST /api/interview/extract` — `application/json`

**Request:**

```json
{
  "interview_id": "uuid-entrevista",
  "property_id": "uuid-propriedade",
  "turn_id": "t003",
  "sequence": 3,
  "speaker": "farmer",
  "transcript": "Ano passado plantei milho, não tenho irrigação e tenho um trator pequeno.",
  "profile_revision": 2,
  "profile_snapshot": {
    "fields": {
      "last_crop": { "status": "pending", "value": null },
      "irrigation": { "status": "pending", "value": null }
    }
  }
}
```

**Response:**

```json
{
  "interview_id": "uuid-entrevista",
  "turn_id": "t003",
  "sequence": 3,
  "base_profile_revision": 2,
  "patches": [
    {
      "field": "last_crop",
      "operation": "set",
      "value": { "crop": "milho", "period_label": "ano passado", "no_previous_cultivation": false },
      "status": "confirmed",
      "confidence": "high",
      "evidence_excerpt": "ano passado plantei milho"
    },
    {
      "field": "irrigation",
      "operation": "set",
      "value": { "water_regime": "rainfed", "irrigation_method": "none", "automated": false, "notes": null },
      "status": "confirmed",
      "confidence": "high",
      "evidence_excerpt": "não tenho irrigação"
    },
    {
      "field": "mechanization",
      "operation": "merge",
      "value": { "equipment": ["trator pequeno"] },
      "status": "uncertain",
      "confidence": "medium",
      "evidence_excerpt": "tenho um trator pequeno"
    }
  ],
  "warnings": []
}
```

**Observação:** payloads de exemplo são parciais para legibilidade; o **servidor** deve validar e normalizar os patches contra os tipos integrais do contrato B/C. O extrator não define diretamente IDs de proprietário nem timestamps.

### 7.4 Regras do extrator

1. Extrair apenas fatos **explicitamente sustentados pelo turno** e pelo contexto enviado.
2. Permitir **0 a N patches** em uma fala.
3. Evidências devem ser substrings literais ou trechos fiéis da fala enviada.
4. Detectar negativa e incerteza: “não tenho irrigação”, “acho que”, “talvez”, “não lembro”.
5. Não transformar `null` em `false` automaticamente.
6. Não inferir “automação nenhuma” de “tenho trator”.
7. Se houver conflito, devolver `uncertain` e aviso; uma correção explícita prevalece após validação.
8. Não editar localização, polígono e área calculada — pertencem ao cadastro geográfico.
9. Não normalizar datas relativas para anos civis sem referência temporal inequívoca.
10. Não inventar unidade de produtividade, peso de saca, hectares nem retorno financeiro.
11. Não fazer recomendações ou completar lacunas com conhecimento geral.
12. Se a fala não contém informação agrícola relevante, retornar `patches: []`.

### 7.5 Prompt do extrator — pronto para uso

```text
Você é um EXTRATOR DE FATOS AGRÍCOLAS, não um chatbot.
Entrada: uma fala finalizada do agricultor e um resumo do perfil prévio.
Saída: APENAS objeto JSON no esquema solicitado, com zero ou mais patches.

Extraia somente informações explicitamente respaldadas pela fala.
Uma mesma fala pode atualizar vários campos.
Preserve a distinção entre última cultura e a cultura IMEDIATAMENTE ANTERIOR.
"Acho", "mais ou menos" e valores aproximados implicam status uncertain.
"Não sei", "não lembro", "prefiro não responder" implicam unknown, value null.
Não confunda ausência de informação com negação.
Declaração clara de fato relatado implica confirmed, mas NÃO implica medição validada.
Não invente unidade, peso de saca, produtividade, ano, equipamento ou prática de manejo.
Se houver ambiguidade/conflito, devolva uncertain e warnings.
Não altere geometria ou dados cadastrais da propriedade.
Cada patch DEVE conter uma evidência textual presente na fala.
Se não houver novo fato, patches deve ser uma lista vazia.
Não emita texto fora do esquema JSON.
```

**Backend Python:** usar `google-genai` e **saída estruturada** por esquema/Pydantic, com validação Pydantic **após** a geração. O esquema exposto à IA deve ser simples (`field`, `operation`, `value`, `status`, `confidence`, `evidence_excerpt`, `warnings`); a validação detalhada de cada `value` é responsabilidade do Flask, pois esquemas polimórficos profundos podem ser mal suportados.

### 7.6 Mesclagem de dados

- Aplicar patches em sequência de `sequence`/`turn_id`, um de cada vez.
- Exigir `base_profile_revision` atual; se divergente, reprocessar com snapshot atualizado ou descartar a proposta antiga de forma explícita.
- `set`: substitui valor quando veio uma correção explícita ou campo estava `pending`/`unknown`.
- `merge`: agrega campos conhecidos sem destruir informações anteriormente válidas.
- Nunca rebaixar `confirmed` para `pending`.
- Nunca rebaixar `confirmed` para `uncertain` sem nova evidência de conflito ou correção.
- Repetição idêntica (`turn_id` duplicado) é **idempotente**: não incrementar revisão duas vezes.
- Guardar revisão anterior mínima para auditoria, sem acumular transcrição integral indiscriminadamente.
- Se duas falas conflitarem, solicitar esclarecimento uma vez se houver tempo; depois preservar `uncertain` e as evidências.

### 7.7 Quando a extração falha

- Não inventar atualização para preencher o checklist.
- Guardar o turno de texto como `pending_extraction` **apenas com consentimento para persistência de transcrição**, para tentar novamente na próxima abertura.
- Mostrar marcação normal somente depois de validação.
- Não bloquear a despedida por falha externa.
- Ao finalizar, tentar drenar extrações pendentes por curto período sem ultrapassar o prazo absoluto; caso contrário preservar a fila local.
- Não alegar que tudo foi salvo se o armazenamento falhar: mostrar erro e oferecer exportar o JSON localmente.

---

## 8. CONTRATO E — API Flask

### 8.1 Rotas

| Método e rota | Função |
|---|---|
| `POST /api/interview/live-token` | Emitir token efêmero para a sessão Live. |
| `POST /api/interview/extract` | Extrair patches estruturados de um turno finalizado. |
| `GET /api/health` | Continuar funcionando, sem mudanças de contrato. |

Nenhum endpoint de login, upload de áudio ou gravação de perfil no servidor nesta fase.

### 8.2 `/api/interview/live-token`

**Request:**

```json
{ "interview_id": "uuid-entrevista", "property_id": "uuid-propriedade" }
```

**Response 200:**

```json
{
  "token": "token-efemero-emitido-pelo-google",
  "model": "gemini-3.8-live",
  "api_version": "v1beta",
  "expires_at": "2026-11-14T20:10:00Z"
}
```

`expires_at` deve refletir **a validade real** do token retornado pelo provedor, nunca horário inventado.

Regras:

- `GEMINI_API_KEY` lida **exclusivamente** do ambiente da VM.
- Gerar token efêmero via API oficial Google; resposta `Cache-Control: no-store`.
- Usar `uses=1`, curta janela de abertura e configurações restritas ao modelo/modalidade, conforme suporte do provedor.
- Exigir POST + JSON válido, tamanho máximo de body e validar IDs UUID.
- Validar origem e aplicar proteção contra abuso **sem bloquear avaliadores por falta de login**.
- Não retornar chave permanente, prompt completo ou dados de outras pessoas.
- Não registrar token ou transcrições nos logs.
- `429` se excesso de requisições; `503` se indisponibilidade do provedor/configuração.
- Uma chave/cota Google ainda pode ser consumida por visitantes: monitorar uso e definir alertas/limites de faturamento, quando disponíveis.

### 8.3 `/api/interview/extract`

- Validar tamanho máximo do texto (p. ex., **3.000 caracteres/turno**), `speaker=farmer`, UUIDs, `sequence` e limite de campos aceitos.
- Receber apenas a fala necessária e o snapshot mínimo do perfil, sem dados supérfluos.
- Chamadas do modelo textual Gemini são **server-side**.
- Retornar patches tipados; remover qualquer campo desconhecido.
- Responder `422` para entrada inválida; `429` para excesso; `502/503` para falha do provedor; jamais retornar traceback.
- Em toda saída, controlar `Cache-Control: no-store`.
- Não fazer `print()` de transcrições ou respostas completas em logs de produção.

### 8.4 Proteção mínima contra abuso

- Rate limit por IP validado, com proxy confiável configurado (não confiar indiscriminadamente em `X-Forwarded-For`). Como referência inicial de MVP: **8 tokens Live/hora/IP** e **120 chamadas de extração/hora/IP**, configuráveis em ambiente.
- Um dispositivo/aba com uma sessão ativa por vez.
- Sem Redis, um rate limiter apenas em memória por processo tem limitação entre workers; documentar e, se necessário, aplicar limite no provedor ou gateway. **Não vender isso como proteção perfeita.**
- Restringir modelo e recursos emitidos pelo token; conferir no Google AI Studio limites, cotas e faturamento antes do pitch.
- Sanitizar o conteúdo apresentado no HTML; transcrições são dados não confiáveis, nunca interpolar via `innerHTML`.

### 8.5 Variáveis de ambiente

Acrescentar ao `.env.example`, sem valores secretos:

```dotenv
GEMINI_API_KEY=
GEMINI_LIVE_MODEL=gemini-3.8-live
GEMINI_EXTRACTION_MODEL=gemini-3.5-flash-lite
AGRION_INTERVIEW_NORMAL_SECONDS=180
AGRION_INTERVIEW_GRACE_SECONDS=120
AGRION_INTERVIEW_ABSOLUTE_SECONDS=300
AGRION_LIVE_TOKENS_PER_HOUR=8
AGRION_EXTRACTIONS_PER_HOUR=120
```

As variáveis de duração devem ser lidas com validação; **os valores de produção desta versão são 180/120/300**. Não habilitar tela de configuração livre para o usuário final.

---

## 9. CONTRATO F — Persistência local e integração futura

### 9.1 Armazenamento obrigatório

Usar **IndexedDB**, preferencialmente aproveitando o padrão atual da aplicação. Não migrar o site para banco de dados remoto agora. O navegador deve manter os dados após reload e fechamento da aba, na mesma origem, salvo limpeza de armazenamento do usuário.

Banco lógico sugerido: `agrion-db` (versão 1 ou migrar versão já existente, se houver). Stores:

| Store | Chave | Conteúdo |
|---|---|---|
| `agricultural_profiles` | `property_id` | Perfil agrícola normalizado e versionado. |
| `interviews` | `interview_id` | Estado/duração/resultado/motivo e contadores. |
| `interview_revisions` | `revision_id` | Histórico mínimo de patches e valores anteriores. |
| `pending_extractions` | `turn_id` | Turnos pendentes quando a extração falhar, conforme consentimento. |

O cadastro geográfico existente permanece **fonte de verdade** de nome, localização, geometria GeoJSON e área em hectares. Associar com o `property_id` real, sem duplicar uma geometria obsoleta no perfil. Se a implementação existente não tiver ID da propriedade, acrescentar um UUID estável de forma não destrutiva.

### 9.2 Escrita segura

- Gravar cada atualização válida assim que recebida, usando transação IndexedDB.
- Persistir checkpoints de sessão e mudança de status (não depender só do evento `beforeunload`).
- Aplicar validação básica também ao carregar os dados.
- Preservar os dados existentes do Agrion, inclusive registro de propriedade e informações do protótipo.
- Nunca fazer `localStorage.clear()` como parte do fluxo.
- Não eliminar informações agrícolas por mudança visual de tela.
- Não prometer sincronização multiusuário/multidispositivo nesta versão.

### 9.3 Contrato para uso futuro nas análises

Criar módulo de consulta interno, por exemplo:

```js
const profile = await profileRepository.getByPropertyId(propertyId);
const analysisInput = buildAgriculturalAnalysisInput(profile, propertyGeometry);
```

`buildAgriculturalAnalysisInput` deverá devolver:

```json
{
  "schema_version": "1.0.0",
  "property_id": "uuid-propriedade",
  "geometry": { "type": "Polygon", "coordinates": [] },
  "area_hectares": 12.4,
  "agricultural_profile": { "last_crop": {}, "irrigation": {} },
  "data_quality": {
    "pending_fields": [],
    "uncertain_fields": ["last_harvest_result"],
    "unknown_fields": []
  }
}
```

O exemplo acima demonstra apenas a forma do contrato; retornar **geometria real** e campos completos, sem arrays fictícios. Futuras APIs de análise consumirão valores **e** estados de qualidade, nunca assumindo que tudo é certo.

---

## 10. Implementação frontend — módulos e eventos

Manter nomes existentes se já houver responsabilidades equivalentes. Estrutura conceitual mínima:

```text
app/static/js/agrion-discovery/
  discovery-entry.js           # integração com rotas/telas existentes
  live-conversation-manager.js # WebSocket Live, VAD, áudio e transcrições
  pcm-audio-worklet.js         # captura e PCM
  audio-output-queue.js        # áudio 24 kHz, flush em interrupção
  interview-controller.js     # relógios e máquina de estados
  transcript-assembler.js     # transforma fragments em turnos finalizados
  agricultural-profile.js     # estados/normalização/validação de patches
  profile-repository.js       # IndexedDB
  interview-checklist.js      # renderização da tela
  interview-api-client.js     # endpoints Flask
  interview-ui.js             # convite, voz, texto, conclusão
```

O nome dos arquivos pode ser ajustado à organização existente, **sem mesclar tudo em um único arquivo monolítico**.

### 10.1 Eventos internos de aplicação (não Gemini)

```text
INTERVIEW_STARTED
LIVE_CONNECTED
MIC_PERMISSION_DENIED
USER_UTTERANCE_FINALIZED
PROFILE_PATCHES_VALIDATED
CHECKLIST_UPDATED
VOICE_INTERRUPTED
CLOSE_REQUESTED
FAREWELL_STARTED
FAREWELL_PLAYBACK_FINISHED
INTERVIEW_FINALIZED
INTERVIEW_FAILED
```

- `USER_UTTERANCE_FINALIZED`: fornece `interview_id`, `turn_id`, `sequence`, `transcript`.
- `PROFILE_PATCHES_VALIDATED`: dispara persistência e cálculo de completude.
- `CLOSE_REQUESTED`: idempotente, com timestamp único e motivo.
- `FAREWELL_PLAYBACK_FINISHED`: só depois da reprodução local de **todos** os chunks correspondentes à despedida.
- `INTERVIEW_FINALIZED`: carrega estado salvo na tela de propriedade, sem reiniciar onboarding.

### 10.2 Interrupções (*barge-in*)

Quando o provedor sinalizar `serverContent.interrupted`:

1. Parar reprodução em andamento.
2. Esvaziar a fila de chunks ainda não tocados.
3. Cancelar a legenda incremental da fala da IA ainda não efetivamente emitida.
4. Deixar o microfone/entrada ativa; escutar o agricultor.
5. Não considerar o texto de resposta interrompida como confirmação do usuário.

### 10.3 Dupla finalização

Somente **uma** função `finalizeInterview(reason)` pode executar, protegida por flag/promessa única. Tool call, botão do usuário, timeout, socket `onclose` e `beforeunload` podem competir; nenhuma dessas rotas pode apagar dados ou abrir várias telas finais.

### 10.4 Mudança de aba e sono do dispositivo

Se a página entrar em segundo plano, não confiar em ticks regulares. Reavaliar deadlines em `visibilitychange`, `pageshow` e no próximo evento da sessão. Microfone interrompido pelo SO deve produzir mensagem de erro e opção de continuar por texto. Persistir estado parcial.

---

## 11. Estratégia para demonstração em 5 minutos

A funcionalidade tem de funcionar de verdade, **sem respostas gravadas ou dados falsos**. Um demonstrador pode escolher previamente uma propriedade já cadastrada e entrar diretamente na entrevista, evitando gastar tempo redesenhando terreno durante a apresentação.

**Exemplo de diálogo demonstrável, não roteiro forçado:**

**Agrion:** “Olá, João! Eu sou o Agrion... O que você plantou por último?”

**Agricultor:** “Foi milho. Antes teve soja. Colhi perto de 80 sacas por hectare, mas a seca prejudicou. Não tenho irrigação e uso um trator pequeno. Quero ganhar mais sem arriscar tanto.”

**Checklist após a fala:**

- Última cultura: milho (`confirmed`)
- Cultura anterior: soja (`confirmed`)
- Produtividade: aproximadamente 80 sacas/ha (`uncertain`)
- Dificuldade: seca (`confirmed`)
- Irrigação: dependência da chuva (`confirmed`)
- Equipamento: trator pequeno (`confirmed` como equipamento relatado; regime de mecanização ainda `uncertain`)
- Objetivo: reduzir risco / melhorar retorno (`confirmed` ou `uncertain`, conforme interpretação fiel)

A IA pode pedir apenas esclarecimento sobre o trabalho manual/mecanizado e, havendo tempo, confirmar rapidamente a estimativa. Depois agradece, salva e abre resumo. **Não prolongar artificialmente** até 3 minutos.

---

## 12. Regras de consentimento, segurança e comunicação

- Informar **antes da primeira captura** que a voz/transcrição será transmitida a serviço de IA do Google para processar a entrevista; explicar que Agrion **não grava o áudio bruto**.
- Pedir consentimento explícito para começar a conversa por voz; permissão de microfone do navegador é uma ação separada.
- Permitir modo texto sem microfone; mantém as mesmas perguntas, extração e JSON.
- Guardar somente dados necessários ao perfil e evidências curtas; transcrição integral persistente é opcional e **desativada por padrão**.
- Minimizar dados pessoais: já temos o primeiro nome; não pedir telefone, documentos, e-mail ou localização adicional.
- Não inserir dados privados em logs nem em URL query strings.
- Não passar a chave permanente da API ao navegador.
- Proteger tokens e endpoints contra abuso; configurar monitoramento de custos/cotas no provedor.
- Se a IA gerar orientação agronômica fora de escopo, instruí-la a dizer que primeiro precisa analisar dados e que recomendações virão em etapa posterior.

---

## 13. Falhas previsíveis e tratamento obrigatório

| Cenário | Comportamento obrigatório |
|---|---|
| Microfone negado | Explicar e oferecer **Continuar por texto**. |
| Navegador não suporta captura PCM | Oferecer modo texto; não afirmar suporte de voz. |
| Token Live não emitido | Mostrar erro claro, manter cadastro, oferecer tentar novamente ou texto. |
| WebSocket cai | Persistir perfil, tentar **uma** reconexão com retomada de sessão se suportada; caso falhe, oferecer continuar por texto/encerrar parcial. |
| IA interrompida pelo agricultor | Limpar áudio local e escutar; sem duplicar resposta. |
| Extração lenta | Continuar áudio; atualização do checklist pode atrasar poucos segundos. |
| Extração devolve JSON inválido | Rejeitar patch, registrar erro técnico, não inventar check. |
| Resposta contraditória | Sinalizar `uncertain` e pedir esclarecimento no máximo uma vez. |
| Usuário não sabe responder | `unknown`, sem insistência. |
| Navegador fecha | Checkpoint salva o que foi validado; reabrir oferece retomar/avançar. |
| Encerrou por completude em 40s | Agradecer e finalizar sem esperar relógio. |
| Passou de 3min | Sinal de fechamento; concluir na próxima pausa sem cortar fala. |
| Passou de 5min ou 2min do pedido de fechamento | Forçar finalização, registrar `safety_timeout`, preservar dados. |
| Sem armazenamento disponível | Avisar e oferecer **Exportar perfil em JSON**, sem alegar gravação bem-sucedida. |
| Reabrir após perfil completo | Não perguntar de novo; acessível pelo ícone flutuante. |

Para uma entrevista curta de até 5 minutos, normalmente não precisamos de reconexão periódica: a documentação atual indica conexão Live com vida aproximada de 10 minutos. Ainda assim, suportar **tratamento de quedas** e retomada quando compatível; não ampliar a duração da entrevista para aproveitar a conexão.

---

## 14. Testes automatizados e de integração — critérios de aceite

### 14.1 Unitários obrigatórios

1. **Sete campos:** criação inicial com todos `pending`.
2. **Múltiplos fatos numa fala:** uma resposta gera cinco ou mais patches compatíveis.
3. **Incerteza:** “acho que foram 80 sacas/ha” → `uncertain`.
4. **Negação:** “não tenho irrigação” → `rainfed/none`, não `unknown`.
5. **Desconhecimento:** “não lembro o que plantei antes” → `unknown`, sem repetições.
6. **Sem cultivo anterior:** “nunca plantei aqui antes” → `previous_crop.confirmed`, `no_previous_cultivation=true`.
7. **Unidades:** “80 sacas” não vira “80 sacas/ha”; kg não inventado.
8. **Conflitos:** informação posterior contraditória → revisão controlada / `uncertain`.
9. **Idempotência:** `turn_id` duplicado não aplica patch duas vezes.
10. **Sequenciamento:** respostas fora de ordem não sobrescrevem revisão nova.
11. **Completude:** todos resolvidos → encerrar cedo, mesmo com `unknown`.
12. **Incertezas finais:** só uma confirmação e concluir, ainda que não seja esclarecida.
13. **Timer:** 179s ativo; 180s fecha naturalmente; 300s força.
14. **Pedido antecipado:** grace de 120s conta do primeiro pedido, não reinicia.
15. **Duplo evento:** timeout + tool + botão encerram somente uma vez.
16. **Persistência:** reload mantém perfil, status e georreferência.
17. **Sem chave:** endpoints retornam erro claro, não `200` fictício.
18. **Validação backend:** rejeita campos e enums desconhecidos.
19. **Segurança:** nenhum token permanente aparece em HTML/JS/JSON público/log.
20. **Health:** `GET /api/health` continua 200 no ambiente configurado.

### 14.2 Integração real obrigatória

- Testar **com chamada real** à Gemini Live, não somente mocks.
- Testar autorização de microfone e fala pt-BR.
- Testar transcrição do agricultor e áudio gerado pelo Agrion.
- Interromper a IA no meio da fala e observar ausência de áudio antigo na fila.
- Verificar atualização do checklist após fala com vários fatos.
- Verificar chamada `complete_initial_interview` e despedida completa.
- Forçar timeout de forma controlada em teste (configuração de teste, sem mudar os valores de produção).
- Confirmar que os dados JSON podem ser recuperados após recarregar a página.
- Testar viewport 390px, 768px e 1440px.
- Testar no domínio HTTPS real após deploy manual, se a chave estiver configurada.

### 14.3 Requisitos de qualidade

- Sem loops repetitivos de pergunta.
- Sem mais de uma pergunta nova por turno da IA.
- Sem falsa confirmação por dedução.
- Sem congelar animações/controles enquanto extrai JSON.
- Sem aparecer `undefined`, `null` cru ou JSON ao agricultor.
- Sem nova dependência de login ou banco remoto.
- Sem reinicializar o mapa ou apagar polígono.
- Sem vazamento de credenciais.
- Sem gravação de áudio bruto.

---

## 15. Ordem de execução para o Codex (não inverter)

1. **Inspecionar** os arquivos reais do Agrion e escrever plano interno curto de alterações, sem trocar stack.
2. Criar **modelos de dados** (`AgriculturalProfile`, `Interview`, `Field`, `ProfilePatch`) e validação com enums e regras deste MD.
3. Implementar **IndexedDB** e testes de atualização, recuperação e idempotência.
4. Implementar o **Blueprint Flask**: token efêmero e extração JSON; testes de erro e segurança.
5. Integrar o **cliente Live** vanilla JS (WebSocket, PCM, transcrição, VAD, interrupções).
6. Implementar **InterviewController** determinístico (3m/2m/5m), tool de conclusão e fechamento seguro.
7. Montar as telas com a identidade Agrion, integração ao cadastro geográfico e checklist em tempo real.
8. Criar modo texto e caminhos de erro.
9. Rodar testes automatizados e integração real, quando a credencial estiver disponível.
10. Atualizar README, arquitetura, design e `.env.example`.
11. Informar quais arquivos mudou, os testes efetivamente executados, eventuais falhas e o modo exato de configurar a credencial. **Não fazer deploy sem autorização.**

### Critérios de pronto

A tarefa só está completa se o agricultor puder iniciar uma **conversa REAL** de voz, falar livremente, interromper a IA, ver o checklist atualizado, encerrar naturalmente ou por limite de tempo e recuperar o **perfil agrícola estruturado** após atualizar a página. Uma interface falsa de áudio ou respostas roteirizadas **não** satisfazem esta especificação.

---

## 16. Referências oficiais e orientações de compatibilidade

Documentação consultada em 14/11/2026:

1. Visão geral Gemini Live: https://ai.google.dev/gemini-api/docs/live-api
2. Capacidades de Live (PCM, transcrições, VAD, interrupções): https://ai.google.dev/gemini-api/docs/live-api/capabilities
3. Tokens efêmeros: https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens
4. Ferramentas / function calling na Live API: https://ai.google.dev/gemini-api/docs/live-api/tools
5. Vida da sessão e reconexão: https://ai.google.dev/gemini-api/docs/live-api/session-management
6. Modelo Gemini 3.8 Live: https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live
7. Modelo Gemini 3.5 Flash-Lite: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
8. Extração com saída estruturada: https://ai.google.dev/gemini-api/docs/structured-output
9. Exemplo oficial Google **Vanilla JS / Tokens efêmeros / WebSocket**: https://github.com/google-gemini/gemini-live-api-examples/tree/main/gemini-live-ephemeral-tokens-websocket
10. Preços: https://ai.google.dev/gemini-api/docs/pricing

**Atenção de implementação:** as APIs Gemini Live e emissão de tokens efêmeros evoluem rapidamente. Verifique os nomes exatos dos campos do SDK/protocolo instalado. Os JSONs de eventos `AGRION_*` deste documento são **contratos internos do Agrion**, não payloads enviados literalmente à API do Google. Não confundir créditos promocionais de GCP com franquia/billing da **Gemini Developer API**; verificar faturamento e cotas na conta correta antes de liberar acesso público.

---

## 17. Texto final que o agente deve exibir ao entregar

> “Implementei o Agrion Discovery mantendo a arquitetura atual. As alterações foram: [arquivos]. Modelos e endpoints criados: [lista]. Testes executados: [lista + resultados]. Integração real de áudio: [sim/não, evidência]. Credenciais necessárias: `GEMINI_API_KEY`. Pendências concretas: [lista]. Não fiz deploy remoto.”

**Regra de ouro:** a inteligência da conversa aparece ao agricultor como simplicidade; a complexidade de dados, estados, validação e encerramento deve ficar invisível, mas implementada de verdade.
