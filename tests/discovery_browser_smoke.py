"""Isolated UI/Live lifecycle tests. No microphone or Google calls are made."""
import runpy
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
runpy.run_path(str(root/'tests/planning_browser_smoke.py'))
output=Path(sys.argv[1]);html=output.read_text(encoding='utf-8')
css=(root/'app/static/discovery.css').read_text(encoding='utf-8')
setup=r'''
localStorage.removeItem('agrion-interview-language-v1');localStorage.removeItem('agrion-ui-language-v1');Object.defineProperty(navigator,'language',{get:()=> 'pt-BR'});Object.defineProperty(navigator,'languages',{get:()=>['pt-BR']});
const errors=[],sockets=[],stopped=[];let delayMic=false,micGrant=null;window.onerror=m=>errors.push(m);
const stores=new Map();function db(name){if(!stores.has(name))stores.set(name,new Map());return stores.get(name)}
const keys={agricultural_profiles:'property_id',interviews:'interview_id',pending_extractions:'turn_id'};
const prop={propertyId:crypto.randomUUID(),personName:'Teste',propertyName:'Área de teste',geometry:{},areaHectares:1};
window.AGRION_CONFIG={interviewLimits:{normal:1000,absolute:1500,grace:30}};
window.AgrionPropertyStore={read:()=>prop};
window.AgrionRepository={get:async(n,k)=>structuredClone(db(n).get(k)),put:async(n,v)=>{db(n).set(v[keys[n]],structuredClone(v));return v},all:async n=>[...db(n).values()].map(v=>structuredClone(v)),remove:async(n,k)=>db(n).delete(k),getByPropertyId:async k=>structuredClone(db('agricultural_profiles').get(k)),savePatch:async(p,r,i)=>{db('agricultural_profiles').set(p.property_id,structuredClone(p));db('interviews').set(i.interview_id,structuredClone(i))}};
window.AgrionHome={reset:()=>{},markup:()=>'<main id="home">Analysis ready</main>',afterRender:()=>{}};
window.render=()=>{document.getElementById('app').innerHTML=window.AgrionDiscovery.markup();window.AgrionDiscovery.afterRender()};
class Socket{static OPEN=1;constructor(){this.readyState=0;this.sent=[];sockets.push(this);setTimeout(()=>{this.readyState=1;this.onopen?.()},5)}send(data){this.sent.push(JSON.parse(data))}close(){this.readyState=3;setTimeout(()=>this.onclose?.({code:1000}),0)}emit(data){this.onmessage?.({data:JSON.stringify(data)})}}
window.WebSocket=Socket;
class Audio{constructor(){this.currentTime=0;this.destination={}}createMediaStreamSource(){return {connect(){},disconnect(){}}}createScriptProcessor(){return {connect(){},disconnect(){}}}createBuffer(n,size,rate){return {duration:size/rate,getChannelData:()=>new Float32Array(size)}}createBufferSource(){return {connect(){},start(){},stop(){stopped.push('audio')}}}async close(){stopped.push('context')}}window.AudioContext=Audio;
Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>delayMic?new Promise(resolve=>{micGrant=()=>resolve({getTracks:()=>[{stop:()=>stopped.push('late mic')}]})}):({getTracks:()=>[{stop:()=>stopped.push('mic')}]})}});
let noExtractedFacts=false;
window.fetch=async(url,options)=>{const body=JSON.parse(options.body);return {ok:true,json:async()=>({base_profile_revision:body.profile_revision,turn_id:body.turn_id,patches:noExtractedFacts?[]:[{field:'current_crop',operation:'set',status:'confirmed',value:{crop:'corn'},confidence:'high',evidence_excerpt:'corn'}]})}};
'''
scripts='\n'.join((root/'app/static'/n).read_text(encoding='utf-8') for n in ['agrion-locale.js','discovery-profile.js','discovery-language.js','discovery-manual.js','agrion-context.js','discovery.js'])
test=r'''
const wait=ms=>new Promise(r=>setTimeout(r,ms));function check(ok,m){if(!ok)throw Error(m)}
async function until(fn){for(let i=0;i<200;i++){if(fn())return;await wait(10)}throw Error('wait timeout')}
function choose(language){const s=document.getElementById('discoveryLanguage');s.value=language;s.dispatchEvent(new Event('change'))}
async function manual(){document.getElementById('discoveryManual').click();await until(()=>document.getElementById('discoveryManualForm'))}
function set(name,value){const form=document.getElementById('discoveryManualForm'),n=form.elements[name];if(n.type==='checkbox')n.checked=value;else n.value=value;n.dispatchEvent(new Event('input',{bubbles:true}));n.dispatchEvent(new Event('change',{bubbles:true}));return n}
function submit(action='continue'){const form=document.getElementById('discoveryManualForm');form.dispatchEvent(new SubmitEvent('submit',{cancelable:true,submitter:form.querySelector(`[value="${action}"]`)}))}
const stored=()=>db('agricultural_profiles').get(prop.propertyId);
async function newManual(profile){prop.propertyId=crypto.randomUUID();if(profile){profile.property_id=prop.propertyId;db('agricultural_profiles').set(prop.propertyId,profile)}await window.AgrionDiscovery.open();await manual()}
(async()=>{try{
const P=window.AgrionProfile,I=window.AgrionInterviewLanguage;
check(I.detect(['pt-PT'])==='en-US'&&I.detect(['en-GB'])==='en-US'&&I.detect(['fr-FR'])==='en-US','browser locale');
await window.AgrionDiscovery.open();check(document.getElementById('discoveryLanguage').value==='pt-BR','initial language');
window.AgrionLocale.set('en-US');await until(()=>sockets.length===1&&sockets[0].sent.length);const first=sockets[0];check(first.sent[0].language==='en-US'&&first.sent[0].voice===null,'global English starts English voice');
choose('pt-BR');await until(()=>sockets.length===2&&sockets[1].sent.length);const second=sockets[1];
first.emit({setupComplete:{}});first.emit({inputTranscription:{text:'stale input',finished:true}});
check(!document.getElementById('discoveryLanguage').disabled,'old events ignored');
check(second.sent[0].voice==='Orus','portuguese voice');second.emit({setupComplete:{}});await wait(50);
second.emit({serverContent:{modelTurn:{parts:[{inlineData:{data:'AAAAAA=='}}]}}});
choose('en-US');await until(()=>sockets.length===3&&sockets[2].sent.length);check(stopped.includes('audio')&&stopped.includes('mic'),'stop old audio');
sockets[2].emit({setupComplete:{}});await wait(50);
delayMic=true;choose('pt-BR');await until(()=>sockets.length===4&&sockets[3].sent.length);sockets[3].emit({setupComplete:{}});await until(()=>micGrant);delayMic=false;choose('en-US');await until(()=>sockets.length===5&&sockets[4].sent.length);const active=sockets[4];active.emit({setupComplete:{}});await wait(50);micGrant();await until(()=>stopped.includes('late mic'));
active.emit({inputTranscription:{text:'corn',finished:true}});await until(()=>stored().fields.current_crop.value?.crop==='corn');
check(document.getElementById('discoveryLanguage').disabled,'lock after answer');choose('pt-BR');await wait(50);check(sockets.length===5&&I.get()==='en-US','reject language change after answer');
await manual();check(document.querySelector('[name="current_crop"]').value==='corn','voice to manual');check(!document.querySelector('[name="previous_crop"]'),'no third crop');check(document.body.textContent.includes('Save and continue to analysis'),'english form');for(const phrase of ['Não sei informar','Preencha o que souber','Cultura anterior','Irrigação','Quantidade aproximada'])check(!document.getElementById('discoveryManualForm').textContent.includes(phrase),'untranslated form: '+phrase);
window.AgrionLocale.set('pt-BR');check(document.body.textContent.includes('Salvar e continuar para análise'),'Portuguese interface after voice lock');check(document.getElementById('discoveryManualForm').textContent.includes('Não sei informar'),'original Portuguese choices restored');check(document.getElementById('discoveryProgressText').textContent.includes('concluído'),'Portuguese progress');check(I.get()==='en-US'&&document.getElementById('discoveryLanguage').disabled,'voice stays English');check(document.getElementById('discoveryLanguageHint').textContent.includes('English'),'fixed voice hint');window.AgrionLocale.set('en-US');check(document.body.textContent.includes('Save and continue to analysis'),'English interface restored');check(document.getElementById('discoveryProgressText').textContent.includes('complete'),'English progress');
set('harvest_result','good');submit();await until(()=>document.getElementById('home'));check(stored().fields.last_harvest_result.value.qualitative_result==='good','qualitative sufficient');check(stored().fields.current_crop.source==='farmer_report','unchanged voice source preserved');check(stored().fields.irrigation.unknown_reason==='declined','unprovided blank');
await newManual();submit();await until(()=>document.getElementById('home'));check(P.ready(stored()),'empty form can continue');
await newManual();set('harvest_quantity','0');submit();await wait(50);check(!document.getElementById('discoveryManualError').hidden,'unit validation');set('last_harvest_result_unknown',true);submit();await until(()=>document.getElementById('home'));check(stored().fields.last_harvest_result.status==='unknown','unknown bypasses numeric validation');
await newManual();set('harvest_result','average');set('harvest_quantity','12');set('estimate_unavailable',true);submit();await until(()=>document.getElementById('home'));check(stored().fields.last_harvest_result.value.qualitative_result==='average'&&!('quantity' in stored().fields.last_harvest_result.value),'skip incomplete number');
await newManual();set('not_planted',true);set('no_previous_cultivation',true);set('planting_date','invalid');submit();await until(()=>document.getElementById('home'));check(stored().fields.current_crop.value.not_planted&&stored().fields.planting_date.value.not_planted,'known no crop');check(stored().fields.last_harvest_result.value.qualitative_result==='not_applicable','no previous harvest');
const legacy=P.create(prop);legacy.fields.previous_crop={status:'confirmed',value:{crop:'legacy'},evidence:[]};legacy.fields.mechanization={...legacy.fields.mechanization,status:'uncertain',value:{work_mode:'mixed',equipment:['tractor'],automation_level:'partial'},source:'farmer_report'};
await newManual(legacy);submit();await until(()=>document.getElementById('home'));check(stored().fields.previous_crop.value.crop==='legacy','preserve legacy storage');check(!('previous_crop' in P.analysisInput(stored(),prop).agricultural_profile),'exclude legacy analysis');check(stored().fields.mechanization.status==='uncertain'&&stored().fields.mechanization.value.automation_level==='partial','preserve uncertainty and unedited detail');
const resolved=P.create(prop);for(const field of P.ESSENTIAL)resolved.fields[field].status='unknown';resolved.fields.last_harvest_result={...resolved.fields.last_harvest_result,status:'confirmed',value:{qualitative_result:'good'}};
prop.propertyId=crypto.randomUUID();resolved.property_id=prop.propertyId;db('agricultural_profiles').set(prop.propertyId,resolved);await window.AgrionDiscovery.open();const count=sockets.length;document.getElementById('discoveryRetry').click();await until(()=>sockets.length>count&&sockets.at(-1).sent.length);const done=sockets.at(-1);done.emit({setupComplete:{}});await wait(50);done.emit({toolCall:{functionCalls:[{id:'done',name:'complete_initial_interview',args:{}}]}});await until(()=>done.sent.some(x=>x.toolResponse));check(done.sent.find(x=>x.toolResponse).toolResponse.functionResponses[0].response.accepted,'voice completion without estimate');await manual();
await newManual();set('current_crop','soy');submit('save');await until(()=>stored().fields.current_crop.value?.crop==='soy');check(!document.getElementById('home'),'partial save stays form');check(document.getElementById('discoveryLanguage').disabled,'manual input locks language');
prop.propertyId=crypto.randomUUID();noExtractedFacts=true;await window.AgrionDiscovery.open();const beforeUnanswered=sockets.length;document.getElementById('discoveryRetry').click();await until(()=>sockets.length>beforeUnanswered&&sockets.at(-1).sent.length);const unanswered=sockets.at(-1);unanswered.emit({setupComplete:{}});unanswered.emit({inputTranscription:{text:'hello',finished:true}});await until(()=>db('interviews').get(unanswered.sent[0].interview_id)?.has_farmer_response===true);await window.AgrionDiscovery.open();check(document.getElementById('discoveryLanguage').disabled,'reload must preserve language lock after answer without extracted facts');noExtractedFacts=false;
window.AgrionLocale.set('pt-BR');check(I.get()==='en-US'&&document.getElementById('discoveryLanguage').disabled,'reload keeps recorded voice language after global change');check(document.getElementById('discoveryLanguageHint').textContent.includes('English'),'reload shows fixed voice');
prop.propertyId=crypto.randomUUID();window.AgrionLocale.set('en-US');await window.AgrionDiscovery.open();check(document.getElementById('discoveryLanguage').value==='en-US','new property starts in global language');
check(document.documentElement.scrollWidth<=innerWidth,'overflow');check(!errors.length,errors.join(';'));localStorage.removeItem('agrion-interview-language-v1');document.getElementById('testStatus').textContent='PASS: optional data, legacy, voice/manual, locale restart and lock';
}catch(e){document.getElementById('testStatus').textContent='FAIL: '+e.message}})();
'''
html=html[:html.index('window.testErrors=')]+setup+scripts+test+'</script></body></html>'
html=html.replace('</style>','\n'+css+'</style>',1)
output.write_text(html,encoding='utf-8')
