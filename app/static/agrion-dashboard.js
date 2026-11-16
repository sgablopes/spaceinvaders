(function(){
  'use strict';
  let generation=0,currentContext=null,view='home';const inFlight=new Map();
  const labels={current_crop:'Cultura atual',current_season_stage:'Fase declarada',planting_date:'Data de plantio',primary_goal:'Objetivo',next_crop_preference:'Preferência de plantio'};
  const stages={not_started:'Ainda não começou',planning:'Planejamento',soil_preparation:'Preparo do solo',planting:'Plantio',growing:'Crescimento',flowering:'Floração',fruiting:'Frutificação',harvesting:'Colheita',post_harvest:'Pós-colheita',fallow:'Pousio',other:'Outra fase'};
  const goals={maximize_profit:'Aumentar lucro',increase_yield:'Aumentar produção',restore_soil:'Recuperar solo',reduce_risk:'Reduzir riscos',reduce_costs:'Reduzir custos',diversify:'Diversificar',other:'Outro objetivo'};
  function value(id,field){if(!field||field.status!=='confirmed'||!field.value)return 'Não informado';const v=field.value;if(id==='current_crop')return v.crop||'Não informado';if(id==='current_season_stage')return stages[v.stage]||'Não informado';if(id==='planting_date')return v.not_planted?'Ainda não plantou':v.date||'Não informado';if(id==='primary_goal')return goals[v.category]||v.description||'Não informado';if(id==='next_crop_preference')return v.no_preference?'Sem preferência':v.crop||'Não informado';return 'Não informado';}
  function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;}
  function pictogram(name){const node=element('span','agrion-crop-icon');node.setAttribute('aria-hidden','true');if(typeof window.icon==='function')node.innerHTML=window.icon(name,20);return node;}
  function cropRow(box,iconName,label,text){const row=element('div','agrion-crop-row'),content=element('div','agrion-crop-row-content');content.append(element('strong','',label),element('p','agrion-dashboard-muted',text));row.append(pictogram(iconName),content);box.append(row);}
  function card(title,description){const box=element('section','agrion-dashboard-card');box.append(element('h2','',title),element('p','agrion-dashboard-muted',description));return box;}
  function dateLabel(value){if(!value)return '';const date=new Date(value);return Number.isNaN(date.getTime())?String(value):new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short'}).format(date);}
  function localDay(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
  function zone(){return Intl.DateTimeFormat().resolvedOptions().timeZone||'local';}
  function cacheKey(context,section){const versions={stage:'stage-v4',daily:'daily-v3',news:'news-v3'};return `${context.property.id}:${versions[section]||section}`;}
  function signature(context){return JSON.stringify(context);}
  function fresh(record,section){if(!record?.saved_at)return false;const saved=Date.parse(record.saved_at);if(!Number.isFinite(saved)||saved>Date.now())return false;if(['daily','bootstrap'].includes(section))return record.local_day===localDay()&&record.timezone===zone();const ttl={forecast:3600000,rainfall:21600000,stage:86400000,news:21600000}[section]||0;return Date.now()-saved<ttl;}
  async function cached(context,section){const record=await window.AgrionDashboardCache.get(cacheKey(context,section));return record?.signature===signature(context)?record:null;}
  async function persist(context,section,result){await window.AgrionDashboardCache.put({key:cacheKey(context,section),signature:signature(context),saved_at:new Date().toISOString(),local_day:localDay(),timezone:zone(),result});}
  function singleFlight(context,section,work){const key=cacheKey(context,section)+':'+signature(context);if(inFlight.has(key))return inFlight.get(key);const promise=work().finally(()=>inFlight.delete(key));inFlight.set(key,promise);return promise;}
  function staleNote(box,savedAt){box.append(element('small','agrion-dashboard-stale',`Resultado antigo, salvo em ${dateLabel(savedAt)}. Atualização pendente ou indisponível.`));}
  function addSources(box,urls){for(const source of urls||[]){try{const url=new URL(source);if(!['http:','https:'].includes(url.protocol))continue;const link=element('a','agrion-dashboard-link',url.hostname);link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';box.append(link);}catch(_){}}}
  function expandable(title){const details=element('details','agrion-dashboard-expand');details.append(element('summary','',title||'Ver análise'));return details;}
  function confidence(container,data){if(!container||!data||!Number.isInteger(data.value))return;const wrap=element('details','agrion-confidence'),summary=element('summary','',`${data.value}% confiança estimada ⓘ`),why=element('span','agrion-confidence-reason',data.reason);wrap.append(summary,why);container.append(wrap);}
  function renderDaily(result,staleAt=null){
    const box=document.getElementById('agrionDashboard-daily'),recommendations=document.getElementById('agrionDashboard-recommendations');
    if(!box||!recommendations)return;
    box.replaceChildren(element('h2','',staleAt?'Última análise do Agrion':'O que o Agrion analisou hoje'));
    recommendations.replaceChildren(element('h2','','Recomendações práticas'));
    if(result?.status!=='ready'){
      box.append(element('p','agrion-dashboard-muted',result?.note||'Análise diária indisponível.'));
      recommendations.append(element('p','agrion-dashboard-muted','Nenhuma recomendação fundamentada disponível.'));
      return;
    }
    const details=expandable(result.headline||result.summary?.headline||'Ver análise');
    if(result.summary)details.append(element('p','agrion-dashboard-muted',result.summary.text));
    for(const item of result.observations||[]){const line=element('div','agrion-dashboard-observation');line.append(element('p','agrion-dashboard-muted',item.text));details.append(line);}
    box.append(details,element('small','agrion-dashboard-source',`Análise por IA · ${dateLabel(result.generated_at)}`));
    if(result.recommendations?.length){for(const item of result.recommendations){const detail=expandable(item.headline||'Ver recomendação');detail.append(element('p','agrion-dashboard-muted',item.text));recommendations.append(detail);}}
    else recommendations.append(element('p','agrion-dashboard-muted','Nenhuma recomendação fundamentada disponível.'));
    window.AgrionSearchSuggestions.append(box,result.search_entry_points,{compact:true});
    if(staleAt){staleNote(box,staleAt);staleNote(recommendations,staleAt);}
  }
  function showGdd(box,gdd){if(!gdd){box.append(element('small','agrion-dashboard-source','Graus-dia: indisponível sem temperatura-base fundamentada.'));return;}box.append(element('p','agrion-dashboard-detail',`Graus-dia acumulados: ${new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2}).format(gdd.value)} °C dia`),element('small','agrion-dashboard-source',`NASA POWER · temperatura-base ${gdd.base_temperature_c} °C · referência: ${gdd.base_temperature_reference}`));}
  function renderSection(section,result){const box=document.getElementById(`agrionDashboard-${section}`);if(!box)return;const title={forecast:'Clima e previsão',rainfall:'Chuva acumulada',stage:'Desenvolvimento da cultura'}[section];box.replaceChildren(element('h2','',title));if(section==='stage'){const fields=currentContext?.agricultural_profile?.fields||{};box.classList.add('agrion-crop-card');const heading=element('div','agrion-crop-heading');heading.append(pictogram('sprout'));const headingText=element('div');headingText.append(element('small','agrion-crop-eyebrow','CULTURA ATUAL'),element('p','agrion-dashboard-value',value('current_crop',fields.current_crop)));heading.append(headingText);box.append(heading);}if(result?.status!=='ready'){box.append(element('p','agrion-dashboard-muted',result?.note||'Informação indisponível no momento.'));if(section==='stage'){box.append(window.AgrionIndicators.phase(null,currentContext?.agricultural_profile?.fields?.current_season_stage));showGdd(box,result?.gdd);}return;}
    if(section==='stage'){
      box.append(window.AgrionIndicators.phase(result.phase,currentContext?.agricultural_profile?.fields?.current_season_stage));
      if(result.harvest_window)cropRow(box,'calendar','Janela estimada de colheita',result.harvest_window);
      const more=expandable('Veja mais · estimativa e referências');
      cropRow(more,'info','O que foi considerado',result.reason);confidence(more,result.phase_confidence);confidence(more,result.harvest_confidence);showGdd(more,result.gdd);box.append(more);
      box.append(element('small','agrion-dashboard-source',`Estimativa por IA · ${dateLabel(result.generated_at)}`));
      window.AgrionSearchSuggestions.append(box,result.search_entry_points,{compact:true});return;
    }

    const metrics=element('div','agrion-weather-values');box.append(metrics);
    const more=expandable('Veja mais · períodos e fontes');
    for(const metric of result.metrics||[]){
      const ui=window.AgrionIndicators,humidity=metric.key==='relative_humidity'&&metric.unit==='%';
      metrics.append(humidity?ui.humidity(metric.value,'Umidade prevista do ar'):ui.metric(metric.label,metric.value,metric.unit,metric.key==='temperature'?'thermometer':metric.key==='wind_speed'?'wind':'droplet'));
      if(metric.forecast_for)more.append(element('small','agrion-dashboard-source',`${metric.label}: previsto para ${dateLabel(metric.forecast_for)}${metric.interval_start?' · desde '+dateLabel(metric.interval_start):''}`));
      if(metric.period_start&&metric.period_end)more.append(element('small','agrion-dashboard-source',`${metric.label}: ${metric.period_start} a ${metric.period_end} · UTC`));
    }
    if(section==='rainfall'){const chart=window.AgrionIndicators.rainfall(result.metrics);if(chart)box.append(chart);}
    box.append(element('small','agrion-dashboard-source',`${result.source||''} · ${section==='forecast'?'Previsão, não medição no terreno':'Estimativa regional histórica'}`));
    more.append(element('small','agrion-dashboard-source',`${result.source_accessed_at?'Fonte consultada em '+dateLabel(result.source_accessed_at):''} · ${result.note||''}`));
    addSources(more,result.source_url?[result.source_url]:[]);box.append(more);
  }

  function displaySection(section,result,staleAt=null){
    if(view==='home'&&['daily','forecast','stage'].includes(section)){if(section==='stage'){const harvest=document.getElementById('agrionOverviewHarvest');if(harvest)harvest.textContent=result?.harvest_window||'Indisponível';}renderCompact(section,result,staleAt);return;}
    if(section==='daily'){renderDaily(result,staleAt);return;}
    if(section==='news'){
      const box=document.getElementById('agrionDashboard-news');if(!box)return;
      box.replaceChildren(element('h2','','Notícias e pesquisas'));
      if(result?.status!=='ready')box.append(element('p','agrion-dashboard-muted',result?.note||'Notícias indisponíveis.'));
      else{
        for(const item of result.items||[]){const article=element('article','agrion-dashboard-observation'),details=expandable(item.title);details.append(element('p','agrion-dashboard-muted',item.summary));if(item.date)details.append(element('small','agrion-dashboard-source',item.date));article.append(details);box.append(article);}
        window.AgrionSearchSuggestions.append(box,result.search_entry_points,{compact:true});
      }
      if(staleAt)staleNote(box,staleAt);return;
    }
    if(section==='stage'){
      const harvest=document.getElementById('agrionOverviewHarvest');
      if(harvest){harvest.textContent=result?.status==='ready'&&result.harvest_window?`${result.harvest_window}${staleAt?' (estimativa anterior)':''}`:'Indisponível';harvest.parentElement.querySelector('.agrion-confidence')?.remove();if(result?.status==='ready')confidence(harvest.parentElement,result.harvest_confidence);}
    }
    renderSection(section,result);
    if(staleAt){const box=document.getElementById(`agrionDashboard-${section}`);if(box)staleNote(box,staleAt);}
  }
  async function request(context,section){return singleFlight(context,section,async()=>{const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),section==='bootstrap'?90000:150000);try{const response=await fetch(`/api/dashboard/${section}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({context}),signal:controller.signal});if(!response.ok)throw Error('unavailable');const data=await response.json();if(data.property_id!==context.property.id)throw Error('property_mismatch');return section==='bootstrap'?data:data.result;}finally{clearTimeout(timer);}});}
  async function updateSection(section,context,id){const previous=await cached(context,section);if(id!==generation)return;if(previous){displaySection(section,previous.result,fresh(previous,section)?null:previous.saved_at);if(fresh(previous,section))return;}try{const result=await request(context,section);if(result?.status!=='ready'){if(id===generation){if(previous)displaySection(section,previous.result,previous.saved_at);else displaySection(section,result);}return;}await persist(context,section,result);if(id===generation)displaySection(section,result);}catch(_){if(id===generation){if(previous)displaySection(section,previous.result,previous.saved_at);else displaySection(section,{status:'error',note:'Não foi possível atualizar esta seção.'});}}}
  function show(context,result,error,staleAt=null){const root=document.getElementById('agrionDashboard');const loading=document.getElementById('agrionHomeLoading');if(!root||!loading)return;const current=window.AgrionPropertyStore.read();if(current?.propertyId!==context.property.id)return;currentContext=context;
    root.replaceChildren();const fields=context.agricultural_profile.fields;const overview=element('section','agrion-property-overview');overview.setAttribute('aria-label','Visão da propriedade');const map=element('div','agrion-overview-map');map.id='agrionOverviewMap';const mapStatus=element('span','agrion-overview-map-status','Carregando mapa…');mapStatus.id='agrionOverviewMapStatus';const overlay=element('div','agrion-overview-overlay');overlay.append(element('h2','',context.property.name||'Sua propriedade'),element('p','',context.property.location_label||'Localização não informada'));const grid=element('div','agrion-overview-grid');for(const id of ['current_crop','planting_date','primary_goal']){const item=element('div','agrion-overview-item');const fieldValue=element('strong','',value(id,fields[id]));item.append(element('small','',labels[id]),fieldValue);grid.append(item);}const item=element('div','agrion-overview-item');const harvestDisplay=element('strong','','Consultando…');harvestDisplay.id='agrionOverviewHarvest';item.append(element('small','','Colheita estimada'),harvestDisplay);grid.append(item);overlay.append(grid);overview.append(map,mapStatus,overlay);root.append(overview);
    const station=element('section','agrion-dashboard-card agrion-station-live');station.id='agrionDashboard-station';root.append(station);window.AgrionStation.attachSummary?.(station);
    addSection(root,'daily','Resumo do dia');
    const indicators=element('div','agrion-home-indicators');root.append(indicators);
    addSection(indicators,'forecast','Clima');addSection(indicators,'stage','Minha safra');
    loading.hidden=true;root.hidden=false;void window.AgrionPropertyOverview.attach(context);
    for(const section of ['daily','forecast','stage'])void updateSection(section,context,generation);
  }
  function addSection(root,id,title){const box=card(title,'Consultando informações…');box.id=`agrionDashboard-${id}`;root.append(box);return box;}
  function navigateButton(box,label,page){const button=element('button','agrion-section-link',label+' →');button.type='button';button.onclick=()=>window.AgrionHome.openPage(page);box.append(button);}
  function renderCompact(section,result,staleAt){
    const box=document.getElementById(`agrionDashboard-${section}`);if(!box)return;
    const config={daily:['Resumo do dia','brain','analysis'],forecast:['Clima previsto','sun','climate'],stage:['Minha safra','sprout','season']}[section];
    box.replaceChildren(pictogram(config[1]),element('h2','',config[0]));
    if(result?.status!=='ready')box.append(element('p','agrion-dashboard-muted','Informação ainda não disponível. Consulte os detalhes para atualizar.'));
    else if(section==='daily'){
      box.append(element('p','agrion-summary-headline',result.headline||result.summary?.headline||'Análise do dia disponível'));
      const list=element('ul','agrion-summary-list');for(const item of (result.recommendations||[]).slice(0,3)){if(item.headline)list.append(element('li','',item.headline));}box.append(list);
      window.AgrionSearchSuggestions.append(box,result.search_entry_points,{compact:true});
    }else if(section==='forecast'){
      for(const metric of (result.metrics||[]).slice(0,2))cropRow(box,metric.key==='temperature'?'sun':'droplet',metric.label,`${new Intl.NumberFormat('pt-BR',{maximumFractionDigits:1}).format(metric.value)} ${metric.unit}`);
      if(result.source)box.append(element('small','agrion-dashboard-source',result.source));
    }else{
      box.append(window.AgrionIndicators.phase(result.phase,currentContext.agricultural_profile.fields.current_season_stage,true));
      window.AgrionSearchSuggestions.append(box,result.search_entry_points,{compact:true});
    }
    if(staleAt)staleNote(box,staleAt);navigateButton(box,'Ver detalhes',config[2]);
  }
  function renderHistory(root,fields){
    const history=card('Histórico de cultivo','Informações fornecidas pelo agricultor.');const historyFields=[['last_crop','Última cultura'],['previous_crop','Cultura anterior']];for(const [id,label] of historyFields){const field=fields[id],v=field?.value;if(field?.status!=='confirmed'||!v)continue;const text=v.never_cultivated?'Nunca cultivou':v.no_previous_cultivation?'Sem cultivo anterior':v.crop;if(text)history.append(element('p','agrion-dashboard-detail',`${label}: ${text}`));}const harvest=fields.last_harvest_result;if(harvest?.status==='confirmed'&&harvest.value){const v=harvest.value;if(typeof v.quantity==='number'&&Number.isFinite(v.quantity))history.append(element('p','agrion-dashboard-detail',`Última colheita: ${new Intl.NumberFormat('pt-BR').format(v.quantity)} ${v.unit||''}`));else if(v.qualitative_result==='not_applicable')history.append(element('p','agrion-dashboard-detail','Ainda não houve colheita.'));else if(v.qualitative_result==='no_harvest')history.append(element('p','agrion-dashboard-detail','Última safra sem colheita.'));}history.append(element('small','agrion-dashboard-source','Atividades e diário de campo ainda não conectados.'));root.append(history);
  }
  const pages={climate:['Clima','sun',['forecast','rainfall']],season:['Minha safra','sprout',['stage']],analysis:['Análises do Agrion','brain',['daily','recommendations','news']],market:['Mercado agrícola','chart',[]],measurements:['Medições de campo','leaf',[]],property:['Minha propriedade','map',[]]};
  async function attachPage(root,page){
    reset();view=page;const id=generation,config=pages[page];if(!root||!config)return;
    root.className='agrion-section-page';
    const back=element('button','agrion-section-link','← Voltar à visão geral');back.type='button';back.onclick=()=>window.AgrionHome.showDashboard();
    const heading=element('header','agrion-section-heading');heading.append(pictogram(config[1]),element('h1','',config[0]));root.replaceChildren(back,heading);
    const content=element('div','agrion-section-content');root.append(content);
    try{
      const context=await window.AgrionContext.load();if(id!==generation)return;currentContext=context;const fields=context.agricultural_profile.fields;
      const titles={forecast:'Clima e previsão',rainfall:'Chuva acumulada',stage:'Desenvolvimento da cultura',daily:'O que o Agrion analisou hoje',recommendations:'Recomendações práticas',news:'Notícias e pesquisas'};
      for(const section of config[2])addSection(content,section,titles[section]);
      if(page==='season')renderHistory(content,fields);
      if(page==='market'){addSection(content,'market','Produção e mercado');void window.AgrionMarket.attach(context);}
      if(page==='measurements'){
        const box=card('Solo e registros de campo','Ainda não há medições de solo registradas nesta área. As leituras meteorológicas estão na Mini Estação.');content.append(box);
        for(const [key,label] of [['soil_management','Manejo do solo'],['fertilization','Adubação'],['cover_crops','Cobertura do solo']])profileField(box,fields,key,label);
        const button=element('button','agrion-section-link','Abrir Mini Estação →');button.onclick=()=>window.AgrionHome.openStation();box.append(button);
      }
      if(page==='property'){
        const box=card(context.property.name||'Sua propriedade',context.property.location_label||'Localização a confirmar');content.append(box);
        if(context.property.area_hectares!=null)cropRow(box,'map','Área',new Intl.NumberFormat('pt-BR',{maximumFractionDigits:3}).format(context.property.area_hectares)+' ha');
        for(const key of ['current_crop','planting_date','primary_goal','next_crop_preference'])cropRow(box,'leaf',labels[key],value(key,fields[key]));
        const extra=card('Informações da entrevista','Dados informados por você.');content.append(extra);
        for(const [key,label] of [['irrigation','Irrigação'],['water_access','Acesso à água'],['mechanization','Mecanização'],['main_difficulties','Dificuldades'],['soil_management','Manejo do solo'],['fertilization','Adubação']])profileField(extra,fields,key,label);
        const edit=element('button','agrion-section-link','Editar mapa da propriedade →');edit.onclick=()=>window.AgrionDiscovery.editProperty();box.append(edit);
      }
      for(const section of config[2].filter(x=>x!=='recommendations'))void updateSection(section,context,id);
    }catch(_){if(id===generation){content.append(card('Dados indisponíveis','Não foi possível carregar os dados salvos.'));const retry=element('button','agrion-section-link','Tentar novamente');retry.onclick=()=>attachPage(root,page);content.append(retry);}}
  }
  function profileField(box,fields,key,label){
    const field=fields[key];if(field?.status!=='confirmed'||!field.value)return;const v=field.value;
    const regimes={rainfed:'Depende da chuva',irrigated:'Usa irrigação',mixed:'Chuva e irrigação',unknown:'A confirmar'};
    const work={manual:'Principalmente manual',mixed:'Manual e máquinas',mechanized:'Principalmente máquinas',automated:'Automatizado',unknown:'A confirmar'};
    const issues={drought:'Seca',excess_rain:'Excesso de chuva',pests:'Pragas',diseases:'Doenças',soil:'Solo',input_costs:'Custo de insumos',labor:'Mão de obra',machinery:'Máquinas',market:'Mercado',other:'Outras dificuldades'};
    let text=typeof v==='string'?v:v.description||v.notes||v.text;
    if(key==='irrigation')text=regimes[v.water_regime]||text;
    if(key==='mechanization')text=[work[v.work_mode],...(v.equipment||[])].filter(Boolean).join(' · ');
    if(key==='main_difficulties')text=[...(v.categories||[]).map(x=>issues[x]).filter(Boolean),text].filter(Boolean).join(' · ');
    if(text)cropRow(box,'leaf',label,text);
  }

  async function start(){reset();view='home';const id=generation;try{const context=await window.AgrionContext.load();if(id!==generation)return;show(context,null,false);}catch(_){if(id!==generation)return;const loading=document.getElementById('agrionHomeLoading');if(loading){loading.querySelector('.agrion-home-spinner').hidden=true;document.getElementById('agrionHomeLoadingText').textContent='Não foi possível carregar os dados da propriedade.';document.getElementById('agrionDashboardRetry').hidden=false;}}}
  function reset(){generation++;window.AgrionStation.close();window.AgrionPropertyOverview.reset();window.AgrionMarket.reset();}
  window.AgrionDashboard={start,reset,attachPage};
})();
