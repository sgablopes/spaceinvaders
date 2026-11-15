"""Gera página isolada para teste de navegação no Chrome, sem chamadas externas.

Uso: python tests/planning_browser_smoke.py .planning-smoke.html
Dados desta página são fixtures fictícias, nunca respostas do produto.
"""
import base64
import json
from pathlib import Path
import sys
import re
import html as html_module

ROOT = Path(__file__).resolve().parents[1]
context = {'property': {'id': 'browser-test', 'name': 'Propriedade de teste', 'area_hectares': 2},
           'agricultural_profile': {'fields': {'current_crop': {'status': 'confirmed', 'value': {'crop': 'Milho'}}}}}
crop = {'id': 'milho', 'name': 'Milho', 'headline': 'Alternativa preliminar para avaliar', 'overview': 'Cultura de interesse neste cenário de teste.',
        'conditions': 'Confirmar as condições do terreno.', 'management': 'Organizar operações com a equipe.', 'water': 'Disponibilidade a confirmar.',
        'labor': 'Equipe a confirmar.', 'mechanization': 'Equipamentos a confirmar.', 'market': 'Referência local a confirmar.',
        'caveat': 'Fixture fictícia de teste. Sem laudo de solo.', 'confidence': 'baixa', 'source_urls': []}
strategy = {'id': 'equilibrada', 'name': 'Rotação equilibrada', 'headline': 'Avaliar diversidade e cobertura do solo.',
            'cycles': [{'crop_id': 'milho', 'purpose': 'Produção', 'window': 'Janela a confirmar'},
                       {'crop_id': 'feijao', 'purpose': 'Diversificação', 'window': 'Após o primeiro ciclo'}],
            'benefits': ['Avaliar diversidade de culturas'], 'constraints': ['Confirmar recursos locais'], 'confidence': 'baixa', 'source_urls': []}
for key in ['soil', 'water', 'risk', 'cost', 'labor']:
    strategy[key] = {'level': 'moderado', 'reason': 'Avaliação fictícia usada apenas neste teste.'}
analysis = {'status': 'partial', 'headline': 'Alternativas para a próxima safra', 'generated_at': '2026-11-15T12:00:00Z',
            'assumptions': ['Dados fictícios para testar a interface'], 'missing_inputs': ['Laudo de solo'], 'search_entry_points': [],
            'crops': [crop, {**crop, 'id': 'feijao', 'name': 'Feijão'}],
            'strategies': [strategy, {**strategy, 'id': 'diversificada', 'name': 'Diversificada'}]}
