(function () {
  'use strict';

  const store = window.AgrionPropertyStore;
  const key = window.AGRION_CONFIG.maptilerKey;
  const assets = [
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
    'https://unpkg.com/@geoman-io/leaflet-geoman-free@2.20.6/dist/leaflet-geoman.js',
    'https://cdn.maptiler.com/maptiler-geocoding-control/v3.1.0/leaflet.umd.js'
  ];
  let saved = store.read();
  let view = saved?.geometry ? 'saved' : 'welcome';
  let map = null;
  let polygon = null;
  let locationLabel = saved?.locationLabel || '';
  let mapLoading = null;
  let generation = 0;
  let editingFromHome = false;

  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const hectares = area => new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(area / 10000);

  function script(url) {
    return new Promise((resolve, reject) => {
      const node = document.createElement('script');
      node.src = url;
      node.onload = resolve;
      node.onerror = () => reject(new Error('Não foi possível carregar os recursos do mapa. Verifique sua conexão.'));
      document.head.appendChild(node);
    });
  }

  function loadMapLibraries() {
    if (!mapLoading) mapLoading = assets.reduce((chain, url) => chain.then(() => script(url)), Promise.resolve()).catch(error => { mapLoading = null; throw error; });
    return mapLoading;
  }

  function tearDownMap() {
    generation += 1;
    if (map) { map.remove(); map = null; }
    polygon = null;
  }

  function setView(next) {
    if (view === 'map' || view === 'saved') tearDownMap();
    view = next;
    window.render();
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  function identifyMarkup() {
    return `<main class="property-intro"><div class="property-form-card">
      <div class="property-mini-brand"><span class="welcome-brand-icon">${icon('leaf',22)}</span><strong>Agrion</strong></div>
      <button type="button" class="property-back" data-action="propertyBack">${icon('back',17)} Voltar</button>
      <p class="eyebrow">Primeiro acesso · sem criar conta</p>
      <h1>Vamos conhecer você e sua propriedade.</h1>
      <p class="property-description">Antes de começar, conte como podemos chamar você e sua propriedade.</p>
      <form id="propertyIdentityForm" novalidate>
        <label class="label" for="propertyPersonName">Seu nome <span aria-hidden="true">*</span></label>
        <input id="propertyPersonName" class="field" name="personName" type="text" autocomplete="name" maxlength="100" required value="${escape(saved?.personName || '')}" placeholder="Como podemos chamar você?">
        <label class="label" for="propertyNameInput">Nome da propriedade <span class="property-optional">(opcional)</span></label>
        <input id="propertyNameInput" class="field" name="propertyName" type="text" maxlength="120" value="${escape(saved?.propertyName === 'Minha propriedade' ? '' : saved?.propertyName || '')}" placeholder="Ex.: Sítio Boa Vista">
        <p id="propertyFormError" class="property-error" role="alert" hidden></p>
        <button type="submit" class="btn btn-primary">Continuar ${icon('arrow',18)}</button>
      </form><p class="property-footnote">Suas informações ficam apenas neste navegador, sem sincronização entre dispositivos.</p>
    </div></main><div id="toastMount" aria-live="polite"></div>`;
  }

  function mapMarkup() {
    const confirmed = view === 'saved';
    const name = saved?.propertyName || 'Minha propriedade';
    return `<main class="property-screen"><header class="property-header">
      <div class="property-header-brand"><span class="welcome-brand-icon">${icon('leaf',21)}</span><strong>Agrion</strong></div>
      <div><p class="eyebrow">${confirmed ? `Olá, ${escape(saved.personName)}` : `Vamos localizar seu terreno, ${escape(saved?.personName || '')}`}</p><h1>Minha propriedade</h1><p>${escape(name)}<span id="propertyLocationLabel">${locationLabel ? ` · ${escape(locationLabel)}` : ''}</span></p></div>
    ${editingFromHome ? '<button type="button" class="property-back" data-action="propertyReturnHome">Voltar</button>' : ''}</header><div class="property-map-layout"><div class="property-map-wrap">
      <div id="propertyMap" class="property-map" role="application" aria-label="Mapa de satélite para localizar e desenhar a propriedade"></div>
      <div id="propertyMapMessage" class="property-map-message" role="status">${key ? 'Carregando mapa de satélite…' : 'Chave do MapTiler não configurada. Configure MAPTILER_API_KEY para usar o mapa.'}</div>
    </div><section class="property-panel" aria-label="Informações do terreno">
      <div class="property-panel-handle" aria-hidden="true"></div>
      <p class="eyebrow">${confirmed ? 'Terreno cadastrado' : 'Cadastro geográfico'}</p>
      <h2>${escape(name)}</h2>
      <p class="property-panel-guide">${confirmed ? 'Seu perímetro está salvo neste navegador. Você pode ampliar o mapa ou editar o terreno.' : 'Encontre a plantação pela busca ou pelo GPS. Depois, toque em Desenhar terreno e marque os vértices no mapa.'}</p>
      <div class="property-area"><span>${confirmed ? '1 área cadastrada' : 'Área delimitada'}</span><strong id="propertyAreaValue">${saved?.geometry ? hectares(saved.areaSquareMeters) + ' ha' : '—'}</strong><small id="propertySquareMeters">${saved?.geometry ? new Intl.NumberFormat('pt-BR', {maximumFractionDigits: 0}).format(saved.areaSquareMeters) + ' m²' : 'Desenhe um perímetro para calcular'}</small></div>
      <p class="property-area-note">Área estimada a partir do contorno manual; confirme os limites antes de usar este valor.</p>
      <div class="property-tools">
        <button type="button" class="btn btn-secondary" data-action="propertyGPS">${icon('pin',17)} Usar minha localização</button>
        ${confirmed ? `<button type="button" class="btn btn-secondary" data-action="propertyEdit">${icon('compare',17)} Editar terreno</button><button type="button" class="btn btn-primary" data-action="propertyNext">Continuar ${icon('arrow',17)}</button>` : `
          <button type="button" class="btn btn-secondary" data-action="propertyDraw">${icon('plus',17)} Desenhar terreno</button>
          <button type="button" class="btn btn-secondary" data-action="propertyEditVertices">${icon('compare',17)} Editar vértices</button>
          <button type="button" class="btn btn-secondary" data-action="propertyUndo">${icon('back',17)} Desfazer ponto</button>
          <button type="button" class="btn btn-secondary" data-action="propertyClear">${icon('reset',17)} Limpar desenho</button>
          <button type="button" class="btn btn-primary property-confirm" id="propertyConfirm" data-action="propertyConfirm" disabled>Confirmar minha propriedade ${icon('arrow',17)}</button>`}
      </div><p class="property-footnote">Dados salvos somente neste navegador. Sem sincronização entre dispositivos.</p>
    </section></div>${confirmed ? '<button type="button" class="discovery-fab" data-action="propertyNext" aria-label="Conversar com Agrion" title="Conversar com Agrion">✦</button>' : ''}</main><div id="toastMount" aria-live="polite"></div>`;
  }

  function markup() { return view === 'identify' ? identifyMarkup() : mapMarkup(); }

  function updateArea() {
    const geometry = polygon?.toGeoJSON()?.geometry;
    const area = geometry ? store.areaSquareMeters(geometry) : 0;
    const value = document.getElementById('propertyAreaValue');
    if (!value) return;
    value.textContent = area ? `${hectares(area)} ha` : '—';
    document.getElementById('propertySquareMeters').textContent = area ? `${new Intl.NumberFormat('pt-BR', {maximumFractionDigits: 0}).format(area)} m²` : 'Desenhe um perímetro para calcular';
    const confirm = document.getElementById('propertyConfirm');
    if (confirm) confirm.disabled = !area;
  }

  function attachPolygon(layer) {
    if (polygon && polygon !== layer) { polygon.pm.disable(); map.removeLayer(polygon); }
    polygon = layer;
    polygon.setStyle({ color: '#D8E889', weight: 4, fillColor: '#385C39', fillOpacity: .35 });
    polygon.on('pm:edit pm:vertexdragend pm:vertexadded pm:vertexremoved', updateArea);
    updateArea();
  }

  function showMapMessage(text) {
    const node = document.getElementById('propertyMapMessage');
    if (node) { node.textContent = text; node.hidden = !text; }
  }

  async function mountMap() {
    const token = ++generation;
    if (!key) return;
    try {
      await loadMapLibraries();
      if (generation !== token || !document.getElementById('propertyMap')) return;
      if (!window.L?.PM || !window.maptilerGeocoder?.GeocodingControl) throw new Error('Os controles de mapa não foram carregados.');
      map = L.map('propertyMap', { zoomControl: false, worldCopyJump: true }).setView([-14.2, -51.9], 4);
      L.control.zoom({ position: 'bottomleft' }).addTo(map);
      let loadedTile = false;
      L.tileLayer(`https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key=${encodeURIComponent(key)}`, {
        maxZoom: 20, minZoom: 2, attribution: '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener">© MapTiler</a> <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a>'
      }).on('tileload', () => { loadedTile = true; showMapMessage(''); }).on('tileerror', () => { if (!loadedTile) showMapMessage('Não foi possível carregar a imagem de satélite. Verifique a conexão e a chave MapTiler.'); }).addTo(map);
      const geocoder = new maptilerGeocoder.GeocodingControl({ apiKey: key, country: 'br', language: 'pt', placeholder: 'Buscar endereço, cidade ou CEP', errorMessage: 'Não foi possível buscar endereços.', debounceSearch: 350, minLength: 3, position: 'topleft' });
      map.addControl(geocoder);
      geocoder.on('select', event => {
        const feature = event.feature || event.detail?.feature;
        if (feature?.place_name) locationLabel = feature.place_name;
        else if (feature?.text) locationLabel = feature.text;
        const label = document.getElementById('propertyLocationLabel');
        if (label && locationLabel) label.textContent = ` · ${locationLabel}`;
      });
      map.on('pm:create', event => { if (event.shape === 'Polygon') attachPolygon(event.layer); });
      if (saved?.geometry) {
        const layer = L.geoJSON(saved.geometry, { style: { color: '#D8E889', weight: 4, fillColor: '#385C39', fillOpacity: .35 } }).getLayers()[0];
        if (layer) { layer.addTo(map); attachPolygon(layer); map.fitBounds(layer.getBounds(), { padding: [35, 35], maxZoom: 18 }); }
      }
      setTimeout(() => map?.invalidateSize(), 100);
    } catch (error) {
      showMapMessage(error.message || 'Não foi possível carregar o mapa.');
    }
  }

  function afterRender() {
    if (view === 'identify') {
      document.getElementById('propertyIdentityForm')?.addEventListener('submit', event => {
        event.preventDefault();
        const personName = document.getElementById('propertyPersonName').value.trim();
        const propertyName = document.getElementById('propertyNameInput').value.trim();
        const error = document.getElementById('propertyFormError');
        if (!personName) { error.textContent = 'Informe seu nome para continuar.'; error.hidden = false; document.getElementById('propertyPersonName').focus(); return; }
        try { saved = store.save({ ...saved, personName, propertyName }); setView('map'); }
        catch (problem) { error.textContent = problem.message; error.hidden = false; }
      });
    } else if (view === 'map' || view === 'saved') mountMap();
  }

  function action(type) {
    switch (type) {
      case 'propertyEnter': setView(saved?.geometry ? 'saved' : 'identify'); break;
      case 'propertyBack': setView('welcome'); break;
      case 'propertyGPS':
        if (!map || !navigator.geolocation) { notify('Não conseguimos acessar sua localização. Você pode encontrar sua propriedade pela busca.'); return; }
        navigator.geolocation.getCurrentPosition(position => map?.setView([position.coords.latitude, position.coords.longitude], 17),
          () => notify('Não conseguimos acessar sua localização. Você pode encontrar sua propriedade pela busca.'),
          { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 });
        break;
      case 'propertyDraw':
        if (!map) return;
        if (polygon) { polygon.pm.disable(); map.removeLayer(polygon); polygon = null; updateArea(); }
        map.pm.enableDraw('Polygon', { allowSelfIntersection: false, pathOptions: { color: '#D8E889', weight: 4, fillColor: '#385C39', fillOpacity: .35 }, markerStyle: { draggable: true } });
        notify('Toque nos vértices do terreno e feche o desenho no primeiro ponto.');
        break;
      case 'propertyEditVertices':
        if (!polygon) { notify('Desenhe o terreno antes de editar.'); return; }
        map.pm.disableDraw(); polygon.pm.enable({ allowSelfIntersection: false, hideMiddleMarkers: false });
        notify('Arraste os pontos para ajustar o contorno.');
        break;
      case 'propertyUndo':
        if (map?.pm.Draw.Polygon?.enabled() && typeof map.pm.Draw.Polygon._removeLastVertex === 'function') map.pm.Draw.Polygon._removeLastVertex();
        else notify('Desenhe um terreno para desfazer o último ponto.');
        break;
      case 'propertyClear':
        if (!map) return;
        map.pm.disableDraw(); if (polygon) { polygon.pm.disable(); map.removeLayer(polygon); polygon = null; }
        updateArea(); break;
      case 'propertyConfirm':
        if (!polygon) return;
        try {
          saved = store.save({ ...saved, locationLabel, geometry: polygon.toGeoJSON().geometry, registeredAt: saved?.registeredAt || new Date().toISOString() });
          setView('saved');
          if(editingFromHome){editingFromHome=false;window.AgrionDiscovery?.showHome();}
          else window.AgrionDiscovery?.invite();
        } catch (problem) { notify(problem.message); }
        break;
      case 'propertyEdit': setView('map'); break;
      case 'propertyNext': window.AgrionDiscovery?.open(); break;
      case 'propertyReturnHome': editingFromHome=false;tearDownMap();view='saved';window.AgrionDiscovery?.showHome();break;
    }
  }

  function editFromHome(){saved=store.read();locationLabel=saved?.locationLabel||'';editingFromHome=true;setView('map');}
  window.AgrionProperty = { view: () => view, markup, afterRender, action, editFromHome };
})();
