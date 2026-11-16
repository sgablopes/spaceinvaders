"""Small Chrome check for the bilingual project presentation page."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app

CHROME = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')


def main():
    page = create_app({'TESTING': True}).test_client().get('/sobre').get_data(as_text=True)
    if not CHROME.is_file():
        raise RuntimeError(f'Chrome not found: {CHROME}')
    for language in ('pt-BR', 'en-US'):
        local = re.sub(r'(["\'])/static/([^"\']+)\1',
                       lambda match: match.group(1) + (ROOT / 'app' / 'static' / match.group(2)).as_uri() + match.group(1), page)
        local = re.sub(r'<link[^>]+href="https://[^>]+>', '', local)
        check = f"AgrionLocale.set('{language}');document.addEventListener('DOMContentLoaded',()=>{{document.getElementById('smoke').textContent=(document.documentElement.lang==='{language}'&&document.title.includes('{ 'Apresentação' if language == 'pt-BR' else 'Project presentation' }')&&document.querySelector('#project-title').textContent.includes('{ 'cultivar o futuro' if language == 'pt-BR' else 'grow the future' }')&&!document.querySelector('#pitch-play').hidden&&document.querySelector('#pitch-pending').hidden&&document.querySelector('#pitch-external').href.includes('QFJOrwcknXY')&&document.querySelector('.repo-card')&&document.querySelector('.nav-return').getAttribute('href')==='/'&&document.documentElement.scrollWidth<=innerWidth+2)?'PASS':'FAIL';}});"
        local = local.replace('</body>', '<p id="smoke">PENDING</p><script>' + check + '</script></body>')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', prefix='.about-smoke-', dir=ROOT, encoding='utf-8', delete=False) as fixture:
            fixture.write(local)
            address = Path(fixture.name).as_uri()
        try:
            result = subprocess.run([str(CHROME), '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-background-networking', '--allow-file-access-from-files', '--window-size=390,844', '--virtual-time-budget=3000', '--dump-dom', address], capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            Path(fixture.name).unlink()
        if b'<p id="smoke">PASS</p>' not in result.stdout:
            raise RuntimeError(f'{language}: bilingual page check failed')
        print(f'{language}: PASS')


if __name__ == '__main__':
    main()
