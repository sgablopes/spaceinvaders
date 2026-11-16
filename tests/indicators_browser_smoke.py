"""Browser checks for telemetry lifecycle, meaningful indicators and search layout."""
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
runpy.run_path(str(root / 'tests/planning_browser_smoke.py'))
output = Path(sys.argv[1])
html = output.read_text(encoding='utf-8')
setup = r'''
const errors=[];window.onerror=m=>errors.push(m);Element.prototype.scrollIntoView=function(){};
const memory=new Map(),calls=[];let mode='recent',release=null,visibility='visible';
Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>visibility});
window.AgrionDashboardCache={get:async k=>memory.get(k),put:async r=>{memory.set(r.key,r);return true}};
window.AgrionContext={load:async()=>testContext};
window.AgrionPropertyStore={read:()=>({propertyId:testContext.property.id,propertyName:'Área de teste',personName:'Teste'})};
window.AgrionPropertyOverview={attach:()=>{},reset:()=>{}};
window.AgrionMarket={attach:()=>{},reset:()=>{}};
window.AgrionPlanning={close:()=>{},attach:()=>{}};
window.AgrionDiscovery={editProperty:()=>{},openChat:()=>{}};
const search='<style>body{margin:8px}.chip{height:32px;background:#eee}</style><div class="chip">Pesquisa de teste</div>';
window.fetch=async(url,options)=>{
calls.push(url);if(url.includes('/telemetry/')){
 if(mode==='failure')throw Error('offline');
 if(mode==='pending')return new Promise(resolve=>{release=resolve});
 return {ok:true,json:async()=>({reading:mode==='empty'?null:{received_at:new Date(Date.now()-(mode==='old'?120000:0)).toISOString(),measurements:{temperature_c:0,humidity_pct:0,vento_estimado_m_s:0,rain_detected:false}}})};
}
return {ok:true,json:async()=>({property_id:testContext.property.id,result:{status:'ready',headline:'Resumo fictício para teste',summary:{text:'Detalhe fictício'},recommendations:[],metrics:[{key:'relative_humidity',label:'Umidade',value:72,unit:'%'}],phase:'Floração',reason:'Dados fictícios',harvest_window:'A confirmar',items:[],search_entry_points:[search,search]}})};
};
window.render=()=>{document.getElementById('app').innerHTML=window.AgrionHome.markup(window.AgrionPropertyStore.read());window.AgrionHome.afterRender()};
'''
scripts='\n'.join((root/'app/static'/n).read_text(encoding='utf-8') for n in ['agrion-indicators.js','agrion-search-suggestions.js','agrion-station.js','agrion-dashboard.js','discovery-home.js'])
test=r'''
function check(ok,m){if(!ok)throw Error(m)}
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function refresh(){document.dispatchEvent(new Event('visibilitychange'));await wait(100)}
(async()=>{try{
localStorage.removeItem('agrion-station-id-v1');window.render();await wait(200);
check(document.querySelector('.agrion-station-status').dataset.state==='recent','recent station');
check(document.querySelector('#agrionDashboard-station [role="meter"]').getAttribute('aria-valuenow')==='0','zero humidity');
check(document.querySelector('#agrionDashboard-station').textContent.includes('Não detectada'),'false rain');
check(document.querySelector('#agrionDashboard-station').textContent.includes('demonstração'),'demo label');
const frame=document.querySelector('#agrionDashboard-daily iframe');await wait(200);
check(document.querySelectorAll('#agrionDashboard-daily iframe').length===1,'duplicate search');
check(parseFloat(frame.style.height)>0&&parseFloat(frame.style.height)<80,'search auto height');
frame.contentDocument.querySelector('.chip').style.height='120px';await wait(100);check(parseFloat(frame.style.height)>=120,'search grows without clipping');
frame.contentDocument.querySelector('.chip').style.height='32px';await wait(100);check(parseFloat(frame.style.height)<80,'search shrinks again');
check(!frame.sandbox.contains('allow-scripts'),'search scripts forbidden');
const probe=document.createElement('div');document.body.append(probe);
window.AgrionSearchSuggestions.append(probe,[search]);check(probe.querySelector('iframe').className==='agrion-search-suggestions','planning default unchanged');probe.remove();
const start=calls.length;await wait(5200);check(calls.length>start,'poll update');
mode='old';await refresh();check(document.querySelector('.agrion-station-status').dataset.state==='old','stale reading');
mode='failure';await refresh();check(document.querySelector('.agrion-station-status').dataset.state==='unavailable','failure state');check(document.querySelector('#agrionDashboard-station [role="meter"]'),'preserve reading');
mode='empty';await refresh();check(document.querySelector('.agrion-station-status').dataset.state==='empty','empty state');check(!document.querySelector('#agrionDashboard-station [role="meter"]'),'clear missing measurement');
visibility='hidden';await refresh();const paused=calls.length;await wait(5200);check(calls.length===paused,'pause hidden tab');visibility='visible';mode='recent';await refresh();
window.AgrionHome.openPage('season');await wait(200);check(document.querySelector('[aria-current="step"]').textContent.includes('Floração'),'phase indicator');check(!document.querySelector('.agrion-phase [role="progressbar"]'),'no fake percent');
const afterLeave=calls.length;await wait(5200);check(calls.length===afterLeave,'stop polling on navigation');
check(!window.AgrionIndicators.humidity(110).querySelector('[role="meter"]'),'invalid humidity');
check(!window.AgrionIndicators.phase('Vegetativo ou floração',null).querySelector('[aria-current]'),'ambiguous phase');
const rain=[{unit:'mm',value:4,period_start:'2026-01-01',period_end:'2026-01-07'},{unit:'mm',value:8,period_start:'2026-01-01',period_end:'2026-01-15'}];check(!window.AgrionIndicators.rainfall(rain),'different rain durations');rain[1].period_start='2026-01-09';check(window.AgrionIndicators.rainfall(rain),'equal rain durations');
window.AgrionHome.openStation();await wait(100);const input=document.querySelector('[name="station_id"]');input.value='station-test';document.querySelector('.agrion-station-form').dispatchEvent(new Event('submit',{cancelable:true}));await wait(100);check(calls.at(-1).includes('station-test'),'paired id');
mode='pending';await refresh();check(release,'pending reading');window.AgrionHome.openPage('climate');release({ok:true,json:async()=>({reading:null})});await wait(100);check(!document.querySelector('.agrion-station-status'),'ignore old response');
mode='recent';window.AgrionHome.showDashboard();await wait(200);check(document.querySelector('#agrionDashboard-station').textContent.includes('station-test'),'saved id on home');
check(document.documentElement.scrollWidth<=innerWidth,'overflow');check(!errors.length,errors.join(';'));
window.AgrionStation.close();localStorage.removeItem('agrion-station-id-v1');document.getElementById('testStatus').textContent='PASS: live station, polling, indicators, search resizing, navigation';
}catch(e){window.AgrionStation.close();document.getElementById('testStatus').textContent='FAIL: '+e.message}})();
'''
html=html[:html.index('window.testErrors=')]+setup+scripts+test+'</script></body></html>'
output.write_text(html,encoding='utf-8')
