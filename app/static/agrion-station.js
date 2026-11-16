(function(){
  'use strict';
  const storageKey='agrion-station-id-v1',valid=/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
  let cleanup=null;
  const T=text=>window.AgrionToolsLanguage?.t(text)||window.AgrionDashboardLanguage?.t(text)||text;
  const node=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=T(text);return n;};
  function stationId(){try{const id=localStorage.getItem(storageKey);return valid.test(id||'')?id:'agrion-demo-001';}catch(_){return 'agrion-demo-001';}}
  function close(){cleanup?.();cleanup=null;}
  function watch(root,id){
    close();let stopped=false,timer=null,controller=null,last=null,failed=false;
    const heading=node('div','agrion-station-live-heading');heading.append(node('div','',id));
    const status=node('span','agrion-station-status','Consultando…');status.setAttribute('role','status');heading.append(status);
    const date=node('small','agrion-dashboard-source'),values=node('div','agrion-station-values');
    root.replaceChildren(heading);
    if(id==='agrion-demo-001')root.append(node('p','agrion-dashboard-muted','Estação de demonstração · localização independente da propriedade.'));
    root.append(date,values);
    function render(){
      const stamp=Date.parse(last?.received_at),age=Date.now()-stamp,recent=Number.isFinite(stamp)&&age>=-5000&&age<=60000;
      status.textContent=T(failed?'Atualização indisponível':!last?'Sem leituras':recent?'Leitura recente':'Leitura antiga');
      status.dataset.state=failed?'unavailable':!last?'empty':recent?'recent':'old';
      date.textContent=Number.isFinite(stamp)?`${T('Recebida em')} ${new Date(stamp).toLocaleString(window.AgrionLocale?.get()||'pt-BR')}${failed?' · '+T('última leitura preservada'):''}`:T(last?'Horário indisponível':'Aguardando o primeiro envio da estação.');
      values.replaceChildren();if(!last)return;const v=last.measurements||{},ui=window.AgrionIndicators;
      values.append(ui.metric('Temperatura',v.temperature_c,'°C','thermometer'),ui.humidity(v.humidity_pct),ui.metric('Vento estimado',v.vento_estimado_m_s,'m/s','wind'),ui.metric('Chuva detectada',typeof v.rain_detected==='boolean'?(v.rain_detected?'Detectada':'Não detectada'):null,'','droplet'));
    }
    async function refresh(){
      if(stopped||controller||document.visibilityState==='hidden')return;
      const request=new AbortController();controller=request;const timeout=setTimeout(()=>request.abort(),10000);
      try{const response=await fetch(`/api/v1/stations/${encodeURIComponent(id)}/telemetry/latest`,{cache:'no-store',signal:request.signal});if(!response.ok)throw Error('unavailable');const data=await response.json();if(stopped)return;last=data.reading||null;failed=false;render();}
      catch(_){if(!stopped){failed=true;render();}}
      finally{clearTimeout(timeout);controller=null;if(!stopped){clearTimeout(timer);timer=setTimeout(refresh,5000);}}
    }
    function visibility(){clearTimeout(timer);if(document.visibilityState==='visible'){if(last)render();void refresh();}else controller?.abort();}
    document.addEventListener('visibilitychange',visibility);
    cleanup=()=>{stopped=true;clearTimeout(timer);controller?.abort();document.removeEventListener('visibilitychange',visibility);};
    void refresh();
  }
  function attachSummary(container){
    const title=node('h2','','Minha estação'),live=node('div');
    const link=node('button','agrion-section-link','Abrir Mini Estação →');link.type='button';link.onclick=()=>window.AgrionHome.openStation();
    container.replaceChildren(title,live,link);watch(live,stationId());
  }
  function attach(container){
    close();const shell=node('div','agrion-home-content agrion-station');
    const back=node('button','agrion-station-back','← Voltar à visão geral');back.type='button';back.onclick=()=>window.AgrionHome.showDashboard();
    const form=node('form','agrion-dashboard-card agrion-station-form'),label=node('label','agrion-market-field','ID da estação'),input=node('input');
    input.name='station_id';input.value=stationId();input.maxLength=64;input.required=true;input.pattern=valid.source;label.append(input);
    const button=node('button','btn btn-primary','Vincular estação');button.type='submit';const status=node('p','agrion-market-status');status.setAttribute('role','status');form.append(label,button,status);
    const readings=node('section','agrion-dashboard-card agrion-station-live');
    shell.append(back,node('h1','','Mini Estação Meteorológica'),node('p','agrion-home-subtitle','Leituras recebidas da estação vinculada.'),form,readings);container.replaceChildren(shell);
    form.onsubmit=e=>{e.preventDefault();const id=input.value.trim();if(!valid.test(id)){status.textContent=T('Informe um ID válido.');return;}try{localStorage.setItem(storageKey,id);status.textContent=T(`Estação ${id} vinculada neste navegador.`);}catch(_){status.textContent=T('Estação aberta nesta sessão; o navegador não conseguiu salvar o vínculo.');}watch(readings,id);};
    watch(readings,stationId());
  }
  window.AgrionStation={attach,attachSummary,close,stationId};
  window.addEventListener('agrion:language',()=>{const page=document.querySelector('.agrion-station');if(page?.parentElement){const typed=page.querySelector('input[name="station_id"]')?.value;const container=page.parentElement;attach(container);if(typed!=null)container.querySelector('input[name="station_id"]').value=typed;}});
})();
