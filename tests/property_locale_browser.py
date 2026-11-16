"""Generate a browser fixture for the translated entry and property screens."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
template = (root / 'app/templates/index.html').read_text(encoding='utf-8')
welcome = template.split('  function welcome(){', 1)[1].split('  function render(){', 1)[0]
locale = (root / 'app/static/agrion-locale.js').read_text(encoding='utf-8')
property_flow = (root / 'app/static/property-flow.js').read_text(encoding='utf-8')
html = '''<!doctype html><html><body><select id="agrionGlobalLanguage"><option value="pt-BR">Português</option><option value="en-US">English</option></select><div id="app"></div><p id="result">PENDING</p><script>
localStorage.removeItem('agrion-ui-language-v1');window.AGRION_CONFIG={maptilerKey:''};
window.AgrionPropertyStore={read:()=>null,save:data=>({...data,propertyName:data.propertyName||'Minha propriedade'})};
window.icon=()=>'';window.notify=()=>{};
''' + locale + property_flow + '\nfunction welcome(){' + welcome + '''
window.render=()=>{document.getElementById('app').innerHTML=window.AgrionProperty.view()==='welcome'?welcome():window.AgrionProperty.markup();if(window.AgrionProperty.view()!=='welcome')window.AgrionProperty.afterRender();};
document.addEventListener('DOMContentLoaded',()=>{try{
 const check=(ok,message)=>{if(!ok)throw Error(message)};
 AgrionLocale.set('en-US');render();check(document.body.textContent.includes('The future of your farm'),'English welcome');
 AgrionProperty.action('propertyEnter');check(document.body.textContent.includes('Tell us about you and your property'),'English identity');
 document.getElementById('propertyIdentityForm').dispatchEvent(new Event('submit',{cancelable:true}));
 check(document.getElementById('propertyFormError').textContent==='Enter your name to continue.','English validation');
 document.getElementById('propertyPersonName').value='Alex';document.getElementById('propertyIdentityForm').dispatchEvent(new Event('submit',{cancelable:true}));
 check(document.body.textContent.includes('Property registration'),'English map');
 check(document.body.textContent.includes('MapTiler key is not configured.'),'English map state');
 AgrionLocale.set('pt-BR');check(document.body.textContent.includes('Cadastro geográfico'),'Portuguese map after switch');
 check(document.documentElement.lang==='pt-BR','document language');
 document.getElementById('result').textContent='PASS';
}catch(error){document.getElementById('result').textContent='FAIL: '+error.message;}});
</script></body></html>'''
Path(sys.argv[1]).write_text(html, encoding='utf-8')
