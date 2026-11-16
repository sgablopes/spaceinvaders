"""Run the active Agrion interface through Chrome in both locales.

Usage: python tests/full_locale_e2e.py
The browser opens a local Flask-rendered page and mocks external API responses.
"""
import json
import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app

MOCK = r"""
(() => {
  const nativeFetch = window.fetch.bind(window);
  const response = value => ({ok:true,status:200,json:async()=>value});
  const criterion={level:'baixo',reason:'Fixture'};
  const strategy={id:'rotation',name:'Balanced rotation',headline:'A possible rotation',cycles:[{crop_id:'corn',window:'Window to confirm',purpose:'First cycle'},{crop_id:'corn',window:'Window to confirm',purpose:'Second cycle'}],benefits:[],constraints:[],soil:criterion,water:criterion,risk:criterion,cost:criterion,labor:criterion,confidence:'moderada',source_urls:[]};
  const plan={status:'ready',headline:'Fixture planning analysis',assumptions:[],missing_inputs:[],crops:[{id:'corn',name:'Corn',headline:'A crop to explore',overview:'Overview',conditions:'Conditions',management:'Management',water:'Water',labor:'Labor',mechanization:'Machinery',market:'Market',caveat:'Check local conditions',confidence:'moderada',source_urls:[]}],strategies:[strategy]};
  window.fetch=async (url,options={}) => {
    const path=String(url);
    if(path.startsWith('/api/dashboard/')) {
      const section=path.split('/').at(-1),language=JSON.parse(options.body).context.ui_language;
      const data={
        daily:{status:'ready',headline:language==='en-US'?'Today’s analysis':'Análise de hoje',summary:{text:language==='en-US'?'Review the crop.':'Revise a lavoura.'},recommendations:[],observations:[]},
        forecast:{status:'ready',metrics:[{key:'temperature',label:'Temperatura',value:24,unit:'°C'},{key:'relative_humidity',label:'Umidade do ar',value:61,unit:'%'}],source:'Open-Meteo'},
        rainfall:{status:'ready',metrics:[{key:'rain_7d',label:'Chuva acumulada em 7 dias',value:12,unit:'mm',period_start:'2026-01-01',period_end:'2026-01-07'}],source:'NASA POWER'},
        stage:{status:'ready',phase:language==='en-US'?'Flowering':'Floração',reason:'Fixture',harvest_window:'Soon'},
        news:{status:'ready',items:[]},
        'market-analysis':{status:'ready',summary:language==='en-US'?'Market context.':'Contexto do mercado.',price:{value:20,unit:'USD',year:2025}}
      };
      return response({property_id:'e2e-property',result:data[section]||{status:'unavailable'}});
    }
    if(path==='/api/planning/analyze')return response({property_id:'e2e-property',result:plan});
    if(path.includes('/telemetry/latest'))return response({reading:null});
    if(path==='/api/assistant/message')return response({text:'Fixture assistant answer',search_entry_points:[]});
    return nativeFetch(url,options);
  };
})();
"""

