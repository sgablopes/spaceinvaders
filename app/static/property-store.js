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

  function read() {
    try {
      const value = JSON.parse(localStorage.getItem(KEY));
      if (value?.version !== VERSION || typeof value.personName !== 'string') return null;
      if (value.geometry && !areaSquareMeters(value.geometry)) return null;
      if (!value.propertyId) {
        value.propertyId = crypto.randomUUID();
        localStorage.setItem(KEY, JSON.stringify(value));
      }
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
      geometry, areaSquareMeters: area, areaHectares: area / 10000,
      locationLabel: value.locationLabel || '',
      registeredAt: geometry ? (value.registeredAt || new Date().toISOString()) : null
    };
    localStorage.setItem(KEY, JSON.stringify(record));
    return record;
  }

  window.AgrionPropertyStore = { read, save, areaSquareMeters };
})();
