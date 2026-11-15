(function(){
  'use strict';
  let expanded=false,loadingTimer=null;
  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const icon=(name,size=28)=>window.icon?window.icon(name,size):'';
  const greeting=()=>{const hour=new Date().getHours();return hour<12?'Bom dia':hour<18?'Boa tarde':'Boa noite';};
  const picture=()=>'<picture class="agrion-home-picture"><source media="(min-width: 768px)" srcset="/static/agrion-hero-desktop.jpg"><img src="/static/agrion-hero-mobile.jpg" alt="Lavoura ao nascer do sol"></picture>';
  const brand=()=>`<div class="agrion-home-brand"><span class="agrion-home-brand-mark">${icon('leaf',35)}</span><strong>Agrion</strong></div>`;
  const owner=property=>`<div class="agrion-home-owner"><span class="agrion-home-owner-icon">${icon('home',27)}</span><div><span>${greeting()}, ${esc((property?.personName||'').trim().split(/\s+/)[0]||'você')}</span><strong>${esc(property?.propertyName||'Sua propriedade')}</strong></div></div>`;
  const features=[
    ['sun','Clima','Condições, previsões e estação Agrion'],
    ['sprout','Medições de campo','Histórico e análises'],
    ['calendar','Planejamento','Atividades e safras'],
    ['chart','Mercado agrícola','Preços e tendências'],
    ['book','Notícias e pesquisas','Conteúdo relevante'],
    ['map','Minha propriedade','Mapa, talhões e dados']
  ];
  const nav=[['home','Início'],['sprout','Planejar'],['satellite','Monitorar'],['chart','Mercado'],['map','Propriedade']];
  function markup(property){
    const featureCards=features.map(([symbol,title,description])=>`<button class="agrion-home-feature" type="button"><span>${icon(symbol,34)}</span><strong>${title}</strong><small>${description}</small></button>`).join('');
    const navigation=nav.map(([symbol,title],index)=>`<button type="button" class="agrion-home-nav-item ${index===0?'is-current':''}" ${index===0?'aria-current="page"':''}>${icon(symbol,23)}<span>${title}</span></button>`).join('');
    return `<main class="agrion-home"><div class="agrion-home-waiting"><header class="agrion-home-top">${brand()}<button class="agrion-home-bell" type="button" aria-label="Notificações">${icon('alert',22)}</button></header>${owner(property)}<div class="agrion-home-waiting-photo">${picture()}</div><section class="agrion-home-loading" aria-label="Preparando a visão geral"><div class="agrion-home-spinner" aria-hidden="true"></div><h1>Preparando sua visão geral</h1><p id="agrionHomeLoadingText" aria-live="polite">Organizando dados da propriedade…</p><small>As análises agrícolas estarão disponíveis em breve.</small></section></div><section id="agrionHomePanel" class="agrion-home-panel ${expanded?'is-expanded':''}" aria-label="Menu Agrion"><button id="agrionHomeMenuToggle" class="agrion-home-menu-toggle" type="button" aria-controls="agrionHomePanelContent" aria-expanded="${expanded}"><span class="agrion-home-menu-grip" aria-hidden="true"></span><span>${expanded?'Fechar menu':'Menu'}</span><span class="agrion-home-menu-arrow" aria-hidden="true">${expanded?'⌄':'⌃'}</span></button><div id="agrionHomePanelContent" class="agrion-home-panel-content" ${expanded?'':'inert'}><header class="agrion-home-top">${brand()}<button class="agrion-home-bell" type="button" aria-label="Notificações">${icon('alert',22)}</button></header>${owner(property)}<div class="agrion-home-hero">${picture()}</div><div class="agrion-home-content"><p class="agrion-home-kicker">VISÃO GERAL</p><h1>Seu campo, suas próximas decisões.</h1><p class="agrion-home-subtitle">Monitoramento, planejamento e inteligência para a sua produção.</p><div class="agrion-home-grid">${featureCards}</div><button type="button" class="agrion-home-assistant"><span aria-hidden="true">✦</span><span><strong>Assistente Agrion</strong><small>Tire dúvidas, analise dados e receba recomendações.</small></span><span aria-hidden="true">›</span></button></div><nav class="agrion-home-nav" aria-label="Navegação principal">${navigation}</nav></div></section></main>`;
  }
  function afterRender(){
    const panel=document.getElementById('agrionHomePanel'),content=document.getElementById('agrionHomePanelContent'),toggle=document.getElementById('agrionHomeMenuToggle');
    if(!panel||!content||!toggle)return;
    toggle.onclick=()=>{expanded=!expanded;panel.classList.toggle('is-expanded',expanded);content.inert=!expanded;toggle.setAttribute('aria-expanded',String(expanded));toggle.querySelector('span:nth-child(2)').textContent=expanded?'Fechar menu':'Menu';toggle.querySelector('.agrion-home-menu-arrow').textContent=expanded?'⌄':'⌃';document.body.classList.toggle('agrion-home-menu-open',expanded);};
    clearInterval(loadingTimer);
    const phrases=['Organizando dados da propriedade…','Levantando informações do campo…','Preparando a área de mercado…'];let index=0;
    loadingTimer=setInterval(()=>{const node=document.getElementById('agrionHomeLoadingText');if(!node){clearInterval(loadingTimer);loadingTimer=null;return;}node.textContent=phrases[++index%phrases.length];},3000);
  }
  function reset(){expanded=false;clearInterval(loadingTimer);loadingTimer=null;document.body.classList.remove('agrion-home-menu-open');}
  window.AgrionHome={markup,afterRender,reset};
})();
