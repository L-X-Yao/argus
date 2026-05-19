<script lang="ts">
  import { onMount } from 'svelte';
  import { app, addWaypoint } from '../lib/stores.svelte';
  import { toGcj } from '../lib/gcj02';

  declare const L: any;

  let mapEl: HTMLDivElement;
  let map: any = null;
  let droneMarker: any = null;
  let homeMarker: any = null;
  let trail: [number, number][] = [];
  let trailLine: any = null;
  let follow = $state(true);
  let isSat = $state(true);
  let measuring = $state(false);
  let mouseCoord = $state('');
  let prevLat = 0;
  let prevLon = 0;
  let wpMarkers: any[] = [];
  let wpLine: any = null;
  let geoCircle: any = null;
  let satLayer: any = null;
  let vecLayer: any = null;
  let activeWpMarker: any = null;
  let measurePts: any[] = [];
  let measureLine: any = null;
  let measureLabel: any = null;

  const SAT_URL = '/api/tile/6/{z}/{x}/{y}';
  const LABEL_URL = '/api/tile/8/{z}/{x}/{y}';
  const VEC_URL = '/api/tile/7/{z}/{x}/{y}';
  let labelLayer: any = null;

  onMount(() => {
    map = L.map(mapEl, { zoomControl: true, attributionControl: false }).setView([34.258, 108.942], 15);
    satLayer = L.tileLayer(SAT_URL, { maxZoom: 18 }).addTo(map);
    labelLayer = L.tileLayer(LABEL_URL, { maxZoom: 18 }).addTo(map);
    vecLayer = L.tileLayer(VEC_URL, { maxZoom: 18 });
    map.on('click', onMapClick);
    map.on('mousemove', onMouseMove);
    setTimeout(() => map.invalidateSize(), 100);
  });

  function onMouseMove(e: any) {
    const ll = e.latlng;
    const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
    mouseCoord = `${wlat.toFixed(6)}, ${wlon.toFixed(6)}`;
  }

  function onMapClick(e: any) {
    const ll = e.latlng;
    if (measuring) {
      addMeasurePoint(ll);
      return;
    }
    const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
    addWaypoint({ lat: wlat, lon: wlon, alt: app.defaultAlt, drop: false, delay: 0 });
  }

  function toWgsFromGcj(glat: number, glon: number): [number, number] {
    const g = toGcj(glat, glon);
    return [glat * 2 - g[0], glon * 2 - g[1]];
  }

  function addMeasurePoint(ll: any) {
    const cm = L.circleMarker([ll.lat, ll.lng], { radius: 4, color: '#ff5252', fillColor: '#ff5252', fillOpacity: 1 }).addTo(map);
    measurePts.push({ marker: cm, ll });
    if (measurePts.length >= 2) {
      const a = measurePts[measurePts.length - 2].ll;
      const b = measurePts[measurePts.length - 1].ll;
      const dist = map.distance(a, b);
      let total = 0;
      for (let i = 1; i < measurePts.length; i++) {
        total += map.distance(measurePts[i - 1].ll, measurePts[i].ll);
      }
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

  function toggleMeasure() {
    if (measuring) {
      clearMeasure();
    } else {
      clearMeasure();
      measuring = true;
    }
  }

  function exportTrack() {
    if (!trail.length) return;
    const coords = trail.map(([glat, glon]) => {
      const [wlat, wlon] = toWgsFromGcj(glat, glon);
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
    const pts = app.waypoints.map(w => toGcj(w.lat, w.lon));
    if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding: [40, 40] });
  }
  function centerHome() {
    if (app.drone.home_lat) map.setView(toGcj(app.drone.home_lat, app.drone.home_lon), 16);
  }

  $effect(() => {
    if (!map || !app.drone.connected) return;
    const lat = app.drone.lat, lon = app.drone.lon;
    if (Math.abs(lat) < 0.001) return;
    const [glat, glon] = toGcj(lat, lon);

    if (!droneMarker) {
      const icon = L.divIcon({
        className: '',
        html: `<div class="drone-arrow" style="transform:rotate(${app.drone.yaw}deg)"><svg viewBox="-12 -12 24 24" width="28" height="28"><polygon points="0,-10 -7,8 0,4 7,8" fill="#4fc3f7" stroke="white" stroke-width="1"/></svg></div>`,
        iconSize: [28, 28], iconAnchor: [14, 14],
      });
      droneMarker = L.marker([glat, glon], { icon, zIndexOffset: 1000 }).addTo(map);
    } else {
      droneMarker.setLatLng([glat, glon]);
      const el = droneMarker.getElement();
      if (el) { const a = el.querySelector('.drone-arrow'); if (a) a.style.transform = `rotate(${app.drone.yaw}deg)`; }
    }

    if (app.drone.home_lat !== 0 && !homeMarker) {
      const [hlat, hlon] = toGcj(app.drone.home_lat, app.drone.home_lon);
      homeMarker = L.circleMarker([hlat, hlon], { radius: 8, color: '#ff9800', fillColor: '#ff9800', fillOpacity: 0.5 }).addTo(map);
    }

    if (Math.abs(lat - prevLat) > 0.000001 || Math.abs(lon - prevLon) > 0.000001) {
      trail.push([glat, glon]);
      if (trail.length > 2000) trail.splice(0, trail.length - 1500);
      if (trailLine) map.removeLayer(trailLine);
      trailLine = L.polyline(trail, { color: '#4fc3f7', weight: 2, opacity: 0.7 }).addTo(map);
      prevLat = lat; prevLon = lon;
    }
    if (follow) map.setView([glat, glon], map.getZoom());
  });

  // Active waypoint indicator
  $effect(() => {
    if (!map) return;
    if (activeWpMarker) { map.removeLayer(activeWpMarker); activeWpMarker = null; }
    const seq = app.drone.wp;
    if (seq >= 2 && app.waypoints.length > 0) {
      const wpIdx = seq - 2;
      if (wpIdx >= 0 && wpIdx < app.waypoints.length) {
        const wp = app.waypoints[wpIdx];
        const [glat, glon] = toGcj(wp.lat, wp.lon);
        activeWpMarker = L.circleMarker([glat, glon], {
          radius: 16, color: '#ffa726', fillColor: 'transparent', weight: 3, dashArray: '4,4',
        }).addTo(map);
      }
    }
  });

  $effect(() => {
    if (!map) return;
    wpMarkers.forEach(m => map.removeLayer(m));
    wpMarkers = [];
    if (wpLine) { map.removeLayer(wpLine); wpLine = null; }
    const pts: [number, number][] = [];
    app.waypoints.forEach((wp, i) => {
      const [glat, glon] = toGcj(wp.lat, wp.lon);
      pts.push([glat, glon]);
      const color = wp.drop ? '#e65100' : '#1565c0';
      const icon = L.divIcon({
        className: '',
        html: `<div style="width:22px;height:22px;border-radius:50%;background:${color};color:white;text-align:center;line-height:22px;font-size:11px;font-weight:bold;border:2px solid white;box-shadow:0 0 4px rgba(0,0,0,0.5)">${i + 1}</div>`,
        iconSize: [22, 22], iconAnchor: [11, 11],
      });
      const m = L.marker([glat, glon], { icon, draggable: true }).addTo(map);
      m.on('dragend', () => {
        const ll = m.getLatLng();
        const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
        app.waypoints[i].lat = wlat;
        app.waypoints[i].lon = wlon;
      });
      wpMarkers.push(m);
    });
    if (pts.length > 1) wpLine = L.polyline(pts, { color: '#1565c0', weight: 2, dashArray: '6,4' }).addTo(map);

    if (geoCircle) { map.removeLayer(geoCircle); geoCircle = null; }
    if (app.drone.home_lat !== 0 && app.geoRadius > 0) {
      const [hlat, hlon] = toGcj(app.drone.home_lat, app.drone.home_lon);
      geoCircle = L.circle([hlat, hlon], { radius: app.geoRadius, color: '#f44336', fill: false, dashArray: '8,4', weight: 1 }).addTo(map);
    }
  });

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
</script>

<div class="map-container">
  <div bind:this={mapEl} class="map"></div>
  <div class="map-btns-left">
    <button class="map-btn" onclick={toggleMapType}>{isSat ? '卫星' : '地图'}</button>
    <button class="map-btn" class:active={measuring} onclick={toggleMeasure}>{measuring ? '取消测距' : '测距'}</button>
    {#if trail.length > 10}
      <button class="map-btn" onclick={exportTrack}>导出轨迹</button>
    {/if}
  </div>
  <div class="map-btns-right">
    <button class="map-btn" class:active={follow} onclick={() => follow = !follow}>{follow ? '跟随' : '自由'}</button>
    <button class="map-btn" onclick={toggleExpand}>{app.mapExpanded ? '收起' : '展开'}</button>
    <button class="map-btn" onclick={centerHome}>起飞点</button>
    <button class="map-btn" onclick={fitRoute}>全览</button>
  </div>
  <div class="coord-bar">{mouseCoord || '---'}</div>

  {#if app.mapExpanded && app.drone.connected}
    <div class="hud">
      <div class="hud-item"><span class="hud-label">高度</span><span class="hud-value">{app.drone.alt_rel.toFixed(1)}m</span></div>
      <div class="hud-item"><span class="hud-label">速度</span><span class="hud-value">{app.drone.gs.toFixed(1)}m/s</span></div>
      <div class="hud-item"><span class="hud-label">距离</span><span class="hud-value">{app.drone.dist_home.toFixed(0)}m</span></div>
      <div class="hud-item"><span class="hud-label">电池</span><span class="hud-value">{app.drone.voltage.toFixed(1)}V {app.drone.remaining >= 0 ? app.drone.remaining + '%' : ''}</span></div>
      <div class="hud-item"><span class="hud-label">航向</span><span class="hud-value">{app.drone.hdg.toFixed(0)}&deg;</span></div>
      {#if app.drone.flight_time > 0}
        <div class="hud-item"><span class="hud-label">时间</span><span class="hud-value">{fmtTime(app.drone.flight_time)}</span></div>
      {/if}
      {#if app.drone.wp > 0}
        <div class="hud-item"><span class="hud-label">航点</span><span class="hud-value">#{app.drone.wp}</span></div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .map-container { position:relative; flex:1; min-width:0; }
  .map { height:100%; border-radius:6px; border:1px solid var(--border); }
  .map-btns-left { position:absolute; top:10px; left:10px; z-index:1000; display:flex; gap:4px; }
  .map-btns-right { position:absolute; top:10px; right:10px; z-index:1000; display:flex; gap:4px; }
  .map-btn { padding:4px 10px; background:rgba(30,30,30,0.9); border:1px solid #555; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold; color:#aaa; }
  .map-btn:hover { color:#4fc3f7; border-color:#4fc3f7; }
  .map-btn.active { color:#ff5252; border-color:#ff5252; }
  .coord-bar { position:absolute; bottom:6px; left:10px; z-index:1000; background:rgba(30,30,30,0.85); color:#aaa; padding:2px 8px; border-radius:3px; font-size:11px; font-family:monospace; }
  .hud { position:absolute; bottom:6px; right:10px; z-index:1000; display:flex; gap:8px; }
  .hud-item { background:rgba(10,10,10,0.85); border:1px solid #333; border-radius:4px; padding:4px 8px; text-align:center; }
  .hud-label { display:block; font-size:9px; color:#666; text-transform:uppercase; }
  .hud-value { display:block; font-size:14px; font-weight:bold; color:#4fc3f7; }
</style>
