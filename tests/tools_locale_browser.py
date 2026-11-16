"""Generate a Chrome fixture for planning, station and assistant locale flows."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
scripts = '\n'.join((root / 'app/static' / name).read_text(encoding='utf-8') for name in [
    'agrion-locale.js', 'agrion-dashboard-language.js', 'agrion-tools-language.js',
    'agrion-planning.js', 'agrion-station.js', 'agrion-chat.js'])
html = '''<!doctype html><html><body><select id="agrionGlobalLanguage"><option value="pt-BR">Português</option><option value="en-US">English</option></select><div id="app"></div><p id="result">PENDING</p><script>
window.icon=()=>'';
const property={propertyId:'test-property',propertyName:'Test Farm'};
window.AgrionPropertyStore={read:()=>property};
window.AgrionContext={load:async()=>({property:{id:property.propertyId,name:property.propertyName,area_hectares:2},agricultural_profile:{fields:{}}})};
const cache=new Map();window.AgrionDashboardCache={get:async key=>cache.get(key),put:async value=>{cache.set(value.key,value);return true}};
window.AgrionSearchSuggestions={append:()=>{}};
window.AgrionHome={showDashboard:()=>{},openStation:()=>{}};
window.AgrionDiscovery={view:()=> 'chat',showHome:()=>{}};
window.AgrionIndicators={metric:(label,value)=>{const n=document.createElement('span');n.textContent=label+': '+value;return n},humidity:value=>{const n=document.createElement('span');n.textContent='Humidity: '+value;return n}};
let planningLanguage='',planningInputs=null,failed=false,assistantFail=false;
let analysis={status:'ready',headline:'Fixture analysis',assumptions:[],missing_inputs:[],crops:[],strategies:[],search_entry_points:[]};
window.fetch=async(url,options={})=>{
 if(url==='/api/planning/analyze'){
  const request=JSON.parse(options.body);planningLanguage=request.context.ui_language;planningInputs=request.inputs;
  if(failed)throw Error('offline');
  return {ok:true,json:async()=>({property_id:property.propertyId,result:analysis})};
 }
 if(url.includes('/telemetry/latest'))return {ok:true,json:async()=>({reading:null})};
 if(url==='/api/assistant/message')return assistantFail?{ok:false,json:async()=>({error:'rate_limited'})}:{ok:true,json:async()=>({text:'Hello from Agrion',search_entry_points:[]})};
 throw Error(url);
};
''' + scripts + '''
window.render=()=>{};
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await wait(20)}throw Error('timeout')}
const check=(ok,message)=>{if(!ok)throw Error(message)};
(async()=>{try{
 AgrionLocale.set('pt-BR');let app=document.getElementById('app');
 await AgrionPlanning.attach(app);await until(()=>planningLanguage==='pt-BR'&&app.textContent.includes('Seu planejamento começa aqui'));
 check(planningLanguage==='pt-BR','planning Portuguese context');
 check(app.textContent.includes('Planejamento de Cultivos'),'planning Portuguese heading');
 AgrionLocale.set('en-US');await until(()=>app.textContent.includes('Your planning starts here'));
 check(planningLanguage==='en-US','planning English context');
 check(app.querySelector('#planningInputs textarea').placeholder==='Not provided','planning English form');
 app.querySelector('#planningInputs textarea[name="soil"]').value='Clay';
 app.querySelector('#planningInputs').dispatchEvent(new Event('submit',{cancelable:true}));
 await until(()=>planningInputs?.soil==='Clay'&&app.textContent.includes('Analysis updated.'));
 const criterion={level:'baixo',reason:'Fixture'};
 analysis={...analysis,crops:[{id:'corn',name:'Corn',headline:'Crop headline',overview:'Overview text',conditions:'Conditions text',management:'Management text',water:'Water text',labor:'Labor text',mechanization:'Machinery text',market:'Market text',caveat:'Caveat',confidence:'moderada',source_urls:[]}],strategies:[{id:'rotation',name:'Balanced rotation',headline:'Strategy headline',cycles:[{crop_id:'corn',window:'Window',purpose:'Purpose'},{crop_id:'corn',window:'Window',purpose:'Purpose'}],benefits:['Benefit'],constraints:['Constraint'],soil:criterion,water:criterion,risk:criterion,cost:criterion,labor:criterion,confidence:'moderada',source_urls:[]}]};
 app.querySelector('[data-planning-action="analyze"]').click();await until(()=>app.textContent.includes('Crop headline'));
 app.querySelector('[data-crop="corn"]').click();check(app.textContent.includes('CROP OPTION'),'planning crop detail');
 app.querySelector('[data-step="1"]').click();check(app.textContent.includes('Suggested strategies'),'planning strategies');
 app.querySelector('[data-step="2"]').click();check(app.textContent.includes('Choose this strategy'),'planning comparison');
 app.querySelector('[data-choose="rotation"]').click();check(app.textContent.includes('Selected strategy'),'planning saved plan');
 const cycle=app.querySelector('[data-cycle="0"]');cycle.value='Em andamento';cycle.dispatchEvent(new Event('change'));
 check(cycle.value==='Em andamento'&&cycle.selectedOptions[0].textContent==='In progress','canonical cycle value');
 failed=true;app.querySelector('[data-planning-action="analyze"]').click();await until(()=>app.textContent.includes('Could not refresh now.'));
 AgrionPlanning.close();app.replaceChildren();
 AgrionStation.attach(app);check(app.textContent.includes('Station ID'),'station English form');
 const form=app.querySelector('form');form.querySelector('input').value='bad id';form.dispatchEvent(new Event('submit',{cancelable:true}));
 check(app.textContent.includes('Enter a valid ID.'),'station English error');
 await until(()=>app.textContent.includes('No readings'));
 AgrionLocale.set('pt-BR');AgrionStation.attach(app);
 check(app.textContent.includes('ID da estação'),'station Portuguese form');
 AgrionStation.close();app.replaceChildren();
 AgrionLocale.set('en-US');
 AgrionChat.open();app.innerHTML=AgrionChat.markup();AgrionChat.afterRender();
 check(app.querySelector('#agrionChatLanguage').value==='en-US','chat initial language');
 check(app.textContent.includes('What would you like to know'),'chat English empty');
 app.querySelector('#agrionChatInput').value='Question';app.querySelector('#agrionChatForm').dispatchEvent(new Event('submit',{cancelable:true}));
 await until(()=>app.textContent.includes('Hello from Agrion'));
 assistantFail=true;app.querySelector('#agrionChatInput').value='Second question';app.querySelector('#agrionChatForm').dispatchEvent(new Event('submit',{cancelable:true}));
 await until(()=>app.textContent.includes('Message limit reached'));
 check(app.querySelector('#agrionChatInput').value==='Second question','chat input retained on error');
 AgrionLocale.set('pt-BR');app.innerHTML=AgrionChat.markup();AgrionChat.afterRender();
 check(app.querySelector('#agrionChatLanguage').value==='pt-BR','chat Portuguese language');
 check(app.textContent.includes('Converse sobre sua propriedade'),'chat Portuguese copy');
 document.getElementById('result').textContent='PASS';
}catch(error){document.getElementById('result').textContent='FAIL: '+error.message}})();
</script></body></html>'''
Path(sys.argv[1]).write_text(html, encoding='utf-8')