SCENARIO = r"""
(async () => {
  const lang=LANGUAGE;
  const step=name=>document.getElementById('e2eResult').textContent='STEP: '+name;
  const wait=async fn=>{for(let i=0;i<150;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,40));}throw Error('Timed out: '+fn.toString())};
  const check=(value,message)=>{if(!value)throw Error(message)};
  const screens=[];
  const review=name=>{
    const width=document.documentElement.scrollWidth,viewport=innerWidth;
    if(width>viewport+2){const offenders=[...document.querySelectorAll('body *')].filter(el=>{const r=el.getBoundingClientRect();return r.width&&r.right>viewport+2}).slice(0,5).map(el=>el.tagName+'.'+el.className);throw Error(name+' overflow '+width+'/'+viewport+' '+offenders.join(','));}
    const unnamed=[...document.querySelectorAll('button')].filter(el=>el.getClientRects().length&&!el.textContent.trim()&&!el.getAttribute('aria-label')&&!el.getAttribute('title'));
    check(!unnamed.length,name+' unnamed button');screens.push(name);
    const unlabeled=[...document.querySelectorAll('input,textarea,select')].filter(el=>el.getClientRects().length&&!el.labels?.length&&!el.getAttribute('aria-label')&&!el.getAttribute('aria-labelledby'));
    check(!unlabeled.length,name+' unlabeled field '+unlabeled.map(el=>el.id||el.name).join(','));
  };
  AgrionLocale.set(lang);
  check(document.documentElement.lang===lang,'document lang');
  check(document.title.includes(lang==='en-US'?'Agricultural planning':'Planejamento agrícola'),'title locale');
  check(document.querySelector('meta[name="description"]').content.startsWith(lang==='en-US'?'Agrion helps':'O Agrion ajuda'),'description locale');
  await wait(()=>document.querySelector('.welcome-page'));
  check(document.querySelector('.welcome-page h1').textContent.includes(lang==='en-US'?'future':'futuro'),'welcome locale');review('welcome');
  document.querySelector('[data-action="propertyEnter"]').click();
  await wait(()=>document.querySelector('#propertyPersonName'));
  check(document.querySelector('#propertyPersonName').placeholder.includes(lang==='en-US'?'What should':'Como podemos'),'property form locale');review('property');
  step('property');
  const geometry={type:'Polygon',coordinates:[[[-48,-23],[-47.999,-23],[-47.999,-22.999],[-48,-22.999],[-48,-23]]]};
  AgrionPropertyStore.save({propertyId:'e2e-property',personName:'Alex',propertyName:'Test Farm',geometry});
  const stores=new Map(),snapshots=new Map();
  Object.assign(AgrionRepository,{put:async(store,value)=>{stores.set(store+':'+(value.property_id||value.interview_id),value);return value;},get:async(store,key)=>stores.get(store+':'+key)||null,all:async store=>[...stores.entries()].filter(([key])=>key.startsWith(store+':')).map(([,value])=>value),getByPropertyId:async id=>stores.get('agricultural_profiles:'+id)||null});
  Object.assign(AgrionDashboardCache,{get:async key=>snapshots.get(key)||null,put:async value=>{snapshots.set(value.key,value);return true;}});
  await AgrionDiscovery.open();await wait(()=>document.querySelector('#discoveryLanguage'));
  check(document.querySelector('#discoveryLanguage').value===lang,'discovery initial language');review('discovery voice');
  document.querySelector('#discoveryManual').click();await wait(()=>document.querySelector('#discoveryManualForm'));
  review('discovery form');
  const property=AgrionPropertyStore.read(),profile=AgrionProfile.create(property);
  for(const field of AgrionProfile.ESSENTIAL)profile.fields[field]={...profile.fields[field],status:'unknown'};
  profile.fields.current_crop={...profile.fields.current_crop,status:'confirmed',value:{crop:'corn'}};
  profile.fields.planting_date={...profile.fields.planting_date,status:'confirmed',value:{date:'2026-01-15'}};
  await AgrionRepository.put('agricultural_profiles',profile);
  step('profile');
  await AgrionRepository.put('interviews',{interview_id:crypto.randomUUID(),property_id:'e2e-property',status:'completed',updated_at:new Date().toISOString()});
  step('interview');
  await AgrionDiscovery.open();
  step('opened');
  await wait(()=>document.querySelector('#agrionDashboard:not([hidden])'));
  check(document.querySelector('#agrionDashboard').textContent.includes(lang==='en-US'?'Daily summary':'Resumo do dia'),'dashboard locale');
  check(document.querySelector('#agrionDashboard').textContent.includes(lang==='en-US'?'1/15/26':'15/01/2026'),'planting date locale');review('dashboard');
  document.querySelector('#agrionHomeMenuToggle').click();
  for(const [page,expected] of [['climate',lang==='en-US'?'Weather and forecast':'Clima e previsão'],['season',lang==='en-US'?'Crop history':'Histórico de cultivo'],['analysis',lang==='en-US'?'News and research':'Notícias e pesquisas'],['market',lang==='en-US'?'Production and market':'Produção e mercado'],['measurements',lang==='en-US'?'Soil and field records':'Solo e registros de campo'],['property',lang==='en-US'?'Interview information':'Informações da entrevista']]){
    document.querySelector(`[data-home-page="${page}"]`).click();await wait(()=>document.querySelector('#agrionSectionScreen')?.textContent.includes(expected));review(page);
    document.querySelector('#agrionSectionScreen button').click();await wait(()=>document.querySelector('#agrionDashboard:not([hidden])'));
    document.querySelector('#agrionHomeMenuToggle').click();
  }
  document.querySelector('#agrionHomePlanning').click();await wait(()=>document.querySelector('.planning-page'));
  check(document.querySelector('.planning-page h1').textContent.includes(lang==='en-US'?'Crop Planning':'Planejamento de Cultivos'),'planning locale');review('planning');
  document.querySelector('.planning-back').click();await wait(()=>document.querySelector('#agrionDashboard:not([hidden])'));
  document.querySelector('#agrionHomeMenuToggle').click();document.querySelector('#agrionHomeStation').click();await wait(()=>document.querySelector('.agrion-station'));
  check(document.querySelector('.agrion-station').textContent.includes(lang==='en-US'?'Station ID':'ID da estação'),'station locale');review('station');
  document.querySelector('.agrion-station-back').click();await wait(()=>document.querySelector('#agrionDashboard:not([hidden])'));
  document.querySelector('.agrion-home-assistant').click();await wait(()=>document.querySelector('.agrion-chat'));
  check(document.querySelector('#agrionChatLanguage').value===lang,'chat language');review('chat');
  document.querySelector('#agrionChatInput').value='Hello';document.querySelector('#agrionChatForm').requestSubmit();await wait(()=>document.querySelector('#agrionChatMessages')?.textContent.includes('Fixture assistant answer'));
  review('chat response');
  return {locale:lang,screens,viewport:innerWidth,title:document.title};
})()
"""


