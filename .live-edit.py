from pathlib import Path
p=Path('app/static/discovery.js');s=p.read_text(encoding='utf-8')
s=s.replace('const P=window.AgrionProfile,R=window.AgrionRepository;', 'const P=window.AgrionProfile,R=window.AgrionRepository,I=window.AgrionInterviewLanguage;')
s=s.replace("last_crop:'Última cultura',previous_crop:'Cultura anterior'", "last_crop:'Cultura anterior'")
s=s.replace("completed=false;const audioSources", "completed=false,languageLocked=false,languageChanging=false;const audioSources")
s=s.replace('node.textContent=text;', 'node.textContent=I.t(text);',1)
s=s.replace("&&!(id==='last_harvest_result'&&needsEstimate())", '')
s=s.replace('`${value}% concluído`', "`${value}% ${I.get()==='en-US'?'complete':'concluído'}`")
language='<div class="discovery-language"><label for="discoveryLanguage">Idioma da conversa</label><select id="discoveryLanguage"><option value="pt-BR">Português (Brasil)</option><option value="en-US">English</option></select><small id="discoveryLanguageHint"></small></div>'
old='<label for="discoveryLanguage">Idioma da conversa</label><select id="discoveryLanguage"><option value="pt-BR">Português (Brasil)</option><option value="en-US">English</option><option value="es-US">Español</option></select>'
s=s.replace(old,'').replace('${manual?window.AgrionManual.markup(profile)',language+'${manual?window.AgrionManual.markup(profile)')
s=s.replace('<strong>Olá, ${esc(property?.personName', "<strong>${I.get()==='en-US'?'Hello':'Olá'}, ${esc(property?.personName")
s=s.replace('   checklist();\n   if(view', '''   checklist();I.translate(document.querySelector('.discovery-shell'));
   const languageSelect=document.getElementById('discoveryLanguage');languageSelect.value=I.get();syncLanguageControl();languageSelect.onchange=()=>{void changeLanguage(languageSelect.value);};
   if(view''',1)
