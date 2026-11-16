(function () {
  'use strict';
  const key = 'agrion-ui-language-v1';
  const valid = value => value === 'pt-BR' || value === 'en-US';
  const detect = (primary = navigator.language) => primary === 'pt-BR' ? 'pt-BR' : 'en-US';
  let saved;
  try { saved = localStorage.getItem(key); } catch (_) {}
  let language = valid(saved) ? saved : detect();

  function apply() {
    document.documentElement.lang = language;
    const about = document.body?.dataset.page === 'about';
    document.title = about
      ? (language === 'pt-BR' ? 'Agrion | Apresentação do projeto' : 'Agrion | Project presentation')
      : (language === 'pt-BR' ? 'Agrion | Planejamento agrícola' : 'Agrion | Agricultural planning');
    const description = document.querySelector('meta[name="description"]');
    if (description) description.content = about
      ? (language === 'pt-BR' ? 'Conheça a proposta do Agrion, assista ao pitch quando disponível e explore o código do projeto da equipe Space Invaders.' : 'Explore Agrion, watch the pitch when available, and view the Space Invaders project repository.')
      : (language === 'pt-BR' ? 'O Agrion ajuda agricultores a explorar culturas, planejar rotações, acompanhar o clima e entender sua propriedade.' : 'Agrion helps farmers explore crops, plan rotations, monitor weather and understand their property.');
    const select = document.getElementById('agrionGlobalLanguage');
    if (select) select.value = language;
  }

  function set(value) {
    if (!valid(value)) return false;
    language = value;
    try { localStorage.setItem(key, value); } catch (_) {}
    apply();
    window.dispatchEvent(new CustomEvent('agrion:language', { detail: { language } }));
    return true;
  }

  window.AgrionLocale = { get: () => language, set, detect, valid, apply };
  apply();
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.getElementById('agrionGlobalLanguage')?.addEventListener('change', event => set(event.target.value));
  });
})();
