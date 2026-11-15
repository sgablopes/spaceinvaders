(function () {
  'use strict';

  const KEY = 'agrion-property-v1';
  const VERSION = 1;
  const RADIUS = 6378137;

  function areaSquareMeters(geometry) {
    const ring = geometry?.coordinates?.[0];
    if (geometry?.type !== 'Polygon' || !Array.isArray(ring) || ring.length < 4) return 0;
    const points = ring.slice(0, -1);
    const distinct = new Set(points.map(point => JSON.stringify(point)));
    if (distinct.size < 3 || JSON.stringify(ring[0]) !== JSON.stringify(ring[ring.length - 1])) return 0;
    if (ring.some(point => !Array.isArray(point) || point.length < 2 || !Number.isFinite(point[0]) || !Number.isFinite(point[1]) || Math.abs(point[0]) > 180 || Math.abs(point[1]) > 90)) return 0;
    let sum = 0;
    for (let i = 0; i < ring.length - 1; i++) {
      const [lon1, lat1] = ring[i];
      const [lon2, lat2] = ring[i + 1];
      sum += (lon2 - lon1) * Math.PI / 180 * (2 + Math.sin(lat1 * Math.PI / 180) + Math.sin(lat2 * Math.PI / 180));
    }
    return Math.abs(sum * RADIUS * RADIUS / 2);
  }

  function centerPoint(geometry) {
    if (!areaSquareMeters(geometry)) throw new Error('Polígono inválido.');
    const ring=geometry.coordinates[0], origin=ring[0][0];
    const points=ring.map(([lon,lat])=>{let x=lon-origin;while(x>180)x-=360;while(x< -180)x+=360;return [x,lat];});
    let crossSum=0,xSum=0,ySum=0;
    for(let i=0;i<points.length-1;i++){const [x1,y1]=points[i],[x2,y2]=points[i+1],cross=x1*y2-x2*y1;crossSum+=cross;xSum+=(x1+x2)*cross;ySum+=(y1+y2)*cross;}
    if(Math.abs(crossSum)<1e-12)throw new Error('Não foi possível calcular o centro do terreno.');
    const x=xSum/(3*crossSum),lat=ySum/(3*crossSum);let lon=x+origin;while(lon>180)lon-=360;while(lon< -180)lon+=360;
    let inside=false;
    for(let i=0,j=points.length-2;i<points.length-1;j=i++){const [xi,yi]=points[i],[xj,yj]=points[j];if((yi>lat)!==(yj>lat)&&x<(xj-xi)*(lat-yi)/(yj-yi)+xi)inside=!inside;}
    return {type:'Point',coordinates:[lon,lat],method:'planar_area_centroid_exterior_wgs84',inside_polygon:inside};
  }

  function read() {
    try {
      const value = JSON.parse(localStorage.getItem(KEY));
      if (value?.version !== VERSION || typeof value.personName !== 'string') return null;
      if (value.geometry && !areaSquareMeters(value.geometry)) return null;
      let changed=false;
      if (!value.propertyId) {
        value.propertyId = crypto.randomUUID();
        changed=true;
      }
      if(value.geometry&&!value.centerPoint){value.centerPoint=centerPoint(value.geometry);changed=true;}
      if(changed)localStorage.setItem(KEY, JSON.stringify(value));
      return value;
    } catch (_) { return null; }
  }

  function save(value) {
    const personName = String(value.personName || '').trim();
    if (!personName) throw new Error('Informe seu nome.');
    const propertyName = String(value.propertyName || '').trim() || 'Minha propriedade';
    const geometry = value.geometry || null;
    const area = geometry ? areaSquareMeters(geometry) : 0;
    if (geometry && !area) throw new Error('Desenhe um terreno válido antes de confirmar.');
    const record = {
      version: VERSION, propertyId: value.propertyId || crypto.randomUUID(), personName, propertyName,
      geometry, centerPoint: geometry ? centerPoint(geometry) : null, areaSquareMeters: area, areaHectares: area / 10000,
      locationLabel: value.locationLabel || '',
      registeredAt: geometry ? (value.registeredAt || new Date().toISOString()) : null
    };
    localStorage.setItem(KEY, JSON.stringify(record));
    return record;
  }

  window.AgrionPropertyStore = { read, save, areaSquareMeters, centerPoint };
})();
