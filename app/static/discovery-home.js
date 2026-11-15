(function(){
  'use strict';
  let expanded=false,stationOpen=false,planningOpen=false,page=null;
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const icon=(name,size=28)=>window.icon?window.icon(name,size):'';
  const greeting=()=>{const hour=new Date().getHours();return hour<12?'Bom dia':hour<18?'Boa tarde':'Boa noite';};
  const picture=()=>'<picture class="agrion-home-picture"><source media="(min-width: 768px)" srcset="/static/agrion-hero-desktop.jpg"><img src="/static/agrion-hero-mobile.jpg" alt="Lavoura ao nascer do sol"></picture>';
  const brand=()=>`<div class="agrion-home-brand"><span class="agrion-home-brand-mark">${icon('leaf',35)}</span><strong>Agrion</strong></div>`;
  const owner=property=>`<div class="agrion-home-owner"><span class="agrion-home-owner-icon">${icon('home',27)}</span><div><span>${greeting()}, ${esc((property?.personName||'').trim().split(/\s+/)[0]||'você')}</span><strong>${esc(property?.propertyName||'Sua propriedade')}</strong></div></div>`;
  const features=[
    ['sprout','Minha safra','Desenvolvimento e histórico'],
    ['brain','Análises do Agrion','Recomendações e pesquisas'],
    ['sun','Clima','Condições e previsões'],
    ['sprout','Medições de campo','Histórico e análises'],
    ['calendar','Planejamento','Atividades e safras'],
    ['chart','Mercado agrícola','Preços e tendências'],
    ['sun','Mini Estação Meteorológica','Leituras da estação'],
    ['map','Minha propriedade','Mapa, talhões e dados']
  ];
  const destinations={'Clima':'climate','Minha safra':'season','Análises do Agrion':'analysis','Mercado agrícola':'market','Medições de campo':'measurements','Minha propriedade':'property'};
  function openPage(next){reset();page=next;window.render();window.scrollTo(0,0);}
  function openStation(){reset();stationOpen=true;window.render();window.scrollTo(0,0);}
  function markup(property){
    if(page)return `<main class="agrion-home"><div class="agrion-home-waiting"><div id="agrionHomeHeader"><header class="agrion-home-top">${brand()}</header>${owner(property)}</div><div id="agrionSectionScreen"></div></div></main>`;
    if(planningOpen)return `<main class="agrion-home"><div class="agrion-home-waiting"><div id="agrionHomeHeader"><header class="agrion-home-top">${brand()}<button class="agrion-home-bell" type="button" aria-label="Notificações">${icon('alert',22)}</button></header>${owner(property)}</div><div id="agrionPlanningScreen"></div></div></main>`;
    if(stationOpen)return `<main class="agrion-home"><div class="agrion-home-waiting"><div id="agrionHomeHeader"><header class="agrion-home-top">${brand()}<button class="agrion-home-bell" type="button" aria-label="Notificações">${icon('alert',22)}</button></header>${owner(property)}</div><div id="agrionStationScreen"></div></div></main>`;
    const featureCards=features.map(([symbol,title,description])=>`<button class="agrion-home-feature" type="button" ${destinations[title]?`data-home-page="${destinations[title]}"`:title==='Minha propriedade'?'id="agrionHomeProperty"':title==='Mini Estação Meteorológica'?'id="agrionHomeStation"':title==='Planejamento'?'id="agrionHomePlanning"':''}><span>${icon(symbol,34)}</span><strong>${title}</strong><small>${description}</small></button>`).join('');
    return `<main class="agrion-home">
      <div class="agrion-home-waiting">
        <div id="agrionHomeHeader">
          <header class="agrion-home-top">${brand()}<button class="agrion-home-bell" type="button" aria-label="Notificações">${icon('alert',22)}</button></header>
          ${owner(property)}
        </div>
        <p class="agrion-home-kicker agrion-home-main-kicker">VISÃO GERAL</p>
        <section id="agrionHomeLoading" class="agrion-home-loading" aria-label="Preparando a visão geral"><div class="agrion-home-waiting-photo" aria-hidden="true">${picture()}</div><div class="agrion-home-loading-content"><div class="agrion-home-spinner" aria-hidden="true"></div><h1>Preparando sua visão geral</h1><p id="agrionHomeLoadingText" aria-live="polite">Organizando dados da propriedade…</p><button id="agrionDashboardRetry" class="agrion-dashboard-retry" type="button" hidden>Tentar novamente</button></div></section>
        <div id="agrionDashboard" class="agrion-dashboard" hidden></div>
        <div class="agrion-home-content agrion-home-main-copy"><h1>Seu campo, suas próximas decisões.</h1><p class="agrion-home-subtitle">Monitoramento, planejamento e inteligência para a sua produção.</p></div>
        <button type="button" class="agrion-home-assistant"><span class="agrion-home-assistant-avatar"><img src="/static/agrion-avatar.jpeg" alt=""></span><span><strong>Assistente Agrion</strong><small>Tire dúvidas, analise dados e receba recomendações.</small></span><span aria-hidden="true">›</span></button>
      </div>
      <section id="agrionHomePanel" class="agrion-home-panel ${expanded?'is-expanded':''}" aria-label="Menu Agrion">
        <button id="agrionHomeMenuToggle" class="agrion-home-menu-toggle" type="button" aria-controls="agrionHomePanelContent" aria-expanded="${expanded}"><span class="agrion-home-menu-grip" aria-hidden="true"></span><span>${expanded?'Fechar menu':'Menu'}</span><span class="agrion-home-menu-arrow" aria-hidden="true">${expanded?'⌄':'⌃'}</span></button>
        <div id="agrionHomePanelContent" class="agrion-home-panel-content" ${expanded?'':'inert'}>
          <div class="agrion-home-content"><div class="agrion-home-grid">${featureCards}<button id="agrionDeleteData" class="agrion-home-delete" type="button">Apagar dados</button></div><p id="agrionDeleteStatus" class="agrion-home-delete-status" role="status"></p></div>
        </div>
      </section>
    </main>`;
  }
  function afterRender(){
    if(page){void window.AgrionDashboard.attachPage(document.getElementById('agrionSectionScreen'),page);return;}
    if(planningOpen){void window.AgrionPlanning.attach(document.getElementById('agrionPlanningScreen'));return;}
    if(stationOpen){window.AgrionStation.attach(document.getElementById('agrionStationScreen'));return;}
    const panel=document.getElementById('agrionHomePanel'),content=document.getElementById('agrionHomePanelContent'),toggle=document.getElementById('agrionHomeMenuToggle');
    if(!panel||!content||!toggle)return;
    document.querySelectorAll('[data-home-page]').forEach(button=>button.onclick=()=>openPage(button.dataset.homePage));
    document.getElementById('agrionHomePlanning').onclick=()=>{expanded=false;planningOpen=true;document.body.classList.remove('agrion-home-menu-open');window.AgrionDashboard.reset();window.render();window.scrollTo(0,0);};
    document.getElementById('agrionHomeStation').onclick=()=>{expanded=false;stationOpen=true;document.body.classList.remove('agrion-home-menu-open');window.AgrionDashboard.reset();window.render();window.scrollTo(0,0);};
    document.querySelector('.agrion-home-assistant').onclick=()=>window.AgrionDiscovery.openChat();
    document.getElementById('agrionDashboardRetry').onclick=()=>window.AgrionDashboard.start();
    document.getElementById('agrionDeleteData').onclick=eraseData;
    const header=document.getElementById('agrionHomeHeader');
    const positionPanel=()=>{if(!header.isConnected){window.removeEventListener('resize',positionPanel);return;}panel.style.setProperty('--agrion-menu-space',`${Math.max(160,window.innerHeight-header.getBoundingClientRect().bottom)}px`);};
    positionPanel();window.addEventListener('resize',positionPanel,{passive:true});
    toggle.onclick=()=>{expanded=!expanded;panel.classList.toggle('is-expanded',expanded);content.inert=!expanded;toggle.setAttribute('aria-expanded',String(expanded));toggle.querySelector('span:nth-child(2)').textContent=expanded?'Fechar menu':'Menu';toggle.querySelector('.agrion-home-menu-arrow').textContent=expanded?'⌄':'⌃';document.body.classList.toggle('agrion-home-menu-open',expanded);};
    window.AgrionDashboard.start();
  }
  function clearDatabase(name){return new Promise((resolve,reject)=>{const request=indexedDB.open(name);request.onerror=()=>reject(request.error);request.onblocked=()=>reject(new Error('blocked'));request.onsuccess=()=>{const db=request.result,names=Array.from(db.objectStoreNames);if(!names.length){db.close();resolve();return;}const tx=db.transaction(names,'readwrite');for(const store of names)tx.objectStore(store).clear();tx.oncomplete=()=>{db.close();resolve();};tx.onerror=()=>{db.close();reject(tx.error);};tx.onabort=()=>{db.close();reject(tx.error||new Error('aborted'));};};});}
  async function eraseData(){if(!window.confirm('Apagar os dados do Agrion neste navegador? A propriedade, as conversas, análises e registros serão excluídos. Esta ação não pode ser desfeita. Feche outras abas do Agrion antes de continuar.'))return;const button=document.getElementById('agrionDeleteData'),status=document.getElementById('agrionDeleteStatus');button.disabled=true;status.textContent='Apagando dados…';window.AgrionDeletingData=true;window.AgrionHome.reset();try{for(const name of ['agrion-discovery','agrion-dashboard','flora-demo-registros-v1'])await clearDatabase(name);const keys=[];for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i);if(key==='agrion-property-v1'||key==='flora-demo-v3-1'||key?.startsWith('agrion-chat-v1:'))keys.push(key);}for(const key of keys)localStorage.removeItem(key);window.location.reload();}catch(_){window.AgrionDeletingData=false;button.disabled=false;status.textContent='Não foi possível apagar todos os dados. Feche outras abas do Agrion e tente novamente.';}}
  function showDashboard(){page=null;window.AgrionDashboard.reset();stationOpen=false;planningOpen=false;window.AgrionPlanning.close();window.AgrionStation.close();window.render();window.scrollTo(0,0);}
  function reset(){page=null;expanded=false;stationOpen=false;planningOpen=false;window.AgrionPlanning.close();window.AgrionStation.close();window.AgrionDashboard.reset();document.body.classList.remove('agrion-home-menu-open');}
  window.AgrionHome={markup,afterRender,reset,showDashboard,openPage,openStation};
})();
