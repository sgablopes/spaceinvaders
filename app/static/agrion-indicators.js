(function(){
  'use strict';
  const node=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=text;return n;};
  const number=value=>new Intl.NumberFormat('pt-BR',{maximumFractionDigits:1}).format(value);
  function metric(label,value,unit,icon){
    const box=node('div','agrion-reading');const title=node('span','agrion-reading-label',label);
    const glyph=node('span','agrion-reading-icon');glyph.setAttribute('aria-hidden','true');
    const paths={thermometer:'<path d="M9 14.8V5a3 3 0 0 1 6 0v9.8a5 5 0 1 1-6 0Z"/><path d="M12 8v10"/>',wind:'<path d="M3 8h12a3 3 0 1 0-3-3M2 12h17a2 2 0 1 0-2-2M4 16h9a3 3 0 1 1-3 3"/>'};
    glyph.innerHTML=paths[icon]?`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">${paths[icon]}</svg>`:window.icon?.(icon,20)||'';
    box.append(glyph,title,node('strong','agrion-reading-value',Number.isFinite(value)?`${number(value)} ${unit}`:typeof value==='string'?value:'Indisponível'));
    return box;
  }
  function humidity(value,label='Umidade relativa do ar'){
    if(!Number.isFinite(value)||value<0||value>100)return metric(label,null,'%','droplet');
    const box=metric(label,value,'%','droplet'),ring=node('div','agrion-humidity-ring');
    ring.style.setProperty('--reading',`${value}%`);ring.setAttribute('role','meter');ring.setAttribute('aria-label',label);ring.setAttribute('aria-valuemin','0');ring.setAttribute('aria-valuemax','100');ring.setAttribute('aria-valuenow',String(value));
    ring.append(node('span','',`${number(value)}%`));box.querySelector('.agrion-reading-value').replaceWith(ring);return box;
  }
  const phases=[['soil_preparation','Preparo'],['planting','Plantio'],['growing','Crescimento'],['flowering','Floração'],['fruiting','Frutificação'],['harvesting','Colheita'],['post_harvest','Pós-colheita']];
  const normalize=text=>String(text||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toLowerCase();
  const aliases={preparo:'soil_preparation','preparo do solo':'soil_preparation',plantio:'planting',crescimento:'growing','crescimento vegetativo':'growing',vegetativo:'growing',floracao:'flowering',frutificacao:'fruiting',colheita:'harvesting','pos-colheita':'post_harvest'};
  function phase(estimate,declared,compact=false){
    const box=node('div','agrion-phase');const estimated=typeof estimate==='string'&&estimate.trim();
    const known=estimated?aliases[normalize(estimate)]:declared?.status==='confirmed'?declared.value?.stage:null;
    const extras={not_started:'Ainda não começou',planning:'Planejamento',fallow:'Pousio',other:'Outra fase'};
    const label=estimated?estimate:phases.find(([id])=>id===known)?.[1]||extras[known]||'Fase a confirmar';
    box.append(node('small','agrion-dashboard-source',estimated?'Fase estimada pela IA':known?'Fase informada na entrevista':'Desenvolvimento da cultura'),node('strong','agrion-phase-current',label));
    if(!compact&&phases.some(([id])=>id===known)){
      const list=node('ol','agrion-phase-track');list.setAttribute('aria-label','Etapas de referência do cultivo');
      for(const [id,title] of phases){const item=node('li',id===known?'is-current':'',title);if(id===known)item.setAttribute('aria-current','step');list.append(item);}box.append(list,node('small','agrion-dashboard-source','Etapas de referência; o ciclo varia conforme a cultura.'));
    }
    return box;
  }
  function rainfall(metrics){
    const items=(metrics||[]).filter(m=>m.unit==='mm'&&Number.isFinite(m.value)&&m.value>=0&&m.period_start&&m.period_end);
    if(items.length<2)return null;
    const duration=m=>Date.parse(m.period_end)-Date.parse(m.period_start);
    if(!Number.isFinite(duration(items[0]))||duration(items[0])<0||items.some(m=>duration(m)!==duration(items[0])))return null;
    const max=Math.max(...items.map(m=>m.value));const box=node('div','agrion-rain-bars');box.append(node('p','agrion-dashboard-muted','Acumulados em períodos de mesma duração'));
    for(const m of items){const row=node('div','agrion-rain-row');row.append(node('span','',`${m.label}: ${number(m.value)} mm`));const bar=node('div','agrion-rain-track'),fill=node('span');fill.style.width=`${max?m.value/max*100:0}%`;bar.setAttribute('aria-hidden','true');bar.append(fill);row.append(bar,node('small','agrion-dashboard-source',`${m.period_start} a ${m.period_end}`));box.append(row);}return box;
  }
  window.AgrionIndicators={metric,humidity,phase,rainfall};
})();
