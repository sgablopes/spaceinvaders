(function(){
  'use strict';
  const observed=new Map();
  const removal=new MutationObserver(()=>{for(const [frame,observer] of observed){if(!frame.isConnected){observer.disconnect();observed.delete(frame);}}});
  removal.observe(document.documentElement,{childList:true,subtree:true});
  function append(root,entries,options={}){
    if(!root)return;const seen=new Set();
    for(const html of entries||[]){
      if(typeof html!=='string'||!html||html.length>50000||options.compact&&seen.has(html))continue;seen.add(html);
      const frame=document.createElement('iframe');frame.className='agrion-search-suggestions';frame.title='Sugestões do Google Search';
      // Scripts remain disabled. Same-origin permits measuring the static provider HTML.
      frame.setAttribute('sandbox',`allow-popups allow-popups-to-escape-sandbox${options.compact?' allow-same-origin':''}`);
      frame.referrerPolicy='no-referrer';
      if(options.compact){
        frame.classList.add('is-compact');
        frame.onload=()=>{
          try{
            const body=frame.contentDocument?.body;if(!body||!frame.isConnected)return;
            observed.get(frame)?.disconnect();
            const measure=()=>{if(!frame.isConnected)return;const style=frame.contentWindow.getComputedStyle(body);const height=Math.ceil(Math.max(body.getBoundingClientRect().height,body.scrollHeight)+(parseFloat(style.marginTop)||0)+(parseFloat(style.marginBottom)||0));if(height>0&&frame.style.height!==height+'px')frame.style.height=height+'px';};
            const observer=new ResizeObserver(measure);observer.observe(body);
            const changes=new MutationObserver(measure);changes.observe(body,{childList:true,subtree:true,attributes:true,characterData:true});
            observed.set(frame,{disconnect(){observer.disconnect();changes.disconnect();}});measure();
          }catch(_){/* Cross-origin navigation keeps the last usable frame size. */}
        };
      }
      frame.srcdoc=html;root.append(frame);
    }
  }
  window.AgrionSearchSuggestions={append};
})();