def main():
    app = create_app()
    page = app.test_client().get('/').get_data(as_text=True)
    assert CHROME.is_file(), f'Chrome not found: {CHROME}'
    for language in ('pt-BR', 'en-US'):
        local_page = re.sub(r'(["\'])/static/([^"\']+)\1', lambda match: match.group(1) + (ROOT / 'app' / 'static' / match.group(2)).as_uri() + match.group(1), page)
        local_page = local_page.replace('</head>', '<script>' + MOCK + '</script></head>')
        scenario = SCENARIO.replace('LANGUAGE', json.dumps(language))
        local_page = local_page.replace('</body>', '<p id="e2eResult">PENDING</p><script>' + scenario + '.then(result=>document.getElementById("e2eResult").textContent=JSON.stringify(result)).catch(error=>document.getElementById("e2eResult").textContent="FAIL: "+error.message);</script></body>')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', prefix='.locale-e2e-', dir=ROOT, encoding='utf-8', delete=False) as fixture:
            fixture.write(local_page)
            address = Path(fixture.name).as_uri()
        try:
            run = subprocess.run([str(CHROME), '--headless=new', '--disable-gpu', '--no-sandbox', '--allow-file-access-from-files', '--window-size=390,844', '--force-device-scale-factor=1.3', '--virtual-time-budget=30000', '--dump-dom', address], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            Path(fixture.name).unlink()
        match = re.search(r'<p id="e2eResult">([^<]*)</p>', run.stdout)
        if not match or not match.group(1).startswith('{'):
            raise RuntimeError(f'{language}: {html.unescape(match.group(1)) if match else "no result"}; {run.stderr[-500:]}')
        print(html.unescape(match.group(1)))


if __name__ == '__main__':
    main()
