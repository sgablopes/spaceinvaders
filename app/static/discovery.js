(function(){
 'use strict';
 const P=window.AgrionProfile,R=window.AgrionRepository,I=window.AgrionInterviewLanguage;
 const LIMITS=window.AGRION_CONFIG.interviewLimits;
 const OPENING_PROMPTS={'pt-BR':'Cumprimente brevemente: diga que é o Agrion e pergunte se está tudo bem. Aguarde a resposta antes de explicar a entrevista.','en-US':'Briefly say you are Agrion and ask how the person is. Wait for their reply before explaining the interview.'};
 const LIVE_PROMPTS={
  confirm:{'pt-BR':'Há uma informação incerta. Faça uma pergunta breve para confirmá-la e aguarde a resposta da pessoa antes de encerrar.','en-US':'One fact is uncertain. Ask a brief question to confirm it and wait for the farmer’s answer before finishing.'},
  pendingFarewell:{'pt-BR':'A entrevista ainda tem dados pendentes. Faça uma pergunta curta sobre uma pendência antes de se despedir.','en-US':'Some facts are pending. Ask one brief question about a missing fact before saying goodbye.'},
  invite:{'pt-BR':'Explique brevemente o que faremos e convide um relato livre sobre a lavoura.','en-US':'Briefly explain what we will do and invite the farmer to talk freely about their crops.'},
  resume:{'pt-BR':'Ainda há dados pendentes. Retome a conversa com uma pergunta breve sobre uma pendência.','en-US':'Some facts are pending. Resume with one brief question about a missing fact.'},
  close:{'pt-BR':'CLOSE_REQUESTED. Agradeça brevemente e encerre agora, sem novas perguntas.','en-US':'CLOSE_REQUESTED. Thank the farmer briefly and end now without further questions.'}
 };
 const livePrompt=key=>LIVE_PROMPTS[key][interview?.language]||LIVE_PROMPTS[key]['pt-BR'];
 const labels={last_crop:'Cultura anterior',last_harvest_result:'Última colheita',main_difficulties:'Dificuldades',irrigation:'Irrigação',mechanization:'Máquinas e trabalho',primary_goal:'Objetivo da próxima safra',next_crop_preference:'Preferência de plantio',current_season_stage:'Fase da safra atual'};
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let property,profile,interview,ws,audioContext,micStream,micSource,processor,playAt=0,timer,closing=false,finalizing=false,farewellStarted=false,closingSignalSent=false,closePromptPending=false,modelTurnActive=false,lastModelFrameMono=0,lastModelTurnMono=0,clarificationPending=false,queue=Promise.resolve(),pendingInput='',pendingOutput='',lastAssistantTurn='',lastStateKey='',inputDebounce,outputDebounce,outputNode=null,inputTurn=null,outputTurn=null,inputQuestion='',sequence=0,introStage=0,startedMono=0,closingMono=0,confirmationState='none',confirmationNeededMono=0,confirmationResponseSeen=false,confirmationPromptCount=0,lastFarmerMono=0,recoveryPrompts=0,view='none',autoTimer=null,manualSession=null,completed=false,languageLocked=false,languageChanging=false,manualBaseline=new Map();const audioSources=new Set(),turnHistory=[],reviewedKeys=new Set();
 function status(text){const node=document.getElementById('discoveryStatus');if(node)node.textContent=I.t(text);}
 function progress(){if(!profile)return 0;if(completed)return 100;const resolved=P.ESSENTIAL.filter(id=>profile.fields[id].status!=='pending'&&profile.fields[id].status!=='uncertain').length;return Math.min(99,Math.round(resolved/P.ESSENTIAL.length*100));}
 function checklist(){const node=document.getElementById('discoveryProgress');if(!node)return;const value=view==='next'?100:progress();node.value=value;node.setAttribute('aria-valuenow',String(value));document.getElementById('discoveryProgressText').textContent=`${value}% ${(window.AgrionLocale?.get()||I.get())==='en-US'?'complete':'concluído'}`;}
 function markup(){
   if(view==='next')return window.AgrionHome.markup(property);
   if(view==='chat')return window.AgrionChat.markup();
   const manual=view==='manual';
   return `<main class="discovery-page"><div class="discovery-shell"><div class="discovery-greeting"><strong>${window.AgrionLocale?.get()==='en-US'?'Hello':'Olá'}, ${esc(property?.personName||'')}</strong><span>${esc(property?.propertyName&&property.propertyName!=='Minha propriedade'?property.propertyName:window.AgrionLocale?.get()==='en-US'?'My property':'Sua propriedade')}</span></div><div class="discovery-avatar"><img src="/static/agrion-avatar.jpeg" alt="Agrion"></div><h1>Vamos conhecer você</h1><p class="discovery-intro">Conte sobre sua experiência nesta propriedade para preparar seu perfil agrícola.</p><div class="discovery-progress-wrap"><div class="discovery-progress-caption"><span>Seu progresso</span><strong id="discoveryProgressText"></strong></div><progress id="discoveryProgress" max="100" value="0" aria-label="Progresso do perfil"></progress></div><div class="discovery-language"><label for="discoveryLanguage">Idioma da conversa</label><select id="discoveryLanguage"><option value="pt-BR">Português (Brasil)</option><option value="en-US">English</option></select><small id="discoveryLanguageHint"></small></div>${manual?window.AgrionManual.markup(profile):`<div class="discovery-voice"><p id="discoveryStatus" role="status">Preparando a conversa…</p><div id="discoveryTranscript" class="discovery-transcript" aria-live="polite"></div><button id="discoveryRetry" class="btn btn-secondary" type="button" hidden>Ativar voz</button><form id="discoveryForm" hidden><label for="discoveryInput">Sua resposta</label><textarea id="discoveryInput" rows="3" maxlength="3000" placeholder="Conte sobre sua lavoura"></textarea><button class="btn btn-primary" type="submit">Enviar</button></form><button id="discoveryManual" class="btn btn-secondary" type="button">Responder manualmente em vez de conversar</button></div>`}</div></main>`;
 }
 function afterRender(){
   if(view==='next'){window.AgrionHome.afterRender();return;}
   if(view==='chat'){window.AgrionChat.afterRender();return;}
   checklist();I.translate(document.querySelector('.discovery-shell'));
   const languageSelect=document.getElementById('discoveryLanguage');languageSelect.value=I.get();syncLanguageControl();languageSelect.onchange=()=>{void changeLanguage(languageSelect.value);};
   if(view==='manual'){
     const form=document.getElementById('discoveryManualForm');form.onsubmit=saveManual;
     try{manualBaseline=new Map(window.AgrionManual.collect(form).map(e=>[e.field,JSON.stringify(e)]));}catch(_){manualBaseline=new Map();}
     form.addEventListener('input',lockLanguage);
     const never=form.elements.no_previous_cultivation,notPlanted=form.elements.not_planted;
     const toggle=()=>{for(const id of ['last_crop','harvest_result'])form.elements[id].closest('.discovery-field').hidden=never.checked;form.elements.planting_date.closest('.discovery-field').hidden=notPlanted.checked;};
     never.onchange=toggle;notPlanted.onchange=toggle;toggle();return;
   }
   document.getElementById('discoveryManual').onclick=()=>{void switchToManual();};
   document.getElementById('discoveryRetry').onclick=()=>{document.getElementById('discoveryRetry').hidden=true;void start('voice');};
   document.getElementById('discoveryForm').onsubmit=e=>{e.preventDefault();const input=document.getElementById('discoveryInput');const text=input.value.trim();if(text){input.value='';const turn=beginTurn('farmer',text);lastFarmerMono=performance.now();recoveryPrompts=0;sendText(text);extract(text,turn.turn_id,lastAssistantTurn);}};
 }
 function syncLanguageControl(){const select=document.getElementById('discoveryLanguage');if(select){select.disabled=languageLocked||languageChanging;select.value=I.get();}const hint=document.getElementById('discoveryLanguageHint');if(hint)hint.textContent=languageLocked?(window.AgrionLocale?.get()!==I.get()?`${I.t('Idioma da conversa permanece em')} ${I.get()==='pt-BR'?'Português (Brasil)':'English'}.`:I.t('Idioma definido após a primeira resposta.')):'';}
 function lockLanguage(){if(languageLocked)return;languageLocked=true;if(profile){profile.interview_language=I.get();void R.put('agricultural_profiles',profile).catch(()=>{});}if(interview){interview.has_farmer_response=true;void R.put('interviews',interview).catch(()=>{});}syncLanguageControl();}
 async function changeLanguage(language){
   if(languageLocked||languageChanging||!I.valid(language)){syncLanguageControl();return;}
   languageChanging=true;syncLanguageControl();clearTimeout(autoTimer);autoTimer=null;
   const old=interview;interview=null;const socket=ws;ws=null;
   clearInterval(timer);clearTimeout(inputDebounce);clearTimeout(outputDebounce);socket?.close();
   try{
     await stopMicrophone();
     if(old){old.status='partial';old.completion_reason='language_changed';old.finished_at=new Date().toISOString();old.updated_at=old.finished_at;await R.put('interviews',old);}
     I.set(language);if(window.AgrionLocale&&window.AgrionLocale.get()!==language)window.AgrionLocale.set(language);pendingInput='';pendingOutput='';lastAssistantTurn='';lastStateKey='';inputTurn=null;outputTurn=null;outputNode=null;inputQuestion='';sequence=0;introStage=0;modelTurnActive=false;closing=false;finalizing=false;farewellStarted=false;closingSignalSent=false;closePromptPending=false;lastModelFrameMono=0;lastModelTurnMono=0;clarificationPending=false;confirmationState='none';recoveryPrompts=0;turnHistory.length=0;reviewedKeys.clear();
     window.render();
   }catch(_){status('Não foi possível iniciar a voz. Tente novamente ou responda manualmente.');}
   finally{languageChanging=false;syncLanguageControl();}
   if(view==='voice')await start('voice');
 }
 function line(who,text,before=null){const list=document.getElementById('discoveryTranscript');if(!list)return null;const p=document.createElement('p');const b=document.createElement('strong');const content=document.createTextNode(text);b.textContent=who+': ';p.append(b,content);if(before)list.insertBefore(p,before);else list.appendChild(p);list.scrollTop=list.scrollHeight;return content;}
 function beginTurn(speaker,text,before=null){if(speaker==='farmer'&&text)lockLanguage();const turn={turn_id:crypto.randomUUID(),speaker,text,node:line(speaker==='farmer'?I.t('Você'):'Agrion',text,before)};const position=before?turnHistory.findIndex(x=>x.node?.parentNode===before):-1;if(position<0)turnHistory.push(turn);else turnHistory.splice(position,0,turn);return turn;}
 function historySnapshot(){return turnHistory.filter(x=>x.text).slice(-40).map(x=>({turn_id:x.turn_id,speaker:x.speaker,text:x.text.slice(0,500)}));}
 function joinTranscript(current,fragment){const next=String(fragment||'').trim();if(!next)return current;if(!current||next.startsWith(current))return next;if(current.startsWith(next)||current.endsWith(next))return current;return current+(/^[.,!?;:%)\]]/.test(next)?'':' ')+next;}
 function interviewState(clarify=false){return {fields:Object.fromEntries(P.ESSENTIAL.map(id=>[id,profile.fields[id].status])),closing,clarify,intro_stage:introStage,first_cultivation:profile.fields.last_crop.value?.never_cultivated===true||profile.fields.last_crop.value?.no_previous_cultivation===true,confirmation_attempted:interview?.confirmation_attempted===true};}
 function sendState(clarify=false){if(ws?.readyState!==WebSocket.OPEN||!interview)return;const state=interviewState(clarify),key=JSON.stringify(state);if(key===lastStateKey)return;lastStateKey=key;ws.send(JSON.stringify({interviewState:state}));}
 function missingFields(){return P.ESSENTIAL.filter(id=>profile.fields[id].status==='pending');}
 function uncertainFields(){return P.ESSENTIAL.filter(id=>profile.fields[id].status==='uncertain');}
 function canCloseByCompleteness(){return !missingFields().length&&(!uncertainFields().length||confirmationState==='answered');}
 function audioDrained(){return !audioContext||playAt<=audioContext.currentTime;}
 function needConfirmation(){if(confirmationState!=='none')return;confirmationState='needed';confirmationNeededMono=performance.now();confirmationResponseSeen=false;status('Aguardando confirmação de uma informação incerta…');}
 function promptConfirmation(){
   if(closing||modelTurnActive||!audioDrained()||ws?.readyState!==WebSocket.OPEN)return;
   confirmationState='asking';confirmationResponseSeen=false;confirmationPromptCount++;
   confirmationNeededMono=performance.now();
   sendText(livePrompt('confirm'));
 }
 function completeConfirmationQuestion(){
   if(confirmationState!=='needed'&&confirmationState!=='asking')return;
   if(confirmationResponseSeen){confirmationState='awaiting_answer';status('Aguardando sua confirmação…');}
   else{confirmationState='needed';confirmationNeededMono=performance.now();}
   confirmationResponseSeen=false;
 }
 async function retryPending(){
   for(const pending of (await R.all('pending_extractions')).filter(x=>x.property_id===property.propertyId)){
     const previous=await R.get('interviews',pending.interview_id);
     if(!previous)continue;
     const body={interview_id:pending.interview_id,property_id:property.propertyId,turn_id:pending.turn_id,sequence:pending.sequence,speaker:'farmer',transcript:pending.transcript,assistant_context:pending.assistant_context||'',profile_revision:profile.revision,profile_snapshot:{fields:Object.fromEntries(P.ESSENTIAL.map(id=>[id,{status:profile.fields[id].status,value:profile.fields[id].value}]))}};
     try{
       const response=await fetch('/api/interview/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
       if(!response.ok)break;
       const result=P.apply(profile,await response.json(),pending.transcript);
       profile=result.profile;
       const revisions=result.applied.map(x=>({...x,revision_id:crypto.randomUUID(),turn_id:pending.turn_id,interview_id:pending.interview_id,created_at:new Date().toISOString()}));
       previous.processed_turn_ids=[...new Set([...previous.processed_turn_ids,pending.turn_id])];
       previous.pending_extraction_turn_ids=previous.pending_extraction_turn_ids.filter(id=>id!==pending.turn_id);
       previous.updated_at=new Date().toISOString();
       await R.savePatch(profile,revisions,previous);
       await R.remove('pending_extractions',pending.turn_id);
       checklist();
     }catch(_){break;}
   }
 }
 async function open(){property=window.AgrionPropertyStore.read();if(!property?.geometry)return;profile=P.ensureFields(await R.getByPropertyId(property.propertyId)||P.create(property));await R.put('agricultural_profiles',profile);const sessions=await R.all('interviews');completed=sessions.some(x=>x.property_id===property.propertyId&&x.status==='completed');manualSession=null;languageLocked=P.ESSENTIAL.some(id=>profile.fields[id].status!=='pending')||sessions.some(x=>x.property_id===property.propertyId&&x.has_farmer_response===true);const previousSession=sessions.filter(x=>x.property_id===property.propertyId).sort((a,b)=>(b.updated_at||'').localeCompare(a.updated_at||''))[0];if(!languageLocked&&window.AgrionLocale)I.set(window.AgrionLocale.get(),false);if(languageLocked&&I.valid(profile.interview_language||previousSession?.language))I.set(profile.interview_language||previousSession.language,false);clearTimeout(autoTimer);window.AgrionHome.reset();view=completed?'next':'voice';window.render();if(completed)return;
 lastAssistantTurn='';pendingInput='';lastStateKey='';closing=false;finalizing=false;farewellStarted=false;closingSignalSent=false;closePromptPending=false;modelTurnActive=false;lastModelFrameMono=0;lastModelTurnMono=0;clarificationPending=false;confirmationState='none';confirmationNeededMono=0;confirmationResponseSeen=false;confirmationPromptCount=0;sequence=0;introStage=0;inputTurn=null;outputTurn=null;inputQuestion='';recoveryPrompts=0;turnHistory.length=0;reviewedKeys.clear();finishOutput();
 if(!completed)autoTimer=setTimeout(()=>{autoTimer=null;if(view==='voice'&&!interview)void start('voice');},1500);else{status('Perfil concluído. Para conversar novamente, use Ativar voz.');document.getElementById('discoveryRetry').hidden=false;}
 retryPending().catch(()=>status('Algumas respostas aguardam análise. Os dados já registrados permanecem salvos.'));
 }
 async function start(mode){if(view!=='voice'||interview?.status==='in_progress')return;const now=new Date().toISOString();startedMono=0;closingMono=0;interview={schema_version:'1.1.0',interview_id:crypto.randomUUID(),profile_id:profile.profile_id,property_id:property.propertyId,status:'in_progress',mode,language:I.get(),voice:I.get()==='pt-BR'?'Orus':null,started_at:null,created_at:now,updated_at:now,closing_requested_at:null,finished_at:null,duration_seconds:null,completion_reason:null,farewell_delivered:false,confirmation_attempted:false,essential_field_counts:{},processed_turn_ids:[],pending_extraction_turn_ids:[],errors:[]};const active=interview;await R.put('interviews',active);if(interview!==active)return;profile.interview_history.push(active.interview_id);await R.put('agricultural_profiles',profile);if(interview!==active||view!=='voice')return;syncLanguageControl();status('Conectando ao Agrion…');try{await connectLive();if(interview!==active||view!=='voice')return;startedMono=performance.now();active.started_at=new Date().toISOString();await R.put('interviews',active);if(interview!==active||view!=='voice')return;timer=setInterval(tick,500);if(mode==='voice')await startMicrophone(active);if(interview!==active||view!=='voice')return;sendState();sendText(OPENING_PROMPTS[active.language]||OPENING_PROMPTS['pt-BR']);status('Microfone ativo. Pode falar e interromper o Agrion.');}catch(err){if(interview!==active||view!=='voice')return;active.errors.push('live_connection_failed');status(err.message.startsWith('live_rate_limited')?'Limite de conexões por hora atingido. Tente novamente mais tarde.':err.message.startsWith('origin_rejected')?'A origem da conexão foi recusada pelo servidor.':err.message.startsWith('vertex_not_configured')?'Vertex AI não está configurado no servidor.':(err.message.startsWith('vertex_unavailable')||err.message.startsWith('vertex_connection_closed'))?'Não foi possível conectar ao Vertex AI. Verifique os logs do servidor.':'Não foi possível iniciar a voz. Tente novamente ou responda manualmente.');await stopMicrophone();if(interview!==active||view!=='voice')return;clearInterval(timer);ws?.close();ws=null;active.status='partial';active.finished_at=new Date().toISOString();await R.put('interviews',active);interview=null;syncLanguageControl();document.getElementById('discoveryRetry').hidden=false;}}
 async function connectLive(){
   return new Promise((resolve,reject)=>{
     const url=(location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/interview/live-session';
     const active=interview,socket=new WebSocket(url);ws=socket;
     let ready=false, settled=false;
     const fail=reason=>{if(settled)return;settled=true;clearTimeout(timeout);reject(new Error(reason));};
     const timeout=setTimeout(()=>{fail('live_timeout');socket.close();},15000);
     socket.onopen=()=>{if(interview!==active||ws!==socket){socket.close();return;}socket.send(JSON.stringify({interview_id:active.interview_id,property_id:property.propertyId,person_name:property.personName,property_name:property.propertyName,language:active.language,voice:active.voice}));};
     socket.onerror=()=>{if(!ready)fail('websocket_handshake_failed');};
     socket.onclose=event=>{if(!ready)fail(`websocket_closed_${event.code}`);else if(interview===active&&ws===socket&&interview?.status==='in_progress'&&!finalizing&&!closing){status('Conexão por voz interrompida. Continue pelo formulário.');void finish('connection_lost',false,'manual');}};
     socket.onmessage=async event=>{
       let message;
       try{
         const raw=typeof event.data==='string' ? event.data : event.data instanceof Blob ? await event.data.text() : new TextDecoder().decode(event.data);
         message=JSON.parse(raw);
       }catch(_){fail('invalid_live_message');return;}
       if(interview!==active||ws!==socket)return;
       if(message.setupComplete){ready=true;if(!settled){settled=true;clearTimeout(timeout);resolve();}}
       else if(message.error&&!ready)fail(`${message.error}${message.stage?`:${message.stage}`:''}`);
       else handleLive(message);
     };
   });
 }
 function sendText(text){if(ws?.readyState===WebSocket.OPEN){modelTurnActive=true;ws.send(JSON.stringify({clientContent:{turns:[{role:'user',parts:[{text}]}],turnComplete:true}}));}}
 function handleLive(msg){
   if(msg.error){status('Vertex AI indisponível. Tente novamente quando o serviço voltar.');ws?.close();return;}
   const content=msg.serverContent;
   const inputTranscription=msg.inputTranscription||content?.inputTranscription;
   const t=inputTranscription?.text;
   if(t){lockLanguage();if(!inputTurn){inputTurn=beginTurn('farmer','',outputTurn?.node?.parentNode);inputQuestion=lastAssistantTurn;}pendingInput=joinTranscript(pendingInput,t);inputTurn.text=pendingInput;if(inputTurn.node)inputTurn.node.nodeValue=pendingInput;clearTimeout(inputDebounce);inputDebounce=setTimeout(flushInput,1800);}
   if(inputTranscription?.finished&&pendingInput)flushInput();
   const outputTranscription=msg.outputTranscription||content?.outputTranscription;
   if(outputTranscription?.text){modelTurnActive=true;lastModelFrameMono=performance.now();if(confirmationState==='needed'||confirmationState==='asking')confirmationResponseSeen=true;if(closing&&closingSignalSent)farewellStarted=true;pendingOutput=joinTranscript(pendingOutput,outputTranscription.text);lastAssistantTurn=pendingOutput.slice(-1000);if(!outputTurn){outputTurn=beginTurn('agrion',pendingOutput);outputNode=outputTurn.node;}else{outputTurn.text=pendingOutput;if(outputNode)outputNode.nodeValue=pendingOutput;}clearTimeout(outputDebounce);outputDebounce=setTimeout(finishOutput,2500);}
   if(outputTranscription?.finished)finishOutput();
   if(content?.interrupted){finishOutput();for(const source of audioSources){try{source.stop();}catch(_){}}audioSources.clear();playAt=0;}
   if(content?.modelTurn?.parts)for(const part of content.modelTurn.parts){modelTurnActive=true;lastModelFrameMono=performance.now();if(confirmationState==='needed'||confirmationState==='asking')confirmationResponseSeen=true;if(part.inlineData?.data){if(closing&&closingSignalSent)farewellStarted=true;playAudio(part.inlineData.data);}if(part.text&&!outputTranscription&&!pendingOutput){if(closing&&closingSignalSent)farewellStarted=true;beginTurn('agrion',part.text);lastAssistantTurn=part.text.slice(-1000);}}
   if(content?.turnComplete){modelTurnActive=false;lastModelTurnMono=performance.now();finishOutput();if(closing&&closePromptPending&&!closingSignalSent)sendClosePrompt();else if(closing&&closingSignalSent&&farewellStarted){const delay=audioContext?Math.max(0,(playAt-audioContext.currentTime)*1000):0;setTimeout(()=>{if(interview?.status==='in_progress')finish(interview.completion_reason||'time_limit',true);},delay+50);}else if(!closing&&introStage>=2&&!missingFields().length){if(canCloseByCompleteness())requestClose('essential_fields_complete');else{needConfirmation();completeConfirmationQuestion();}}else if(!closing&&introStage>=2&&missingFields().length&&/(encerr|finaliz|termin|obrigad|até logo|goodbye|finish|gracias|adiós)/i.test(lastAssistantTurn))setTimeout(()=>{void (async()=>{if(interview?.status!=='in_progress'||modelTurnActive||performance.now()-lastFarmerMono<=2500)return;await reanalyzePending();if(interview?.status!=='in_progress'||closing)return;if(!missingFields().length){if(canCloseByCompleteness())requestClose('essential_fields_complete');else{needConfirmation();promptConfirmation();}return;}if(recoveryPrompts++<2)sendText(livePrompt('pendingFarewell'));else finish('model_stalled');})();},3000);}
   if(msg.toolCall?.functionCalls)void handleToolCalls(msg.toolCall.functionCalls);
 }
 async function handleToolCalls(calls){
   const active=interview,socket=ws;
   await Promise.race([queue.catch(()=>{}),new Promise(resolve=>setTimeout(resolve,5000))]);
   if(interview!==active||ws!==socket||!active)return;
   if(calls.some(call=>call.name==='complete_initial_interview')&&missingFields().length)await reanalyzePending();
   if(interview!==active||ws!==socket)return;
   const responses=[];let accepted=false;
   for(const call of calls){
     if(call.name==='get_interview_state')responses.push({id:call.id,name:call.name,response:{status:'ok',retryable:false,message:'Use os campos pendentes para escolher a próxima pergunta.',...interviewState(),pending_fields:missingFields(),uncertain_fields:uncertainFields()}});
     if(call.name==='complete_initial_interview'){
       const pending=missingFields(),uncertain=uncertainFields();
       const allowed=closing||canCloseByCompleteness();
       if(!allowed&&uncertain.length&&!pending.length)needConfirmation();
       responses.push({id:call.id,name:call.name,response:allowed?{status:'ok',retryable:false,message:'Conclusão autorizada. Despeça-se brevemente.',accepted:true,next_action:'say_short_farewell'}:{status:'incomplete',retryable:false,message:'Ainda há uma informação a esclarecer com o agricultor.',accepted:false,next_action:pending.length?'ask_one_missing_essential_question':'confirm_uncertainty_once',missing_fields:pending,uncertain_fields:uncertain}});
       accepted=accepted||allowed;
     }
   }
   if(responses.length&&ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({toolResponse:{functionResponses:responses}}));
   if(accepted&&!closing)requestClose('essential_fields_complete',false);
 }
 async function reanalyzePending(){
   const farmer=[...turnHistory].reverse().find(turn=>turn.speaker==='farmer'&&turn.text);
   if(!farmer||!missingFields().length||!interview||closing)return;
   const key=`${profile.revision}:${farmer.turn_id}`;
   if(reviewedKeys.has(key))return;
   reviewedKeys.add(key);
   extract(farmer.text,farmer.turn_id,lastAssistantTurn,true);
   await Promise.race([queue.catch(()=>{}),new Promise(resolve=>setTimeout(resolve,10000))]);
 }
 function flushInput(){clearTimeout(inputDebounce);inputDebounce=null;const text=pendingInput.trim(),turn=inputTurn,question=inputQuestion;pendingInput='';inputTurn=null;inputQuestion='';if(text){modelTurnActive=true;lastFarmerMono=performance.now();recoveryPrompts=0;extract(text,turn?.turn_id,question);}}
 function finishOutput(){clearTimeout(outputDebounce);outputDebounce=null;pendingOutput='';outputNode=null;outputTurn=null;}
 function extract(text,sourceTurnId=null,question=null,review=false){
   const activeInterview=interview,assistantContext=(question??lastAssistantTurn).slice(-1000),history=historySnapshot();
   if(!activeInterview)return;
   const turnId=sourceTurnId||crypto.randomUUID(),seq=++sequence;
   queue=queue.catch(()=>{}).then(async()=>{
     const body={interview_id:activeInterview.interview_id,property_id:property.propertyId,turn_id:turnId,sequence:seq,speaker:'farmer',transcript:text,assistant_context:assistantContext,history,profile_revision:profile.revision,profile_snapshot:{fields:Object.fromEntries(P.ESSENTIAL.map(id=>[id,{status:profile.fields[id].status,value:profile.fields[id].value}]))}};
     try{
       const res=await fetch('/api/interview/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
       if(!res.ok)throw Error('extraction');
       const data=await res.json();if(view!=='voice'||interview!==activeInterview)return;const result=P.apply(profile,data,text,history);
       const revisions=result.applied.map(x=>({...x,revision_id:crypto.randomUUID(),turn_id:x.after.evidence.at(-1)?.turn_id||turnId,interview_id:activeInterview.interview_id,created_at:new Date().toISOString()}));
       profile=result.profile;if(!activeInterview.processed_turn_ids.includes(turnId))activeInterview.processed_turn_ids.push(turnId);activeInterview.updated_at=new Date().toISOString();
       const answeredConfirmation=!review&&confirmationState==='awaiting_answer';
       await R.savePatch(profile,revisions,activeInterview);checklist();
       if(interview===activeInterview){
         if(answeredConfirmation){confirmationState='answered';activeInterview.confirmation_attempted=true;await R.put('interviews',activeInterview);}
         if(!review&&introStage<2){introStage++;if(introStage===1&&!modelTurnActive)setTimeout(()=>{if(interview===activeInterview&&!modelTurnActive)sendText(livePrompt('invite'));},1000);}
         const pending=missingFields(),uncertain=uncertainFields();
         if(!pending.length&&uncertain.length)needConfirmation();
         const clarify=!review&&!result.applied.length&&seq>1&&!!assistantContext&&!clarificationPending;
         if(result.applied.length)clarificationPending=false;
         else if(clarify)clarificationPending=true;
         sendState(clarify);
         if(!review&&canCloseByCompleteness())requestClose('essential_fields_complete');
       }
     }catch(err){
       activeInterview.errors.push('extraction_failed');
       if(!review&&introStage<2){introStage++;sendState();}
       if(!review&&document.getElementById('discoveryConsent')?.checked){await R.put('pending_extractions',{turn_id:turnId,interview_id:activeInterview.interview_id,property_id:property.propertyId,sequence:seq,transcript:text,assistant_context:assistantContext});activeInterview.pending_extraction_turn_ids.push(turnId);}
       await R.put('interviews',activeInterview);status('Não foi possível analisar esta resposta agora. Você pode continuar.');
     }
   });
 }
 async function recoverStalledConversation(){
   lastModelTurnMono=0;
   await reanalyzePending();
   if(interview?.status!=='in_progress'||closing||modelTurnActive)return;
   if(!missingFields().length){if(canCloseByCompleteness())requestClose('essential_fields_complete');else{needConfirmation();promptConfirmation();}return;}
   if(recoveryPrompts++<2)sendText(livePrompt('resume'));
 }
 function tick(){
   if(!interview||interview.status!=='in_progress')return;
   const now=performance.now(),elapsed=(now-startedMono)/1000;
   if(elapsed>=LIMITS.absolute||closingMono&&now-closingMono>=LIMITS.grace*1000){finish('safety_timeout');return;}
   if(closing){
     if(closePromptPending&&!closingSignalSent&&!modelTurnActive&&audioDrained())sendClosePrompt();
     else if(now-closingMono>=30000&&audioDrained())finish('farewell_timeout');
     return;
   }
   if(elapsed>=LIMITS.normal){requestClose('time_limit');return;}
   if(confirmationState==='needed'&&modelTurnActive&&now-lastModelFrameMono>=20000
      &&now-confirmationNeededMono>=20000&&audioDrained())modelTurnActive=false;
   if(confirmationState==='needed'&&!modelTurnActive&&audioDrained()&&now-confirmationNeededMono>=6000){
     if(confirmationPromptCount<2)promptConfirmation();
     else if(now-confirmationNeededMono>=25000)finish('confirmation_timeout');
     return;
   }
   if(confirmationState==='asking'&&now-confirmationNeededMono>=20000&&now-lastModelFrameMono>=20000){
     modelTurnActive=false;confirmationState='needed';confirmationNeededMono=now;return;
   }
   if(confirmationState==='awaiting_answer'&&confirmationPromptCount<2&&!modelTurnActive&&audioDrained()
      &&now-lastModelTurnMono>=30000&&now-lastFarmerMono>=30000&&!inputTurn){promptConfirmation();return;}
   if(introStage>=2&&missingFields().length&&lastModelTurnMono&&now-lastModelTurnMono>=20000
      &&now-lastFarmerMono>=20000&&!inputTurn&&!modelTurnActive&&recoveryPrompts<2)void recoverStalledConversation();
 }
 function sendClosePrompt(){if(!closePromptPending||closingSignalSent||modelTurnActive||!audioDrained()||ws?.readyState!==WebSocket.OPEN)return;closePromptPending=false;closingSignalSent=true;sendText(livePrompt('close'));}
 function requestClose(reason,signal=true){if(closing||!interview||interview.status!=='in_progress')return;closing=true;farewellStarted=false;closingSignalSent=!signal;closePromptPending=signal;closingMono=performance.now();interview.closing_requested_at=new Date().toISOString();interview.completion_reason=reason;R.put('interviews',interview);status('Encerrando a conversa…');sendState();if(signal)sendClosePrompt();if(!ws||ws.readyState!==WebSocket.OPEN)finish(reason);}
 async function finish(reason='user_request',farewell=false,destination=null){if(!interview){if(destination){view=destination;window.render();}return;}if(interview.status!=='in_progress'||finalizing)return;finalizing=true;clearInterval(timer);clearTimeout(inputDebounce);finishOutput();if(pendingInput)flushInput();await stopMicrophone();ws?.close();ws=null;await Promise.race([queue,new Promise(resolve=>setTimeout(resolve,4000))]);interview.status=reason==='user_request'?'cancelled':reason==='essential_fields_complete'?'completed':'partial';interview.finished_at=new Date().toISOString();interview.updated_at=interview.finished_at;interview.duration_seconds=startedMono?Math.round((performance.now()-startedMono)/1000):0;interview.completion_reason=reason;interview.farewell_delivered=farewell;interview.essential_field_counts=Object.fromEntries(['pending','confirmed','uncertain','unknown'].map(s=>[s,P.ESSENTIAL.filter(id=>profile.fields[id].status===s).length]));await R.put('interviews',interview);completed=completed||interview.status==='completed';interview=null;closing=false;finalizing=false;view=destination||(reason==='essential_fields_complete'?'next':'manual');if(view==='next')window.AgrionHome.reset();window.render();}
 async function switchToManual(){clearTimeout(autoTimer);autoTimer=null;const button=document.getElementById('discoveryManual');if(button)button.disabled=true;if(interview)await finish('user_request',false,'manual');else{await stopMicrophone();ws?.close();ws=null;view='manual';window.render();}}
 async function saveManual(event){event.preventDefault();if(event.currentTarget.dataset.saving==='true')return;const continueAnalysis=event.submitter?.value!=='save';const form=event.currentTarget,error=document.getElementById('discoveryManualError');error.hidden=true;let entries;try{entries=window.AgrionManual.collect(form).filter(e=>manualBaseline.get(e.field)!==JSON.stringify(e));}catch(problem){error.textContent=I.t(problem.message);error.hidden=false;return;}const buttons=[...form.querySelectorAll('button[type="submit"]')];form.dataset.saving='true';buttons.forEach(b=>b.disabled=true);try{
   if(!manualSession){const now=new Date().toISOString();manualSession={schema_version:'1.1.0',interview_id:crypto.randomUUID(),profile_id:profile.profile_id,property_id:property.propertyId,status:'in_progress',mode:'manual',language:I.get(),voice:null,started_at:now,created_at:now,updated_at:now,closing_requested_at:null,finished_at:null,duration_seconds:null,completion_reason:null,farewell_delivered:false,confirmation_attempted:false,essential_field_counts:{},processed_turn_ids:[],pending_extraction_turn_ids:[],errors:[]};profile.interview_history.push(manualSession.interview_id);}
   if(continueAnalysis)for(const id of P.ESSENTIAL)if(profile.fields[id].status==='pending'&&!entries.some(e=>e.field===id))entries.push({field:id,status:'unknown',value:null,unknown_reason:'declined'});
   profile.interview_language=I.get();manualSession.language=I.get();const result=P.applyManual(profile,entries);profile=result.profile;const now=new Date().toISOString();const revisions=result.applied.map(x=>({...x,revision_id:crypto.randomUUID(),turn_id:x.turn_id,interview_id:manualSession.interview_id,created_at:now}));manualSession.updated_at=now;
   const ready=continueAnalysis;
   if(ready){manualSession.status='completed';manualSession.finished_at=now;manualSession.completion_reason=P.ready(profile)?'essential_fields_complete':'preliminary_analysis';manualSession.essential_field_counts=Object.fromEntries(['pending','confirmed','uncertain','unknown'].map(s=>[s,P.ESSENTIAL.filter(id=>profile.fields[id].status===s).length]));}
   await R.savePatch(profile,revisions,manualSession);
   if(ready){completed=true;manualSession=null;view='next';window.AgrionHome.reset();}window.render();
 }catch(problem){error.textContent=I.t('Não foi possível salvar agora. Tente novamente.');error.hidden=false;form.dataset.saving='false';buttons.forEach(b=>b.disabled=false);}}
 async function startMicrophone(active){const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});if(interview!==active||view!=='voice'){stream.getTracks().forEach(t=>t.stop());return;}micStream=stream;audioContext=new AudioContext({sampleRate:16000});micSource=audioContext.createMediaStreamSource(micStream);processor=audioContext.createScriptProcessor(2048,1,1);processor.onaudioprocess=e=>{if(ws?.readyState!==WebSocket.OPEN)return;const input=e.inputBuffer.getChannelData(0),pcm=new Int16Array(input.length);for(let i=0;i<input.length;i++)pcm[i]=Math.max(-32768,Math.min(32767,input[i]*32767));let binary='';const bytes=new Uint8Array(pcm.buffer);for(let i=0;i<bytes.length;i++)binary+=String.fromCharCode(bytes[i]);ws.send(JSON.stringify({realtimeInput:{mediaChunks:[{mimeType:'audio/pcm;rate=16000',data:btoa(binary)}]}}));};micSource.connect(processor);processor.connect(audioContext.destination);}
 function playAudio(base64){if(!audioContext)return;const binary=atob(base64),count=binary.length/2,buffer=audioContext.createBuffer(1,count,24000),samples=buffer.getChannelData(0);for(let i=0;i<count;i++){let v=binary.charCodeAt(i*2)|(binary.charCodeAt(i*2+1)<<8);if(v>32767)v-=65536;samples[i]=v/32768;}const source=audioContext.createBufferSource();source.buffer=buffer;source.connect(audioContext.destination);source.onended=()=>audioSources.delete(source);audioSources.add(source);playAt=Math.max(playAt,audioContext.currentTime);source.start(playAt);playAt+=buffer.duration;}
 async function stopMicrophone(){processor?.disconnect();micSource?.disconnect();micStream?.getTracks().forEach(t=>t.stop());for(const source of audioSources){try{source.stop();}catch(_){}}audioSources.clear();const context=audioContext;audioContext=null;if(context&&context.state!=='closed')await context.close();playAt=0;}
 function invite(){return open().catch(console.error);}
 async function restore(){const stored=window.AgrionPropertyStore.read();if(!stored?.geometry)return;const sessions=(await R.all('interviews')).filter(x=>x.property_id===stored.propertyId).sort((a,b)=>(b.updated_at||'').localeCompare(a.updated_at||''));await open();if(!completed&&sessions[0]?.mode==='manual'){clearTimeout(autoTimer);autoTimer=null;manualSession=sessions[0].status==='in_progress'?sessions[0]:null;view='manual';window.render();}}
 function editProperty(){window.AgrionHome.reset();view='none';window.AgrionProperty.editFromHome();}
 function showHome(){property=window.AgrionPropertyStore.read();window.AgrionHome.reset();view='next';window.render();}
 function openChat(){window.AgrionHome.reset();window.AgrionChat.open();view='chat';window.render();}
 window.addEventListener('agrion:language',event=>{if(view!=='voice'&&view!=='manual')return;const next=event.detail?.language;if(!languageLocked&&!languageChanging&&I.valid(next)&&I.get()!==next){void changeLanguage(next);return;}I.translate(document.querySelector('.discovery-shell'));const greeting=document.querySelector('.discovery-greeting strong');if(greeting)greeting.textContent=`${next==='en-US'?'Hello':'Olá'}, ${property?.personName||''}`;const propertyName=document.querySelector('.discovery-greeting span');if(propertyName&&(!property?.propertyName||property.propertyName==='Minha propriedade'))propertyName.textContent=next==='en-US'?'My property':'Sua propriedade';checklist();syncLanguageControl();});
 window.AgrionDiscovery={open:()=>open().catch(console.error),invite,restore,editProperty,showHome,openChat,view:()=>view,markup,afterRender};
})();