template = (ROOT / 'app/templates/index.html').read_text(encoding='utf-8')
icons = template[template.index('  const icons={'):template.index("  const STORAGE=")]
base_style = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', template, re.S))
css = base_style + ''.join((ROOT / 'app/static' / name).read_text(encoding='utf-8') for name in ['discovery-home.css', 'agrion-planning.css'])
photo = base64.b64encode((ROOT / 'app/static/agrion-hero-desktop.jpg').read_bytes()).decode()
css = css.replace('/static/agrion-hero-desktop.jpg', 'data:image/jpeg;base64,' + photo)
scripts = '\n'.join((ROOT / 'app/static' / name).read_text(encoding='utf-8') for name in ['agrion-planning.js', 'discovery-home.js'])
setup = '''
window.testErrors=[];window.onerror=(message)=>{window.testErrors.push(message)};
Element.prototype.scrollIntoView=function(){};
const memory=new Map();let fail=false;
window.AgrionDashboardCache={get:async key=>structuredClone(memory.get(key)||null),put:async data=>{memory.set(data.key,structuredClone(data));return true}};
window.AgrionContext={load:async()=>structuredClone(testContext)};
window.AgrionDashboard={start:()=>{},reset:()=>{}};window.AgrionStation={close:()=>{}};
window.AgrionSearchSuggestions={append:()=>{}};window.confirm=()=>true;
let polls=0,posted=0;
window.fetch=async(url,options)=>{
if(options?.method==='POST'){check(options.headers.Prefer==='respond-async','async request');posted++;polls=0;return {ok:true,json:async()=>({property_id:testContext.property.id,job_id:'a'.repeat(64),status:'running'})};}
polls++;return {ok:true,json:async()=>polls===1?{status:'running'}:{property_id:testContext.property.id,status:'completed',result:fail?{status:'unavailable'}:structuredClone(testAnalysis)}};
};
document.addEventListener('click',e=>{if(e.target.closest('[data-action]')?.dataset.action==='analyze')testErrors.push('legacy action collision');});
window.render=()=>{document.getElementById('app').innerHTML=window.AgrionHome.markup({personName:'Teste',propertyName:'Propriedade de teste'});window.AgrionHome.afterRender()};
function check(ok,message){if(!ok)throw Error(message)}
async function until(checker){for(let i=0;i<1000;i++){if(checker())return;await new Promise(r=>setTimeout(r,10))}throw Error('timeout')}
'''
test = '''
(async()=>{try{
window.render();document.getElementById('agrionHomePlanning').click();
check(!!document.getElementById('agrionPlanningScreen')&&!document.getElementById('agrionHomePanel'),'page must be outside menu');
check(!!document.getElementById('agrionHomeHeader'),'header missing');
await until(()=>document.querySelector('[data-crop]'));
document.querySelector('[data-crop]').click();check(!!document.querySelector('[data-tab="conditions"]'),'crop tabs');
document.querySelector('[data-select]').click();document.querySelector('[data-step="1"]').click();
check(document.querySelectorAll('.planning-strategy').length===2,'strategies');
document.querySelector('[data-step="2"]').click();check(document.querySelectorAll('[data-choose]').length===2,'comparison');
document.querySelector('[data-choose]').click();check(document.querySelectorAll('[data-cycle]').length===2,'cycles');
const task=document.querySelector('[data-task]');task.checked=true;task.dispatchEvent(new Event('change'));
document.querySelector('[data-planning-action="back"]').click();check(!!document.getElementById('agrionHomePanel'),'back');
document.getElementById('agrionHomePlanning').click();await until(()=>document.querySelector('[data-task]'));
check(document.querySelector('[data-task]').checked,'saved checklist');
testContext.property.area_hectares=3;window.AgrionHome.showDashboard();document.getElementById('agrionHomePlanning').click();
await until(()=>document.querySelector('.planning-plan-heading'));check(document.body.textContent.includes('mudaram'),'stale plan');
fail=true;document.querySelector('[data-planning-action="analyze"]').click();await until(()=>document.body.textContent.includes('análise anterior continua'));
check(!!document.querySelector('.planning-plan-heading'),'failure must retain plan');
testContext.property.id='empty-test';window.AgrionHome.showDashboard();document.getElementById('agrionHomePlanning').click();
await until(()=>document.body.textContent.includes('campos complementares são opcionais'));
check(!!document.querySelector('.planning-empty')&&!document.querySelector('.planning-spinner'),'finite cold failure');
testContext.property.id='browser-test';fail=false;window.AgrionHome.showDashboard();document.getElementById('agrionHomePlanning').click();
await until(()=>document.querySelector('.planning-plan-heading'));document.querySelector('[data-step="2"]').click();
check(document.documentElement.scrollWidth<=innerWidth,'horizontal overflow');check(!testErrors.length,testErrors.join(';'));
document.getElementById('testStatus').textContent='PASS: navigation, partial result, comparison, plan, persistence, stale context, failure';
window.scrollTo(0,0);
}catch(error){document.getElementById('testStatus').textContent='FAIL: '+error.message;}})();
'''
html = '<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>' + css + '</style><body><p id="testStatus" style="padding:8px;background:#e5efc7;font:12px sans-serif">TEST FIXTURE — dados fictícios</p><div id="app"></div><script>' + icons + '\nconst testContext=' + json.dumps(context) + ';const testAnalysis=' + json.dumps(analysis) + ';\n' + setup + scripts + test + '</script></body></html>'
Path(sys.argv[1]).write_text(html, encoding='utf-8')
if len(sys.argv)>2:
    # Iframe permite medir 390px reais mesmo em Chrome Windows com janela mínima.
    Path(sys.argv[2]).write_text('<!doctype html><html><body style="margin:0"><iframe style="border:0;width:390px;height:1000px" srcdoc="'+html_module.escape(html, quote=True)+'"></iframe></body></html>', encoding='utf-8')
