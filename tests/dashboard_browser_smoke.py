"""Generate isolated browser regression checks with explicitly fictional data."""
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
runpy.run_path(str(root / 'tests/planning_browser_smoke.py'))
output = Path(sys.argv[1])
html = output.read_text(encoding='utf-8')
setup = r'''
const errors=[];window.onerror=m=>errors.push(m);Element.prototype.scrollIntoView=function(){};
const memory=new Map(),calls=[];
window.AgrionDashboardCache={get:async k=>memory.get(k),put:async r=>{memory.set(r.key,r);return true}};
window.AgrionContext={load:async()=>testContext};
window.AgrionPropertyStore={read:()=>({propertyId:testContext.property.id,propertyName:'Área de teste',personName:'Teste'})};
window.AgrionPropertyOverview={attach:()=>{},reset:()=>{}};
window.AgrionMarket={attach:()=>{calls.push('market');document.getElementById('agrionDashboard-market').textContent='Mercado de teste'},reset:()=>{}};
window.AgrionSearchSuggestions={append:()=>{}};window.AgrionStation={close:()=>{},attach:()=>{document.getElementById('agrionStationScreen').textContent='Estação de teste'}};
window.AgrionPlanning={close:()=>{},attach:()=>{document.getElementById('agrionPlanningScreen').textContent='Planejamento preservado'}};
window.AgrionDiscovery={editProperty:()=>{window.edited=true},openChat:()=>{}};
let fail=false;
window.fetch=async url=>{const section=url.split('/').pop();calls.push(section);if(fail)throw Error('fixture failure');return {ok:true,json:async()=>({property_id:testContext.property.id,result:{status:'ready',headline:'Resumo fictício para teste',summary:{text:'Detalhe fictício'},recommendations:[{headline:'Recomendação de teste',text:'Detalhe'}],metrics:[{key:'temperature',label:'Temperatura',value:25,unit:'°C'}],phase:'Fase de teste',reason:'Dados fictícios',harvest_window:'A confirmar',items:[],search_entry_points:[]}})}};
window.render=()=>{document.getElementById('app').innerHTML=window.AgrionHome.markup(window.AgrionPropertyStore.read());window.AgrionHome.afterRender()};
'''
scripts='\n'.join((root/'app/static'/n).read_text(encoding='utf-8') for n in ['agrion-dashboard.js','discovery-home.js'])
test=r'''
function check(ok,m){if(!ok)throw Error(m)}
async function settle(){await new Promise(r=>setTimeout(r,50))}
(async()=>{try{
window.render();await settle();
check(calls.sort().join(',')==='daily,forecast,stage','home requests: '+calls);
check(!document.getElementById('agrionDashboard-news')&&!document.getElementById('agrionDashboard-market'),'home overcrowding');
for(const [page,expected] of [['climate','rainfall'],['season','stage'],['analysis','news'],['market','market'],['measurements',null],['property',null]]){
window.AgrionHome.openPage(page);await settle();
check(!!document.getElementById('agrionHomeHeader')&&!document.getElementById('agrionHomePanel'),'separate page '+page);
if(expected)check(calls.includes(expected),'missing data '+expected);
if(page==='property'){document.querySelectorAll('.agrion-section-link')[1].click();check(window.edited,'map edit')}
document.querySelector('.agrion-section-link').click();await settle();check(!!document.getElementById('agrionDashboard'),'return '+page);
}
const count=calls.length;window.AgrionHome.openPage('climate');await settle();check(calls.length===count,'cache reuse');
window.AgrionHome.showDashboard();await settle();document.getElementById('agrionHomePlanning').click();check(!!document.getElementById('agrionPlanningScreen'),'planning route');
window.AgrionHome.showDashboard();await settle();document.getElementById('agrionHomeStation').click();check(!!document.getElementById('agrionStationScreen'),'station route');
memory.clear();fail=true;window.AgrionHome.openPage('climate');await settle();check(document.body.textContent.includes('Não foi possível atualizar'),'failure state');
fail=false;window.AgrionHome.showDashboard();await settle();
check(document.documentElement.scrollWidth<=innerWidth,'overflow');check(!errors.length,errors.join(';'));
document.getElementById('testStatus').textContent='PASS: dashboard, navigation, lazy queries, cache, failures, planning and station';
}catch(e){document.getElementById('testStatus').textContent='FAIL: '+e.message}})();
'''
html=html[:html.index('window.testErrors=')]+setup+scripts+test+'</script></body></html>'
output.write_text(html,encoding='utf-8')
