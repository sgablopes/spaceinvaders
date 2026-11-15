(function(){
  'use strict';
  function append(root,entries){for(const html of entries||[]){if(typeof html!=='string'||!html||html.length>50000)continue;const frame=document.createElement('iframe');frame.className='agrion-search-suggestions';frame.title='Sugestões do Google Search';frame.setAttribute('sandbox','allow-popups allow-popups-to-escape-sandbox');frame.referrerPolicy='no-referrer';frame.srcdoc=html;root.append(frame);}}
  window.AgrionSearchSuggestions={append};
})();
