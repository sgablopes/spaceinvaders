"""Generate a browser fixture for dashboard copy with ready and unavailable data."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
scripts = '\n'.join((root / 'app/static' / name).read_text(encoding='utf-8') for name in [
    'agrion-locale.js', 'agrion-dashboard-language.js', 'agrion-indicators.js',
    'agrion-market.js', 'agrion-dashboard.js', 'discovery-home.js'])
html = '''<!doctype html><html><body><select id="agrionGlobalLanguage"><option value="pt-BR">Português</option><option value="en-US">English</option></select><div id="app"></div><p id="result">PENDING</p><script>
localStorage.removeItem('agrion-ui-language-v1');window.icon=()=>'';
const property={propertyId:'test-property',personName:'Alex',propertyName:'Test Farm'};
const fields={current_crop:{status:'confirmed',value:{crop:'corn'}},planting_date:{status:'confirmed',value:{date:'2026-01-15'}},primary_goal:{status:'confirmed',value:{category:'increase_yield'}},current_season_stage:{status:'confirmed',value:{stage:'flowering'}},last_crop:{status:'confirmed',value:{crop:'soy'}},last_harvest_result:{status:'confirmed',value:{qualitative_result:'good'}}};
const context={property:{id:property.propertyId,name:property.propertyName,geometry:null,area_hectares:2},agricultural_profile:{fields}};
const cache=new Map();let unavailable=false;
window.AgrionPropertyStore={read:()=>property};window.AgrionContext={load:async()=>structuredClone(context)};
window.AgrionDashboardCache={get:async key=>cache.get(key),put:async value=>cache.set(value.key,value)};
window.AgrionSearchSuggestions={append:()=>{}};window.AgrionPropertyOverview={attach:async()=>{},reset:()=>{}};
window.AgrionStation={close:()=>{},attachSummary:box=>box.textContent='Station fixture',attach:()=>{}};
window.AgrionPlanning={close:()=>{}};window.AgrionDiscovery={view:()=> 'next',openChat:()=>{}};
window.fetch=async(url,options)=>{const language=JSON.parse(options.body).context.ui_language;
 const section=url.split('/').at(-1),ready={daily:{status:'ready',headline:language==='en-US'?'Today’s analysis':'Análise de hoje',summary:{text:language==='en-US'?'The crop is growing.':'A cultura está crescendo.'},recommendations:[],observations:[]},forecast:{status:'ready',metrics:[{key:'temperature',label:'Temperatura',value:24,unit:'°C'},{key:'relative_humidity',label:'Umidade do ar',value:61,unit:'%'}],source:'Open-Meteo'},rainfall:{status:'ready',metrics:[{key:'rain_7d',label:'Chuva acumulada em 7 dias',value:12,unit:'mm',period_start:'2026-01-01',period_end:'2026-01-07'},{key:'rain_15d',label:'Chuva acumulada em 15 dias',value:20,unit:'mm',period_start:'2026-01-01',period_end:'2026-01-15'}],source:'NASA POWER'},stage:{status:'ready',phase:language==='en-US'?'Flowering':'Floração',reason:'Fixture',harvest_window:'Soon'},news:{status:'ready',items:[]},'market-analysis':{status:'ready',summary:language==='en-US'?'Market context.':'Contexto do mercado.',price:{value:20,unit:'USD',year:2025}}};
 return {ok:true,json:async()=>({property_id:property.propertyId,result:unavailable?{status:'unavailable',note:section==='forecast'?'Previsão indisponível no momento.':'Informação indisponível no momento.'}:ready[section]})};};
''' + scripts + '''
window.render=()=>{document.getElementById('app').innerHTML=window.AgrionHome.markup(property);window.AgrionHome.afterRender();};
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await wait(20)}throw Error('timeout')}
(async()=>{try{
 AgrionLocale.set('pt-BR');render();await until(()=>document.getElementById('agrionDashboard')?.textContent.includes('Resumo do dia'));
 const check=(condition,message)=>{if(!condition)throw Error(message)};
 check(document.getElementById('agrionHomePanel').textContent.includes('Mercado agrícola'),'Portuguese menu');
 AgrionHome.openPage('climate');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Umidade prevista do ar'));
 check(document.getElementById('agrionSectionScreen').textContent.includes('Chuva acumulada em 7 dias'),'Portuguese rainfall');
 AgrionHome.openPage('season');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Histórico de cultivo'));
 check(document.getElementById('agrionSectionScreen').textContent.includes('Cultura anterior: soy'),'Portuguese history');
 AgrionHome.openPage('analysis');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Notícias e pesquisas'));
 AgrionHome.openPage('measurements');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Solo e registros de campo'));
 AgrionHome.openPage('property');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Informações da entrevista'));
 AgrionHome.showDashboard();
 AgrionLocale.set('en-US');await until(()=>document.getElementById('agrionDashboard')?.textContent.includes('Daily summary'));
 check(document.getElementById('agrionHomePanel').textContent.includes('Agricultural market'),'English menu');
 check(document.getElementById('agrionDashboard').textContent.includes('Forecast weather'),'English forecast');
 AgrionHome.openPage('climate');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Weather and forecast'));
 await until(()=>document.getElementById('agrionSectionScreen').textContent.includes('Forecast air humidity'));
 check(document.getElementById('agrionSectionScreen').textContent.includes('Rainfall accumulated'),'English rain');
 AgrionHome.openPage('season');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Crop history'));
 check(document.getElementById('agrionSectionScreen').textContent.includes('Previous crop: soy'),'English history');
 await until(()=>document.getElementById('agrionSectionScreen').textContent.includes('Flowering'));
 AgrionHome.openPage('market');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Historical reference'));
 check(document.getElementById('agrionSectionScreen').textContent.includes('Market context.'),'English market data');
 AgrionHome.openPage('analysis');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('News and research'));
 AgrionHome.openPage('measurements');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Soil and field records'));
 AgrionHome.openPage('property');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Interview information'));
 unavailable=true;cache.clear();AgrionHome.openPage('climate');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Forecast unavailable right now.'));
 AgrionLocale.set('pt-BR');await until(()=>document.getElementById('agrionSectionScreen')?.textContent.includes('Previsão indisponível no momento.'));
 document.getElementById('result').textContent='PASS';
}catch(error){document.getElementById('result').textContent='FAIL: '+error.message}})();
</script></body></html>'''
Path(sys.argv[1]).write_text(html, encoding='utf-8')
