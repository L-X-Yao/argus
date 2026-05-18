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
  let prevLat = 0;
  let prevLon = 0;
  let wpMarkers: any[] = [];
  let wpLine: any = null;
  let geoCircle: any = null;
  let satLayer: any = null;
  let vecLayer: any = null;

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
    setTimeout(() => map.invalidateSize(), 100);
  });

  function onMapClick(e: any) {
    const ll = e.latlng;
    const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
    addWaypoint({ lat: wlat, lon: wlon, alt: app.defaultAlt, drop: false, delay: 0 });
  }

  function toWgsFromGcj(glat: number, glon: number): [number, number] {
    const g = toGcj(glat, glon);
    return [glat * 2 - g[0], glon * 2 - g[1]];
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
</script>

<div class="map-container">
  <div bind:this={mapEl} class="map"></div>
  <button class="map-btn" style="top:10px;left:10px" onclick={toggleMapType}>{isSat ? '卫星' : '地图'}</button>
  <button class="map-btn" style="top:10px;right:10px" class:active={follow} onclick={() => follow = !follow}>{follow ? '跟随' : '自由'}</button>
  <button class="map-btn" style="top:10px;right:70px" onclick={toggleExpand}>{app.mapExpanded ? '收起' : '展开'}</button>
  <button class="map-btn" style="top:10px;right:130px" onclick={centerHome}>起飞点</button>
  <button class="map-btn" style="top:10px;right:200px" onclick={fitRoute}>全览</button>
</div>

<style>
  .map-container { position:relative; flex:1; min-width:0; }
  .map { height:100%; border-radius:6px; border:1px solid var(--border); }
  .map-btn { position:absolute; z-index:1000; padding:4px 10px; background:rgba(30,30,30,0.9); border:1px solid #555; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold; color:#aaa; }
  .map-btn:hover { color:#4fc3f7; border-color:#4fc3f7; }
  .map-btn.active { color:#4fc3f7; border-color:#4fc3f7; }
</style>