a=s.index("   if(view==='manual'){const form=");b=s.index("   document.getElementById('discoveryManual')",a)
s=s[:a]+'''   if(view==='manual'){
     const form=document.getElementById('discoveryManualForm');form.onsubmit=saveManual;
     form.addEventListener('input',lockLanguage);
     const never=form.elements.no_previous_cultivation,notPlanted=form.elements.not_planted;
     const toggle=()=>{for(const id of ['last_crop','harvest_result'])form.elements[id].closest('.discovery-field').hidden=never.checked;form.elements.planting_date.closest('.discovery-field').hidden=notPlanted.checked;};
     never.onchange=toggle;notPlanted.onchange=toggle;toggle();return;
   }
'''+s[b:]
s=s.replace("function beginTurn(speaker,text,before=null){const turn=", "function beginTurn(speaker,text,before=null){if(speaker==='farmer'&&text)lockLanguage();const turn=")
s=s.replace("speaker==='farmer'?'Você':'Agrion'", "speaker==='farmer'?I.t('Você'):'Agrion'")
a=s.index(' function needsEstimate()');b=s.index(' function interviewState',a);s=s[:a]+s[b:]
s=s.replace('harvest_estimate_pending:!!needsEstimate(),','')
a=s.index(' function missingFields()');b=s.index(' function uncertainFields()',a);s=s[:a]+" function missingFields(){return P.ESSENTIAL.filter(id=>profile.fields[id].status==='pending');}\n"+s[b:]
s=s.replace("first_cultivation:profile.fields.last_crop.value?.never_cultivated===true", "first_cultivation:profile.fields.last_crop.value?.never_cultivated===true||profile.fields.last_crop.value?.no_previous_cultivation===true")
# Initialize language before rendering; preserve language on profiles with answers.
old="manualSession=null;clearTimeout(autoTimer);window.AgrionHome.reset();"
new="manualSession=null;languageLocked=P.ESSENTIAL.some(id=>profile.fields[id].status!=='pending');const previousSession=sessions.filter(x=>x.property_id===property.propertyId).sort((a,b)=>(b.updated_at||'').localeCompare(a.updated_at||''))[0];if(languageLocked&&I.valid(profile.interview_language||previousSession?.language))I.set(profile.interview_language||previousSession.language,false);clearTimeout(autoTimer);window.AgrionHome.reset();"
assert old in s;s=s.replace(old,new,1)
s=s.replace("language:document.getElementById('discoveryLanguage').value,voice:'Orus'", "language:I.get(),voice:I.get()==='pt-BR'?'Orus':null")
s=s.replace("document.getElementById('discoveryLanguage').disabled=true;", 'syncLanguageControl();')
s=s.replace("document.getElementById('discoveryLanguage').disabled=false;", 'syncLanguageControl();')
s=s.replace("if(t){if(!inputTurn)", "if(t){lockLanguage();if(!inputTurn)")
# Use the session and socket captured for each connection, including after Blob decoding.
s=s.replace('     ws=new WebSocket(url);', '     const active=interview,socket=new WebSocket(url);ws=socket;')
s=s.replace("fail('live_timeout');ws.close();", "fail('live_timeout');socket.close();")
s=s.replace('     ws.onopen=()=>ws.send(JSON.stringify({interview_id:interview.interview_id,property_id:property.propertyId,person_name:property.personName,property_name:property.propertyName,language:interview.language,voice:interview.voice}));', '     socket.onopen=()=>{if(interview!==active||ws!==socket){socket.close();return;}socket.send(JSON.stringify({interview_id:active.interview_id,property_id:property.propertyId,person_name:property.personName,property_name:property.propertyName,language:active.language,voice:active.voice}));};')
s=s.replace('     ws.onerror=', '     socket.onerror=').replace('     ws.onclose=', '     socket.onclose=').replace('     ws.onmessage=', '     socket.onmessage=')
s=s.replace("else if(interview?.status==='in_progress'&&!finalizing&&!closing)", "else if(interview===active&&ws===socket&&interview?.status==='in_progress'&&!finalizing&&!closing)")
s=s.replace('       if(message.setupComplete)', '       if(interview!==active||ws!==socket)return;\n       if(message.setupComplete)')
s=s.replace("if(mode==='voice')await startMicrophone();", "if(mode==='voice')await startMicrophone(active);")
s=s.replace("async function startMicrophone(){micStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});", "async function startMicrophone(active){const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});if(interview!==active||view!=='voice'){stream.getTracks().forEach(t=>t.stop());return;}micStream=stream;")
# Manual save: continuing is explicit and does not invent answers to blank questions.
s=s.replace('const form=event.currentTarget,error=', "const continueAnalysis=event.submitter?.value!=='save';const form=event.currentTarget,error=")
s=s.replace('error.textContent=problem.message;', 'error.textContent=I.t(problem.message);')
s=s.replace("if(!entries.length){error.textContent='Preencha pelo menos uma resposta antes de salvar.';error.hidden=false;return;}", '')
s=s.replace("language:'pt-BR',voice:null", "language:I.get(),voice:null")
s=s.replace('   const result=P.applyManual(profile,entries);', "   if(continueAnalysis)for(const id of P.ESSENTIAL)if(profile.fields[id].status==='pending'&&!entries.some(e=>e.field===id))entries.push({field:id,status:'unknown',value:null,unknown_reason:'declined'});\n   profile.interview_language=I.get();const result=P.applyManual(profile,entries);")
s=s.replace("const ready=P.ESSENTIAL.every(id=>profile.fields[id].status!=='pending'&&profile.fields[id].status!=='uncertain')&&!needsEstimate();", 'const ready=continueAnalysis;')
s=s.replace("manualSession.completion_reason='essential_fields_complete';", "manualSession.completion_reason=P.ready(profile)?'essential_fields_complete':'preliminary_analysis';")
s=s.replace("error.textContent='Não foi possível salvar agora. Tente novamente.'", "error.textContent=I.t('Não foi possível salvar agora. Tente novamente.')")
# Control changes only before any input; do not reuse finish() which changes completion state/view.
pos=s.index(' function line(')
s=s[:pos]+''' function syncLanguageControl(){const select=document.getElementById('discoveryLanguage');if(select){select.disabled=languageLocked||languageChanging;select.value=I.get();}const hint=document.getElementById('discoveryLanguageHint');if(hint)hint.textContent=languageLocked?I.t('Idioma definido após a primeira resposta.'):'';}
 function lockLanguage(){languageLocked=true;if(profile)profile.interview_language=I.get();syncLanguageControl();}
 async function changeLanguage(language){
   if(languageLocked||languageChanging||!I.valid(language)){syncLanguageControl();return;}
   languageChanging=true;syncLanguageControl();clearTimeout(autoTimer);autoTimer=null;
   const old=interview;interview=null;const socket=ws;ws=null;
   clearInterval(timer);clearTimeout(inputDebounce);clearTimeout(outputDebounce);socket?.close();
   try{
     await stopMicrophone();
     if(old){old.status='partial';old.completion_reason='language_changed';old.finished_at=new Date().toISOString();old.updated_at=old.finished_at;await R.put('interviews',old);}
     I.set(language);pendingInput='';pendingOutput='';lastAssistantTurn='';lastStateKey='';inputTurn=null;outputTurn=null;outputNode=null;inputQuestion='';sequence=0;introStage=0;modelTurnActive=false;closing=false;finalizing=false;farewellStarted=false;closingSignalSent=false;closePromptPending=false;lastModelFrameMono=0;lastModelTurnMono=0;clarificationPending=false;confirmationState='none';recoveryPrompts=0;turnHistory.length=0;reviewedKeys.clear();
     window.render();
   }catch(_){status('Não foi possível iniciar a voz. Tente novamente ou responda manualmente.');}
   finally{languageChanging=false;syncLanguageControl();}
   if(view==='voice')await start('voice');
 }
'''+s[pos:]
p.write_text(s,encoding='utf-8')
