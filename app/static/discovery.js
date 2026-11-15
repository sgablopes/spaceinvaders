(function(){
 'use strict';
 const P=window.AgrionProfile,R=window.AgrionRepository;
 const LIMITS=window.AGRION_CONFIG.interviewLimits;
 const VOICES=['Zephyr','Kore','Orus','Autonoe','Umbriel','Erinome','Laomedeia','Schedar','Achird','Sadachbia','Puck','Fenrir','Aoede','Enceladus','Algieba','Algenib','Achernar','Gacrux','Zubenelgenubi','Sadaltager','Charon','Leda','Callirrhoe','Iapetus','Rasalgethi','Alnilam','Pulcherrima','Forward','Vindemiatrix','Sulafat'];
 const OPENING_PROMPTS={'pt-BR':'Olá. Apresente-se e convide a pessoa para esta conversa.','en-US':'Hello. Introduce yourself and invite the person to this conversation.','es-US':'Hola. Preséntate e invita a la persona a esta conversación.'};
 const labels={last_crop:'Última cultura',previous_crop:'Cultura anterior',last_harvest_result:'Última colheita',main_difficulties:'Dificuldades',irrigation:'Irrigação',mechanization:'Máquinas e trabalho',primary_goal:'Objetivo da próxima safra'};
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let property,profile,interview,ws,audioContext,micStream,micSource,processor,playAt=0,timer,closing=false,finalizing=false,farewellStarted=false,closingSignalSent=false,closePromptPending=false,modelTurnActive=false,lastModelFrameMono=0,clarificationPending=false,queue=Promise.resolve(),pendingInput='',pendingOutput='',lastAssistantTurn='',lastStateKey='',inputDebounce,outputDebounce,outputNode=null,sequence=0,startedMono=0,closingMono=0,confirmationTurn=null;const audioSources=new Set();
 const mount=()=>document.getElementById('discoveryMount');
 function ensureMount(){if(!mount()){const d=document.createElement('div');d.id='discoveryMount';document.body.appendChild(d);}}
 function status(text){const node=document.getElementById('discoveryStatus');if(node)node.textContent=text;}
 function checklist(){const node=document.getElementById('discoveryChecklist');if(node)node.innerHTML=P.ESSENTIAL.map(id=>`<li><span>${esc(labels[id])}</span><b class="discovery-${profile.fields[id].status}">${{pending:'Pendente',confirmed:'Registrado',uncertain:'Incerto',unknown:'Não informado'}[profile.fields[id].status]}</b></li>`).join('');}
 function line(who,text){const list=document.getElementById('discoveryTranscript');if(!list)return null;const p=document.createElement('p');const b=document.createElement('strong');const content=document.createTextNode(text);b.textContent=who+': ';p.append(b,content);list.appendChild(p);list.scrollTop=list.scrollHeight;return content;}
 function joinTranscript(current,fragment){const next=String(fragment||'').trim();if(!next)return current;if(!current||next.startsWith(current))return next;if(current.startsWith(next)||current.endsWith(next))return current;return current+(/^[.,!?;:%)\]]/.test(next)?'':' ')+next;}
 function interviewState(clarify=false){return {fields:Object.fromEntries(P.ESSENTIAL.map(id=>[id,profile.fields[id].status])),closing,clarify,intro_complete:sequence>0,confirmation_attempted:interview?.confirmation_attempted===true};}
 function sendState(clarify=false){if(ws?.readyState!==WebSocket.OPEN||!interview)return;const state=interviewState(clarify),key=JSON.stringify(state);if(key===lastStateKey)return;lastStateKey=key;ws.send(JSON.stringify({interviewState:state}));}
 function missingFields(){return P.ESSENTIAL.filter(id=>profile.fields[id].status==='pending');}
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
 async function open(){property=window.AgrionPropertyStore.read();if(!property?.geometry)return;ensureMount();profile=await R.getByPropertyId(property.propertyId)||P.create(property);await R.put('agricultural_profiles',profile);mount().innerHTML=`<div class="discovery-backdrop"><section class="discovery-card" role="dialog" aria-modal="true" aria-labelledby="discoveryTitle"><header><div><small>AGRION DISCOVERY</small><h2 id="discoveryTitle">Vamos conversar sobre sua lavoura</h2></div><button id="discoveryClose" type="button" aria-label="Fechar">×</button></header><p>Conte sua experiência. Suas respostas ficam neste navegador e ajudam a preparar análises futuras.</p><label for="discoveryLanguage">Idioma da conversa</label><select id="discoveryLanguage"><option value="pt-BR">Português (Brasil)</option><option value="en-US">English</option><option value="es-ES">Español</option></select><div class="discovery-modes"><button id="discoveryVoice" class="btn btn-primary" type="button">Conversar por voz</button><button id="discoveryText" class="btn btn-secondary" type="button">Conversar por texto</button></div><p id="discoveryStatus" role="status">Escolha como deseja conversar.</p><div id="discoveryTranscript" class="discovery-transcript" aria-live="polite"></div><form id="discoveryForm" hidden><label for="discoveryInput">Sua resposta</label><textarea id="discoveryInput" rows="3" maxlength="3000" placeholder="Conte sobre sua lavoura"></textarea><button class="btn btn-primary" type="submit">Enviar</button></form><h3>O que já foi registrado</h3><ul id="discoveryChecklist" class="discovery-checklist"></ul><p class="discovery-privacy"><label><input type="checkbox" id="discoveryConsent"> Guardar texto pendente para tentar extrair depois, se a conexão falhar</label></p><button id="discoveryFinish" class="btn btn-secondary" type="button" hidden>Encerrar conversa</button></section></div>`;checklist();
 lastAssistantTurn='';pendingInput='';lastStateKey='';closing=false;finalizing=false;farewellStarted=false;closingSignalSent=false;closePromptPending=false;modelTurnActive=false;lastModelFrameMono=0;clarificationPending=false;confirmationTurn=null;sequence=0;finishOutput();
 document.getElementById('discoveryLanguage').insertAdjacentHTML('afterend',`<label for="discoveryVoiceChoice">Voz do Agrion</label><select id="discoveryVoiceChoice"><option value="">Padrão do modelo</option>${VOICES.map(voice=>`<option value="${voice}">${voice}</option>`).join('')}</select>`);
 document.getElementById('discoveryLanguage').querySelector('option[value="es-ES"]').value='es-US';
 document.getElementById('discoveryClose').onclick=()=>finish('user_request');document.getElementById('discoveryFinish').onclick=()=>requestClose('user_request');document.getElementById('discoveryVoice').onclick=()=>start('voice');document.getElementById('discoveryText').onclick=()=>start('text');document.getElementById('discoveryForm').onsubmit=e=>{e.preventDefault();const input=document.getElementById('discoveryInput');const text=input.value.trim();if(text){input.value='';line('Você',text);sendText(text);extract(text);}};
 retryPending().catch(()=>status('Algumas respostas aguardam análise. Os dados já registrados permanecem salvos.'));
 }
 async function start(mode){if(interview?.status==='in_progress')return;const now=new Date().toISOString();startedMono=0;closingMono=0;interview={schema_version:'1.0.0',interview_id:crypto.randomUUID(),profile_id:profile.profile_id,property_id:property.propertyId,status:'in_progress',mode,language:document.getElementById('discoveryLanguage').value,voice:document.getElementById('discoveryVoiceChoice').value,started_at:null,created_at:now,updated_at:now,closing_requested_at:null,finished_at:null,duration_seconds:null,completion_reason:null,farewell_delivered:false,confirmation_attempted:false,essential_field_counts:{},processed_turn_ids:[],pending_extraction_turn_ids:[],errors:[]};await R.put('interviews',interview);profile.interview_history.push(interview.interview_id);await R.put('agricultural_profiles',profile);document.getElementById('discoveryVoice').disabled=true;document.getElementById('discoveryText').disabled=true;document.getElementById('discoveryLanguage').disabled=true;document.getElementById('discoveryVoiceChoice').disabled=true;document.getElementById('discoveryFinish').hidden=false;document.getElementById('discoveryForm').hidden=false;document.getElementById('discoveryForm').querySelector('textarea').focus();status('Conectando ao Agrion…');try{await connectLive();if(!interview)return;startedMono=performance.now();interview.started_at=new Date().toISOString();await R.put('interviews',interview);timer=setInterval(tick,500);if(mode==='voice')await startMicrophone();sendState();sendText(OPENING_PROMPTS[interview.language]||OPENING_PROMPTS['pt-BR']);status(mode==='voice'?'Microfone ativo. Pode falar e interromper o Agrion.':'Conversa por texto iniciada.');}catch(err){if(!interview)return;if(!startedMono){startedMono=performance.now();interview.started_at=new Date().toISOString();timer=setInterval(tick,500);}interview.errors.push('live_connection_failed');status(err.message.startsWith('live_rate_limited')?'Limite de conexões por hora atingido. Tente novamente mais tarde.':err.message.startsWith('origin_rejected')?'A origem da conexão foi recusada pelo servidor.':err.message.startsWith('vertex_not_configured')?'Vertex AI não está configurado no servidor.':(err.message.startsWith('vertex_unavailable')||err.message.startsWith('vertex_connection_closed'))?'Não foi possível conectar ao Vertex AI. Verifique os logs do servidor.':'Não foi possível abrir o WebSocket. Verifique o proxy HTTPS e tente novamente.');if(mode==='voice'){interview.mode='text';await stopMicrophone();}await R.put('interviews',interview);}}
 async function connectLive(){
   return new Promise((resolve,reject)=>{
     const url=(location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/api/interview/live-session';
     ws=new WebSocket(url);
     let ready=false, settled=false;
     const fail=reason=>{if(settled)return;settled=true;clearTimeout(timeout);reject(new Error(reason));};
     const timeout=setTimeout(()=>{fail('live_timeout');ws.close();},15000);
     ws.onopen=()=>ws.send(JSON.stringify({interview_id:interview.interview_id,property_id:property.propertyId,person_name:property.personName,property_name:property.propertyName,language:interview.language,voice:interview.voice}));
     ws.onerror=()=>{if(!ready)fail('websocket_handshake_failed');};
     ws.onclose=event=>{if(!ready)fail(`websocket_closed_${event.code}`);else if(interview?.status==='in_progress')status('Conexão por voz interrompida. Você pode continuar por texto.');};
     ws.onmessage=async event=>{
       let message;
       try{
         const raw=typeof event.data==='string' ? event.data : event.data instanceof Blob ? await event.data.text() : new TextDecoder().decode(event.data);
         message=JSON.parse(raw);
       }catch(_){fail('invalid_live_message');return;}
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
   if(t){pendingInput+=t;clearTimeout(inputDebounce);inputDebounce=setTimeout(flushInput,1100);}
   if(inputTranscription?.finished&&pendingInput)flushInput();
   const outputTranscription=msg.outputTranscription||content?.outputTranscription;
   if(outputTranscription?.text){modelTurnActive=true;lastModelFrameMono=performance.now();if(closing&&closingSignalSent)farewellStarted=true;pendingOutput=joinTranscript(pendingOutput,outputTranscription.text);lastAssistantTurn=pendingOutput.slice(-1000);if(!outputNode)outputNode=line('Agrion',pendingOutput);else outputNode.nodeValue=pendingOutput;clearTimeout(outputDebounce);outputDebounce=setTimeout(finishOutput,2500);}
   if(outputTranscription?.finished)finishOutput();
   if(content?.interrupted){finishOutput();for(const source of audioSources){try{source.stop();}catch(_){}}audioSources.clear();playAt=0;}
   if(content?.modelTurn?.parts)for(const part of content.modelTurn.parts){modelTurnActive=true;lastModelFrameMono=performance.now();if(part.inlineData?.data){if(closing&&closingSignalSent)farewellStarted=true;playAudio(part.inlineData.data);}if(part.text&&!outputTranscription&&!pendingOutput){if(closing&&closingSignalSent)farewellStarted=true;line('Agrion',part.text);}}
   if(content?.turnComplete){modelTurnActive=false;if(closing&&closePromptPending&&!closingSignalSent)sendClosePrompt();else if(closing&&closingSignalSent&&farewellStarted){const delay=audioContext?Math.max(0,(playAt-audioContext.currentTime)*1000):0;setTimeout(()=>{if(interview?.status==='in_progress')finish(interview.completion_reason||'time_limit',true);},delay+50);}}
   if(msg.toolCall?.functionCalls)void handleToolCalls(msg.toolCall.functionCalls);
 }
 async function handleToolCalls(calls){
   await Promise.race([queue.catch(()=>{}),new Promise(resolve=>setTimeout(resolve,5000))]);
   const responses=[];let accepted=false;
   for(const call of calls){
     if(call.name==='get_interview_state')responses.push({id:call.id,name:call.name,response:{status:'ok',retryable:false,message:'Use os campos pendentes para escolher a próxima pergunta.',...interviewState(),pending_fields:missingFields(),uncertain_fields:P.ESSENTIAL.filter(id=>profile.fields[id].status==='uncertain')}});
     if(call.name==='complete_initial_interview'){
       const pending=missingFields(),uncertain=P.ESSENTIAL.filter(id=>profile.fields[id].status==='uncertain');
       const allowed=closing||(!pending.length&&(!uncertain.length||interview?.confirmation_attempted));
       if(!allowed&&uncertain.length&&!pending.length&&confirmationTurn===null)confirmationTurn=sequence;
       responses.push({id:call.id,name:call.name,response:allowed?{status:'ok',retryable:false,message:'Conclusão autorizada. Despeça-se brevemente.',accepted:true,next_action:'say_short_farewell'}:{status:'incomplete',retryable:false,message:'Ainda há uma informação a esclarecer com o agricultor.',accepted:false,next_action:pending.length?'ask_one_missing_essential_question':'confirm_uncertainty_once',missing_fields:pending,uncertain_fields:uncertain}});
       accepted=accepted||allowed;
     }
   }
   if(responses.length&&ws?.readyState===WebSocket.OPEN)ws.send(JSON.stringify({toolResponse:{functionResponses:responses}}));
   if(accepted&&!closing)requestClose('essential_fields_complete',false);
 }
 function flushInput(){clearTimeout(inputDebounce);inputDebounce=null;const text=pendingInput.trim();pendingInput='';if(text){modelTurnActive=true;line('Você',text);extract(text);}}
 function finishOutput(){clearTimeout(outputDebounce);outputDebounce=null;pendingOutput='';outputNode=null;}
 function extract(text){
   const activeInterview=interview,assistantContext=lastAssistantTurn.slice(-1000);
   if(!activeInterview)return;
   const turnId=crypto.randomUUID(),seq=++sequence;
   queue=queue.catch(()=>{}).then(async()=>{
     const body={interview_id:activeInterview.interview_id,property_id:property.propertyId,turn_id:turnId,sequence:seq,speaker:'farmer',transcript:text,assistant_context:assistantContext,profile_revision:profile.revision,profile_snapshot:{fields:Object.fromEntries(P.ESSENTIAL.map(id=>[id,{status:profile.fields[id].status,value:profile.fields[id].value}]))}};
     try{
       const res=await fetch('/api/interview/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
       if(!res.ok)throw Error('extraction');
       const data=await res.json(),result=P.apply(profile,data,text);
       const revisions=result.applied.map(x=>({...x,revision_id:crypto.randomUUID(),turn_id:turnId,interview_id:activeInterview.interview_id,created_at:new Date().toISOString()}));
       profile=result.profile;activeInterview.processed_turn_ids.push(turnId);activeInterview.updated_at=new Date().toISOString();
       if(confirmationTurn!==null&&seq>confirmationTurn)activeInterview.confirmation_attempted=true;
       await R.savePatch(profile,revisions,activeInterview);checklist();
       if(interview===activeInterview){
         const pending=missingFields(),uncertain=P.ESSENTIAL.filter(id=>profile.fields[id].status==='uncertain');
         if(!pending.length&&uncertain.length&&!activeInterview.confirmation_attempted&&confirmationTurn===null)confirmationTurn=seq;
         const clarify=!result.applied.length&&seq>1&&!!assistantContext&&!clarificationPending;
         if(result.applied.length)clarificationPending=false;
         else if(clarify)clarificationPending=true;
         sendState(clarify);
         if(!pending.length&&(!uncertain.length||activeInterview.confirmation_attempted))requestClose('essential_fields_complete');
       }
     }catch(err){
       activeInterview.errors.push('extraction_failed');
       if(document.getElementById('discoveryConsent')?.checked){await R.put('pending_extractions',{turn_id:turnId,interview_id:activeInterview.interview_id,property_id:property.propertyId,sequence:seq,transcript:text,assistant_context:assistantContext});activeInterview.pending_extraction_turn_ids.push(turnId);}
       await R.put('interviews',activeInterview);status('Não foi possível analisar esta resposta agora. Você pode continuar.');
     }
   });
 }
 function tick(){if(!interview||interview.status!=='in_progress')return;const now=performance.now(),elapsed=(now-startedMono)/1000;if(elapsed>=LIMITS.absolute||closingMono&&now-closingMono>=LIMITS.grace*1000)finish('safety_timeout');else if(closing&&closePromptPending&&!closingSignalSent&&now-closingMono>=20000&&now-lastModelFrameMono>=20000&&(!audioContext||playAt<=audioContext.currentTime))sendClosePrompt();else if(elapsed>=LIMITS.normal&&!closing)requestClose('time_limit');}
 function sendClosePrompt(){if(!closePromptPending||closingSignalSent||ws?.readyState!==WebSocket.OPEN)return;closePromptPending=false;closingSignalSent=true;sendText('CLOSE_REQUESTED. Agradeça brevemente e encerre agora, sem novas perguntas.');}
 function requestClose(reason,signal=true){if(closing||!interview||interview.status!=='in_progress')return;closing=true;farewellStarted=false;closingSignalSent=!signal;closePromptPending=signal;closingMono=performance.now();interview.closing_requested_at=new Date().toISOString();interview.completion_reason=reason;R.put('interviews',interview);status('Encerrando a conversa…');sendState();if(signal&&!modelTurnActive)sendClosePrompt();if(!ws||ws.readyState!==WebSocket.OPEN)finish(reason);}
 async function finish(reason='user_request',farewell=false){if(!interview){mount()?.remove();return;}if(interview.status!=='in_progress'||finalizing)return;finalizing=true;clearInterval(timer);clearTimeout(inputDebounce);finishOutput();if(pendingInput)flushInput();await Promise.race([queue,new Promise(resolve=>setTimeout(resolve,4000))]);await stopMicrophone();ws?.close();interview.status=reason==='user_request'?'cancelled':reason==='safety_timeout'||reason==='time_limit'||reason==='farewell_timeout'?'partial':'completed';interview.finished_at=new Date().toISOString();interview.updated_at=interview.finished_at;interview.duration_seconds=startedMono?Math.round((performance.now()-startedMono)/1000):0;interview.completion_reason=reason;interview.farewell_delivered=farewell;interview.essential_field_counts=Object.fromEntries(['pending','confirmed','uncertain','unknown'].map(s=>[s,P.ESSENTIAL.filter(id=>profile.fields[id].status===s).length]));await R.put('interviews',interview);interview=null;closing=false;finalizing=false;mount()?.remove();}
 async function startMicrophone(){micStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});audioContext=new AudioContext({sampleRate:16000});micSource=audioContext.createMediaStreamSource(micStream);processor=audioContext.createScriptProcessor(2048,1,1);processor.onaudioprocess=e=>{if(ws?.readyState!==WebSocket.OPEN)return;const input=e.inputBuffer.getChannelData(0),pcm=new Int16Array(input.length);for(let i=0;i<input.length;i++)pcm[i]=Math.max(-32768,Math.min(32767,input[i]*32767));let binary='';const bytes=new Uint8Array(pcm.buffer);for(let i=0;i<bytes.length;i++)binary+=String.fromCharCode(bytes[i]);ws.send(JSON.stringify({realtimeInput:{mediaChunks:[{mimeType:'audio/pcm;rate=16000',data:btoa(binary)}]}}));};micSource.connect(processor);processor.connect(audioContext.destination);}
 function playAudio(base64){if(!audioContext)return;const binary=atob(base64),count=binary.length/2,buffer=audioContext.createBuffer(1,count,24000),samples=buffer.getChannelData(0);for(let i=0;i<count;i++){let v=binary.charCodeAt(i*2)|(binary.charCodeAt(i*2+1)<<8);if(v>32767)v-=65536;samples[i]=v/32768;}const source=audioContext.createBufferSource();source.buffer=buffer;source.connect(audioContext.destination);source.onended=()=>audioSources.delete(source);audioSources.add(source);playAt=Math.max(playAt,audioContext.currentTime);source.start(playAt);playAt+=buffer.duration;}
 async function stopMicrophone(){processor?.disconnect();micSource?.disconnect();micStream?.getTracks().forEach(t=>t.stop());for(const source of audioSources){try{source.stop();}catch(_){}}audioSources.clear();if(audioContext){await audioContext.close();audioContext=null;}playAt=0;}
 function invite(){if(!window.AgrionPropertyStore.read()?.geometry)return;ensureMount();mount().innerHTML='<div class="discovery-backdrop"><section class="discovery-card" role="dialog" aria-modal="true"><h2>Propriedade cadastrada!</h2><p>Quer contar um pouco sobre suas safras para preparar seu perfil agrícola?</p><div class="discovery-modes"><button id="discoveryInviteYes" class="btn btn-primary">Conversar com Agrion</button><button id="discoveryInviteSkip" class="btn btn-secondary">Agora não</button></div></section></div>';document.getElementById('discoveryInviteYes').onclick=()=>open().catch(()=>mount().remove());document.getElementById('discoveryInviteSkip').onclick=()=>mount().remove();}
 window.AgrionDiscovery={open:()=>open().catch(()=>{}),invite};
})();
