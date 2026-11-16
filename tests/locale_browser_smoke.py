"""Generate a small browser fixture for the global language preference."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
script = (root / 'app/static/agrion-locale.js').read_text(encoding='utf-8')
html = '''<!doctype html><html lang="en-US"><head><meta name="description" content="Agrion helps farmers explore crops, plan rotations, monitor weather and understand their property."><title>Agrion | Agricultural planning</title></head><body>
<select id="agrionGlobalLanguage"><option value="pt-BR">Português</option><option value="en-US">English</option></select>
<p id="result">PENDING</p><script>
Object.defineProperty(navigator,'language',{get:()=> 'pt-PT'});
if(!sessionStorage.getItem('agrion-locale-reload'))localStorage.removeItem('agrion-ui-language-v1');
''' + script + '''
document.addEventListener('DOMContentLoaded',()=>{
 const L=window.AgrionLocale, select=document.getElementById('agrionGlobalLanguage');
 const check=(ok,message)=>{if(!ok)throw Error(message)};
 try {
  check(L.detect('pt-BR')==='pt-BR','Brazilian Portuguese');
  check(L.detect('pt-PT')==='en-US','other Portuguese');
  check(L.detect('fr-FR')==='en-US','other language');
  if(sessionStorage.getItem('agrion-locale-reload')){
   check(L.get()==='pt-BR'&&document.documentElement.lang==='pt-BR'&&select.value==='pt-BR','preference after reload');
   check(document.title==='Agrion | Planejamento agrícola'&&document.querySelector('meta[name="description"]').content.startsWith('O Agrion'),'Portuguese metadata');
   sessionStorage.removeItem('agrion-locale-reload');localStorage.removeItem('agrion-ui-language-v1');
   document.getElementById('result').textContent='PASS';return;
  }
  check(L.get()==='en-US'&&document.documentElement.lang==='en-US','initial fallback');
  check(document.title==='Agrion | Agricultural planning'&&document.querySelector('meta[name="description"]').content.startsWith('Agrion helps'),'English metadata');
  select.value='pt-BR';select.dispatchEvent(new Event('change'));
  check(L.get()==='pt-BR'&&localStorage.getItem('agrion-ui-language-v1')==='pt-BR','saved selection');
  check(document.documentElement.lang==='pt-BR','document language');
  sessionStorage.setItem('agrion-locale-reload','1');location.reload();
 } catch(error) { document.getElementById('result').textContent='FAIL: '+error.message; }
});
</script></body></html>'''
Path(sys.argv[1]).write_text(html, encoding='utf-8')
