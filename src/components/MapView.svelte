<script lang="ts">
  import { onMount } from 'svelte';
  import { app, addWaypoint, addToast, showConfirm } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import { toGcj, toWgs } from '../lib/gcj02';
  import { API_BASE } from '../lib/backend';
  import MapControls from './MapControls.svelte';
  import HudOverlay from './HudOverlay.svelte';
  import DroneLayer from './layers/DroneLayer.svelte';
  import WaypointLayer from './layers/WaypointLayer.svelte';
  import GuidedLayer from './layers/GuidedLayer.svelte';
  import FenceLayer from './layers/FenceLayer.svelte';
  import SurveyLayer from './layers/SurveyLayer.svelte';
  import ReplayLayer from './layers/ReplayLayer.svelte';
  import { Layers, Ruler, Navigation, Grid3x3, ShieldAlert, Download, Crosshair, Home, Maximize2 } from '@lucide/svelte';
  import { t } from '../lib/i18n.svelte';

  declare const L: any;

  let { showHud = true }: { showHud?: boolean } = $props();

  let mapEl: HTMLDivElement;
  let map = $state<any>(null);
  let follow = $state(true);
  let isSat = $state(true);
  let measuring = $state(false);
  let mouseCoord = $state('');
  let guidedTarget = $state<{ lat: number; lon: number; alt: number } | null>(null);
  let droneTrail: [number, number][] = $state([]);

  let satLayer: any = null;
  let vecLayer: any = null;
  let labelLayer: any = null;
  let measurePts: any[] = [];
  let measureLine: any = null;
  let measureLabel: any = null;

  const CN_SAT = `${API_BASE}/api/tile/6/{z}/{x}/{y}`;
  const CN_LABEL = `${API_BASE}/api/tile/8/{z}/{x}/{y}`;
  const CN_VEC = `${API_BASE}/api/tile/7/{z}/{x}/{y}`;
  const GL_SAT = `${API_BASE}/api/tile/osm_sat/{z}/{x}/{y}`;
  const GL_VEC = `${API_BASE}/api/tile/osm/{z}/{x}/{y}`;

  function tileUrls() {
    if (app.mapRegion === 'global') return { sat: GL_SAT, vec: GL_VEC, label: null };
    return { sat: CN_SAT, vec: CN_VEC, label: CN_LABEL };
  }
  let useGcj = $derived(app.mapRegion === 'china');

  function toMap(lat: number, lon: number): [number, number] {
    return useGcj ? toGcj(lat, lon) : [lat, lon];
  }
  function fromMap(mlat: number, mlon: number): [number, number] {
    return useGcj ? toWgs(mlat, mlon) : [mlat, mlon];
  }

  onMount(() => {
    const urls = tileUrls();
    map = L.map(mapEl, { zoomControl: true, attributionControl: false }).setView([34.258, 108.942], 15);
    satLayer = L.tileLayer(urls.sat, { maxZoom: 18 }).addTo(map);
    labelLayer = urls.label ? L.tileLayer(urls.label, { maxZoom: 18 }).addTo(map) : null;
    vecLayer = L.tileLayer(urls.vec, { maxZoom: 18 });
    L.control.scale({ metric: true, imperial: false, position: 'bottomright' }).addTo(map);
    map.on('click', onMapClick);
    map.on('contextmenu', onRightClick);
    map.on('mousemove', (e: any) => {
      const [wlat, wlon] = fromMap(e.latlng.lat, e.latlng.lng);
      mouseCoord = `${wlat.toFixed(6)}, ${wlon.toFixed(6)}`;
    });
    window.addEventListener('keydown', onKeyDown);
    setTimeout(() => map.invalidateSize(), 100);
  });

  function onMapClick(e: any) {
    const ll = e.latlng;
    if (measuring) { addMeasurePoint(ll); return; }
    if (app.drawingPolygon) {
      const [wlat, wlon] = fromMap(ll.lat, ll.lng);
      app.surveyPolygon = [...app.surveyPolygon, { lat: wlat, lon: wlon }];
      return;
    }
    if (app.drawingFence) {
      const [wlat, wlon] = fromMap(ll.lat, ll.lng);
      app.fencePolygon = [...app.fencePolygon, { lat: wlat, lon: wlon }];
      return;
    }
    if (app.guidedMode && app.drone.connected && app.drone.armed) {
      const [wlat, wlon] = fromMap(ll.lat, ll.lng);
      sendCommand('guided_goto', undefined, { lat: wlat, lon: wlon, alt: app.defaultAlt });
      guidedTarget = { lat: wlat, lon: wlon, alt: app.defaultAlt };
      addToast(`引导飞往 ${wlat.toFixed(5)}, ${wlon.toFixed(5)}`, 'info');
      return;
    }
    const [wlat, wlon] = fromMap(ll.lat, ll.lng);
    addWaypoint({ lat: wlat, lon: wlon, alt: app.defaultAlt, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 });
  }

  function onRightClick(e: any) {
    e.originalEvent.preventDefault();
    if (!app.drone.connected || !app.drone.armed) return;
    const ll = e.latlng;
    const [wlat, wlon] = fromMap(ll.lat, ll.lng);
    showConfirm(`${t('confirm.guidedGoto')}\n${wlat.toFixed(5)}, ${wlon.toFixed(5)}\n${t('ctrl.altitude')}: ${app.defaultAlt}m`).then(ok => {
      if (ok) {
        sendCommand('guided_goto', undefined, { lat: wlat, lon: wlon, alt: app.defaultAlt });
        guidedTarget = { lat: wlat, lon: wlon, alt: app.defaultAlt };
        addToast(`引导飞往 ${wlat.toFixed(5)}, ${wlon.toFixed(5)}`, 'info');
      }
    });
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      if (measuring) clearMeasure();
      if (app.guidedMode) { app.guidedMode = false; guidedTarget = null; }
      if (app.drawingPolygon) { app.drawingPolygon = false; app.surveyPolygon = []; }
      if (app.drawingFence) { app.drawingFence = false; app.fencePolygon = []; }
      map?.closePopup();
    }
    if (e.key === 'g' && (e.target as HTMLElement).tagName !== 'INPUT') {
      if (app.drone.connected && app.drone.armed) app.guidedMode = !app.guidedMode;
    }
  }

  function addMeasurePoint(ll: any) {
    const cm = L.circleMarker([ll.lat, ll.lng], { radius: 4, color: '#ff5252', fillColor: '#ff5252', fillOpacity: 1 }).addTo(map);
    measurePts.push({ marker: cm, ll });
    if (measurePts.length >= 2) {
      const a = measurePts[measurePts.length - 2].ll;
      const b = measurePts[measurePts.length - 1].ll;
      let total = 0;
      for (let i = 1; i < measurePts.length; i++) total += map.distance(measurePts[i - 1].ll, measurePts[i].ll);
      const pts = measurePts.map((p: any) => [p.ll.lat, p.ll.lng]);
      if (measureLine) map.removeLayer(measureLine);
      measureLine = L.polyline(pts, { color: '#ff5252', weight: 2, dashArray: '4,4' }).addTo(map);
      if (measureLabel) map.removeLayer(measureLabel);
      const mid = L.latLng((a.lat + b.lat) / 2, (a.lng + b.lng) / 2);
      const txt = total < 1000 ? `${total.toFixed(0)}m` : `${(total / 1000).toFixed(2)}km`;
      measureLabel = L.marker(mid, {
        icon: L.divIcon({
          className: '',
          html: `<div style="background:rgba(30,30,30,0.9);color:#ff5252;padding:2px 6px;border-radius:3px;font-size:11px;font-weight:bold;white-space:nowrap">${txt}</div>`,
          iconAnchor: [0, 0],
        }),
      }).addTo(map);
    }
  }

  function clearMeasure() {
    measuring = false;
    measurePts.forEach((p: any) => map.removeLayer(p.marker));
    measurePts = [];
    if (measureLine) { map.removeLayer(measureLine); measureLine = null; }
    if (measureLabel) { map.removeLayer(measureLabel); measureLabel = null; }
  }

  function toggleMeasure() { if (measuring) clearMeasure(); else { clearMeasure(); measuring = true; } }

  function toggleMapType() {
    isSat = !isSat;
    if (isSat) {
      map.removeLayer(vecLayer);
      map.addLayer(satLayer);
      map.addLayer(labelLayer);
    } else {
      map.removeLayer(satLayer);
      map.removeLayer(labelLayer);
      map.addLayer(vecLayer);
    }
  }

  function toggleExpand() { app.mapExpanded = !app.mapExpanded; setTimeout(() => map?.invalidateSize(), 100); }

  function fitRoute() {
    const pts = app.waypoints.map(w => toMap(w.lat, w.lon));
    if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding: [40, 40] });
  }

  function centerHome() {
    if (app.drone.home_lat) map.setView(toMap(app.drone.home_lat, app.drone.home_lon), 16);
  }

  function exportTrack() {
    if (!droneTrail.length) return;
    const coords = droneTrail.map(([glat, glon]) => {
      const [wlat, wlon] = fromMap(glat, glon);
      return `${wlon},${wlat},0`;
    }).join('\n');
    const kml = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>飞行轨迹</name>
<Style id="track"><LineStyle><color>ff4fc3f7</color><width>2</width></LineStyle></Style>
<Placemark><name>轨迹</name><styleUrl>#track</styleUrl>
<LineString><coordinates>${coords}</coordinates></LineString>
</Placemark></Document></kml>`;
    const blob = new Blob([kml], { type: 'application/vnd.google-earth.kml+xml' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '轨迹_' + new Date().toISOString().slice(0, 10) + '.kml';
    a.click();
    URL.revokeObjectURL(a.href);
  }
</script>

<div class="relative flex-1 min-w-0">
  <div bind:this={mapEl} class="h-full rounded-lg border border-border"></div>

  {#if map}
    <DroneLayer {map} {follow} trail={droneTrail} coord={toMap} />
    <WaypointLayer {map} coord={toMap} coordInv={fromMap} />
    <GuidedLayer {map} bind:target={guidedTarget} coord={toMap} />
    <FenceLayer {map} coord={toMap} />
    <SurveyLayer {map} coord={toMap} />
    <ReplayLayer {map} {follow} coord={toMap} />
  {/if}

  <div class="absolute top-2.5 left-2.5 z-[1000] flex gap-1">
    <button class="map-btn" onclick={toggleMapType} title={isSat ? t('map.street') : t('map.satellite')}>
      <Layers size={13} />{isSat ? t('map.satellite') : t('map.street')}
    </button>
    <button class="map-btn {measuring ? '!text-destructive !border-destructive' : ''}" onclick={toggleMeasure} title={t('map.measure')}>
      <Ruler size={13} />{measuring ? t('map.cancel') : t('map.measure')}
    </button>
    {#if app.drone.connected && app.drone.armed}
      <button class="map-btn {app.guidedMode ? '!text-warning !border-warning' : ''}" onclick={() => app.guidedMode = !app.guidedMode} title={t('map.guided')}>
        <Navigation size={13} />{app.guidedMode ? t('map.guidedActive') : t('map.guided')}
      </button>
    {/if}
    <button class="map-btn {app.showSurvey || app.drawingPolygon ? '!text-purple-400 !border-purple-400' : ''}"
            onclick={() => app.showSurvey = !app.showSurvey} title={t('map.survey')}>
      <Grid3x3 size={13} />{t('map.survey')}
    </button>
    <button class="map-btn {app.showFence || app.drawingFence ? '!text-destructive !border-destructive' : ''}"
            onclick={() => app.showFence = !app.showFence} title={t('map.fence')}>
      <ShieldAlert size={13} />{t('map.fence')}
    </button>
    {#if droneTrail.length > 10}
      <button class="map-btn" onclick={exportTrack} title={t('map.track')}>
        <Download size={13} />{t('map.track')}
      </button>
    {/if}
  </div>
  <div class="absolute top-2.5 right-2.5 z-[1000] flex gap-1">
    <button class="map-btn {follow ? '!text-destructive !border-destructive' : ''}" onclick={() => follow = !follow} title={follow ? t('map.free') : t('map.follow')}>
      <Crosshair size={13} />{follow ? t('map.follow') : t('map.free')}
    </button>
    <button class="map-btn" onclick={centerHome} title={t('map.home')}>
      <Home size={13} />{t('map.home')}
    </button>
    <button class="map-btn" onclick={fitRoute} title={t('map.fitAll')}>
      <Maximize2 size={13} />{t('map.fitAll')}
    </button>
  </div>
  {#if app.drone.connected}
    <div class="absolute top-12 right-3 z-[1000]" title="航向 {app.drone.hdg.toFixed(0)}°">
      <svg width="42" height="42" viewBox="0 0 42 42" class="drop-shadow-lg">
        <circle cx="21" cy="21" r="19" fill="rgba(0,0,0,0.65)" stroke="rgba(255,255,255,0.15)" stroke-width="0.5" />
        <text x="21" y="10" text-anchor="middle" fill="#f44336" font-size="9" font-weight="bold" font-family="monospace">N</text>
        <text x="21" y="37" text-anchor="middle" fill="#666" font-size="7" font-family="monospace">S</text>
        <text x="5" y="24" text-anchor="middle" fill="#666" font-size="7" font-family="monospace">W</text>
        <text x="37" y="24" text-anchor="middle" fill="#666" font-size="7" font-family="monospace">E</text>
        <g transform="rotate({app.drone.hdg}, 21, 21)" class="compass-needle">
          <polygon points="21,5 18,17 24,17" fill="#4fc3f7" opacity="0.9" />
          <polygon points="21,37 18,25 24,25" fill="#4fc3f7" opacity="0.25" />
        </g>
      </svg>
    </div>
  {/if}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="absolute bottom-1.5 left-2.5 z-[1000] bg-card/85 backdrop-blur text-muted-foreground px-2 py-0.5 rounded text-[11px] font-mono cursor-pointer hover:text-primary transition-colors"
       onclick={() => { if (mouseCoord) { navigator.clipboard.writeText(mouseCoord); addToast('坐标已复制', 'success', 1500); } }}
       title="点击复制坐标">{mouseCoord || '---'}</div>
  <MapControls />

  {#if showHud && app.drone.connected}
    <HudOverlay />
  {/if}
</div>

<style>
  .map-btn { display:inline-flex; align-items:center; gap:3px; padding:4px 10px; background:hsl(var(--card) / 0.92); border:1px solid hsl(var(--border)); border-radius:6px; cursor:pointer; font-size:12px; font-weight:600; color:hsl(var(--muted-foreground)); backdrop-filter:blur(4px); transition:all 0.15s; }
  .map-btn:hover { color:hsl(var(--primary)); border-color:hsl(var(--primary)); }
  :global(.drone-icon) { transition: transform 200ms linear !important; background: none !important; border: none !important; }
  :global(.drone-arrow) { transition: transform 150ms ease-out; }
  :global(.dark .leaflet-tile-pane) { filter: brightness(0.75) contrast(1.1) saturate(0.85); }
  :global(.dark .leaflet-control-zoom a) { background: hsl(var(--card)); color: hsl(var(--foreground)); border-color: hsl(var(--border)); }
  :global(.guided-pulse) { animation: guidedPulse 1.5s ease-in-out infinite; }
  @keyframes guidedPulse { 0%,100% { opacity: 0.6; } 50% { opacity: 1; } }
  .compass-needle { transition: transform 200ms ease-out; transform-origin: 21px 21px; }
</style>
