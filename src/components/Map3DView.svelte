<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { app } from '../lib/stores.svelte';
  import { toGcj } from '../lib/gcj02';
  import { t } from '../lib/i18n.svelte';
  import { API_BASE } from '../lib/backend';
  import maplibregl from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';

  let mapEl: HTMLDivElement;
  let map: maplibregl.Map | null = $state(null);
  let droneMarker: maplibregl.Marker | null = null;
  let homeMarker: maplibregl.Marker | null = null;
  let trailCoords: [number, number][] = [];
  let prevLat = 0;
  let prevLon = 0;

  interface TileSourceDef {
    name: string; sat: string; vec: string; label: string | null;
    gcj02: boolean; region: string;
  }
  const SOURCES: Record<string, TileSourceDef> = {
    amap:          { name: 'Amap',             sat: '6',            vec: '7',             label: '8',         gcj02: true,  region: 'china' },
    google_sat:    { name: 'Google Satellite',  sat: 'google_sat',   vec: 'google_street', label: null,        gcj02: false, region: 'global' },
    google_hybrid: { name: 'Google Hybrid',     sat: 'google_hybrid',vec: 'google_street', label: null,        gcj02: false, region: 'global' },
    osm:           { name: 'OpenStreetMap',     sat: 'osm_sat',      vec: 'osm',           label: null,        gcj02: false, region: 'global' },
    esri:          { name: 'Esri Topo',         sat: 'osm_sat',      vec: 'esri_topo',     label: null,        gcj02: false, region: 'global' },
  };

  function curSource(): TileSourceDef { return SOURCES[app.tileSource] || SOURCES['osm']; }
  let useGcj = $derived(curSource().gcj02);
  function toMap(lat: number, lon: number): [number, number] {
    return useGcj ? toGcj(lat, lon) : [lat, lon];
  }

  function createSvgElement(svgMarkup: string): SVGSVGElement {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgMarkup, 'image/svg+xml');
    return doc.documentElement as unknown as SVGSVGElement;
  }

  onMount(() => {
    const src = curSource();
    const tileUrl = `${API_BASE}/api/tile/${src.sat}/{z}/{x}/{y}`;

    map = new maplibregl.Map({
      container: mapEl,
      style: {
        version: 8,
        sources: {
          'raster-tiles': {
            type: 'raster',
            tiles: [tileUrl],
            tileSize: 256,
            maxzoom: 18,
          },
          'terrain-dem': {
            type: 'raster-dem',
            tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            tileSize: 256,
            maxzoom: 15,
            encoding: 'terrarium',
          },
        },
        layers: [
          { id: 'raster', type: 'raster', source: 'raster-tiles' },
        ],
        terrain: { source: 'terrain-dem', exaggeration: 1.3 },
        sky: {
          'sky-color': '#199EF3',
          'sky-horizon-blend': 0.5,
          'horizon-color': '#ffffff',
          'horizon-fog-blend': 0.5,
          'fog-color': '#0000ff',
          'fog-ground-blend': 0.5,
        },
      },
      center: [108.942, 34.258],
      zoom: 14,
      pitch: 50,
      bearing: 0,
      maxPitch: 85,
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 150 }), 'bottom-right');

    map.on('load', () => {
      map!.addSource('waypoints', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      map!.addLayer({
        id: 'waypoint-line',
        type: 'line',
        source: 'waypoints',
        paint: { 'line-color': '#1565c0', 'line-width': 3, 'line-dasharray': [2, 1] },
      });
      map!.addLayer({
        id: 'waypoint-points',
        type: 'circle',
        source: 'waypoints',
        filter: ['==', '$type', 'Point'],
        paint: { 'circle-radius': 5, 'circle-color': '#1565c0', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' },
      });

      map!.addSource('trail', {
        type: 'geojson',
        data: { type: 'Feature', geometry: { type: 'LineString', coordinates: [] }, properties: {} },
      });
      map!.addLayer({
        id: 'trail-line',
        type: 'line',
        source: 'trail',
        paint: { 'line-color': '#4fc3f7', 'line-width': 2, 'line-opacity': 0.7 },
      });
    });
  });

  onDestroy(() => {
    if (droneMarker) droneMarker.remove();
    if (homeMarker) homeMarker.remove();
    if (map) map.remove();
  });

  $effect(() => {
    if (!map) return;
    const d = app.drone;
    if (!d.connected || d.lat === 0) return;

    const [mlat, mlon] = toMap(d.lat, d.lon);

    if (!droneMarker) {
      const el = document.createElement('div');
      const svg = createSvgElement('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><polygon points="16,4 8,28 16,22 24,28" fill="#4fc3f7" stroke="#fff" stroke-width="1.5"/></svg>');
      el.appendChild(svg);
      el.style.transform = `rotate(${d.hdg}deg)`;
      droneMarker = new maplibregl.Marker({ element: el, rotationAlignment: 'map' })
        .setLngLat([mlon, mlat])
        .addTo(map!);
    } else {
      droneMarker.setLngLat([mlon, mlat]);
      (droneMarker.getElement() as HTMLElement).style.transform = `rotate(${d.hdg}deg)`;
    }

    if (Math.abs(mlat - prevLat) > 0.00001 || Math.abs(mlon - prevLon) > 0.00001) {
      trailCoords.push([mlon, mlat]);
      if (trailCoords.length > 2000) trailCoords = trailCoords.slice(-1500);
      prevLat = mlat;
      prevLon = mlon;
      const trailSrc = map!.getSource('trail') as maplibregl.GeoJSONSource;
      if (trailSrc) {
        trailSrc.setData({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: trailCoords },
          properties: {},
        });
      }
    }

    if (d.home_lat !== 0 && !homeMarker) {
      const [hlat, hlon] = toMap(d.home_lat, d.home_lon);
      const hel = document.createElement('div');
      const hsvg = createSvgElement('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><circle cx="10" cy="10" r="8" fill="#4caf50" stroke="#fff" stroke-width="2"/><text x="10" y="14" text-anchor="middle" fill="white" font-size="10" font-weight="bold">H</text></svg>');
      hel.appendChild(hsvg);
      homeMarker = new maplibregl.Marker({ element: hel })
        .setLngLat([hlon, hlat])
        .addTo(map!);
    }
  });

  $effect(() => {
    if (!map || !map.isStyleLoaded()) return;
    const wps = app.waypoints;
    const src = map.getSource('waypoints') as maplibregl.GeoJSONSource;
    if (!src) return;

    const features: GeoJSON.Feature[] = [];

    if (wps.length >= 2) {
      const coords = wps.map(w => {
        const [lat, lon] = toMap(w.lat, w.lon);
        return [lon, lat] as [number, number];
      });
      features.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: coords },
        properties: {},
      });
    }

    for (let i = 0; i < wps.length; i++) {
      const [lat, lon] = toMap(wps[i].lat, wps[i].lon);
      features.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [lon, lat] },
        properties: { index: i + 1, alt: wps[i].alt },
      });
    }

    src.setData({ type: 'FeatureCollection', features });
  });
</script>

<div class="relative flex-1 min-w-0">
  <div bind:this={mapEl} class="h-full rounded-lg border border-border"></div>

  <div class="absolute top-2.5 left-2.5 z-10 flex gap-1">
    <div class="map-btn">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
      3D {t('map.satellite')}
    </div>
  </div>

  {#if app.drone.connected}
    <div class="absolute bottom-2 left-2.5 z-10 bg-card/85 backdrop-blur text-muted-foreground px-2 py-0.5 rounded text-[11px] font-mono">
      {app.drone.lat.toFixed(6)}, {app.drone.lon.toFixed(6)} | {app.drone.alt_rel.toFixed(1)}m AGL
    </div>
  {/if}
</div>

<style>
  .map-btn { display:inline-flex; align-items:center; gap:3px; padding:4px 10px; background:hsl(var(--card) / 0.92); border:1px solid hsl(var(--border)); border-radius:6px; cursor:pointer; font-size:12px; font-weight:600; color:hsl(var(--muted-foreground)); backdrop-filter:blur(4px); }
</style>
