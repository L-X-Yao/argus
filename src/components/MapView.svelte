<script lang="ts">
  import { onMount } from 'svelte';
  import { app, addWaypoint, addToast, saveWaypoints, showConfirm } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import { toGcj } from '../lib/gcj02';
  import { API_BASE } from '../lib/backend';
  import MapControls from './MapControls.svelte';
  import HudOverlay from './HudOverlay.svelte';
  import { Layers, Ruler, Navigation, Grid3x3, ShieldAlert, Download, Crosshair, Home, Maximize2 } from '@lucide/svelte';

  declare const L: any;

  let { showHud = true }: { showHud?: boolean } = $props();

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
  let velocityLine: any = null;
  let measurePts: any[] = [];
  let measureLine: any = null;
  let measureLabel: any = null;
  let wpPopup: any = null;
  let replayMarker: any = null;
  let replayTrail: [number, number][] = [];
  let replayTrailLine: any = null;
  let surveyPolyLayer: any = null;
  let surveyVertMarkers: any[] = [];
  let fencePolyLayer: any = null;
  let fenceVertMarkers: any[] = [];
  let rangeRing: any = null;

  const SAT_URL = `${API_BASE}/api/tile/6/{z}/{x}/{y}`;
  const LABEL_URL = `${API_BASE}/api/tile/8/{z}/{x}/{y}`;
  const VEC_URL = `${API_BASE}/api/tile/7/{z}/{x}/{y}`;
  let labelLayer: any = null;

  onMount(() => {
    map = L.map(mapEl, { zoomControl: true, attributionControl: false }).setView([34.258, 108.942], 15);
    satLayer = L.tileLayer(SAT_URL, { maxZoom: 18 }).addTo(map);
    labelLayer = L.tileLayer(LABEL_URL, { maxZoom: 18 }).addTo(map);
    vecLayer = L.tileLayer(VEC_URL, { maxZoom: 18 });
    map.on('click', onMapClick);
    map.on('contextmenu', onRightClick);
    map.on('mousemove', onMouseMove);
    window.addEventListener('keydown', onKeyDown);
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
    if (app.drawingPolygon) {
      const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
      app.surveyPolygon = [...app.surveyPolygon, { lat: wlat, lon: wlon }];
      return;
    }
    if (app.drawingFence) {
      const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
      app.fencePolygon = [...app.fencePolygon, { lat: wlat, lon: wlon }];
      return;
    }
    if (app.guidedMode && app.drone.connected && app.drone.armed) {
      const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
      sendCommand('guided_goto', undefined, { lat: wlat, lon: wlon, alt: app.defaultAlt });
      addToast(`引导飞往 ${wlat.toFixed(5)}, ${wlon.toFixed(5)}`, 'info');
      return;
    }
    const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
    addWaypoint({ lat: wlat, lon: wlon, alt: app.defaultAlt, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 });
  }

  function onRightClick(e: any) {
    e.originalEvent.preventDefault();
    if (!app.drone.connected || !app.drone.armed) return;
    const ll = e.latlng;
    const [wlat, wlon] = toWgsFromGcj(ll.lat, ll.lng);
    showConfirm(`引导飞往此点？\n${wlat.toFixed(5)}, ${wlon.toFixed(5)}\n高度: ${app.defaultAlt}m`).then(ok => {
      if (ok) {
        sendCommand('guided_goto', undefined, { lat: wlat, lon: wlon, alt: app.defaultAlt });
        addToast(`引导飞往 ${wlat.toFixed(5)}, ${wlon.toFixed(5)}`, 'info');
      }
    });
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

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      if (measuring) clearMeasure();
      if (app.guidedMode) app.guidedMode = false;
      if (app.drawingPolygon) { app.drawingPolygon = false; app.surveyPolygon = []; }
      if (app.drawingFence) { app.drawingFence = false; app.fencePolygon = []; }
      if (wpPopup) { map.closePopup(wpPopup); wpPopup = null; }
    }
    if (e.key === 'g' && (e.target as HTMLElement).tagName !== 'INPUT') {
      if (app.drone.connected && app.drone.armed) app.guidedMode = !app.guidedMode;
    }
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

    if (velocityLine) { map.removeLayer(velocityLine); velocityLine = null; }
    if (app.drone.gs > 0.5) {
      const hdgRad = app.drone.hdg * Math.PI / 180;
      const scale = Math.min(app.drone.gs * 8, 200);
      const endLat = glat + Math.cos(hdgRad) * scale / 111320;
      const endLon = glon + Math.sin(hdgRad) * scale / (111320 * Math.cos(glat * Math.PI / 180));
      velocityLine = L.polyline([[glat, glon], [endLat, endLon]], {
        color: '#69f0ae', weight: 2, opacity: 0.6, dashArray: '4,6',
      }).addTo(map);
    }

    if (app.drone.home_lat !== 0 && !homeMarker) {
      const [hlat, hlon] = toGcj(app.drone.home_lat, app.drone.home_lon);
      const homeIcon = L.divIcon({
        className: '',
        html: '<div style="width:26px;height:26px;border-radius:50%;background:#4caf50;color:white;text-align:center;line-height:26px;font-size:14px;font-weight:bold;border:2px solid white;box-shadow:0 0 6px rgba(0,0,0,0.5)">H</div>',
        iconSize: [26, 26], iconAnchor: [13, 13],
      });
      homeMarker = L.marker([hlat, hlon], { icon: homeIcon, zIndexOffset: 500 }).addTo(map);
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
        saveWaypoints();
      });
      m.on('click', (e: any) => {
        e.originalEvent?.stopPropagation();
        const content = `<div style="font-size:12px;min-width:140px">
          <b>航点 ${i + 1}</b> ${wp.drop ? '<span style="color:#e65100">投放</span>' : ''}<br>
          <span style="color:#888">${wp.lat.toFixed(6)}, ${wp.lon.toFixed(6)}</span><br>
          高度: <b>${wp.alt}m</b>
          ${wp.delay ? '<br>延迟: ' + wp.delay + 's' : ''}
        </div>`;
        if (wpPopup) map.closePopup(wpPopup);
        wpPopup = L.popup({ closeButton: true, className: 'wp-popup' })
          .setLatLng([glat, glon])
          .setContent(content)
          .openOn(map);
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

  // RTL range ring — shows safe operating radius based on remaining battery
  $effect(() => {
    if (!map) return;
    if (rangeRing) { map.removeLayer(rangeRing); rangeRing = null; }
    const d = app.drone;
    if (!d.connected || !d.armed || d.home_lat === 0 || d.bat_time <= 0) return;
    const speed = Math.max(d.gs, 3);
    const safeSeconds = Math.max(0, d.bat_time - 60);
    const radius = safeSeconds * speed * 0.5;
    if (radius < 10) return;
    const [hlat, hlon] = toGcj(d.home_lat, d.home_lon);
    const ratio = d.dist_home / Math.max(radius, 1);
    const color = ratio > 0.9 ? '#ef4444' : ratio > 0.7 ? '#eab308' : '#22c55e';
    rangeRing = L.circle([hlat, hlon], {
      radius, color, fill: true, fillColor: color, fillOpacity: 0.06,
      dashArray: '8,6', weight: 1.5,
    }).addTo(map);
  });

  // Replay position rendering
  $effect(() => {
    if (!map) return;
    const rp = app.replayPos;
    if (!rp) {
      if (replayMarker) { map.removeLayer(replayMarker); replayMarker = null; }
      if (replayTrailLine) { map.removeLayer(replayTrailLine); replayTrailLine = null; }
      replayTrail = [];
      return;
    }
    const [glat, glon] = toGcj(rp.lat, rp.lon);
    if (!replayMarker) {
      const icon = L.divIcon({
        className: '',
        html: `<div class="drone-arrow" style="transform:rotate(${rp.yaw}deg)"><svg viewBox="-12 -12 24 24" width="28" height="28"><polygon points="0,-10 -7,8 0,4 7,8" fill="#ffa726" stroke="white" stroke-width="1"/></svg></div>`,
        iconSize: [28, 28], iconAnchor: [14, 14],
      });
      replayMarker = L.marker([glat, glon], { icon, zIndexOffset: 900 }).addTo(map);
    } else {
      replayMarker.setLatLng([glat, glon]);
      const el = replayMarker.getElement();
      if (el) { const a = el.querySelector('.drone-arrow'); if (a) a.style.transform = `rotate(${rp.yaw}deg)`; }
    }
    replayTrail.push([glat, glon]);
    if (replayTrail.length > 3000) replayTrail.splice(0, replayTrail.length - 2000);
    if (replayTrailLine) map.removeLayer(replayTrailLine);
    replayTrailLine = L.polyline(replayTrail, { color: '#ffa726', weight: 2, opacity: 0.6 }).addTo(map);
    if (follow) map.setView([glat, glon], map.getZoom());
  });

  // Survey polygon rendering
  $effect(() => {
    if (!map) return;
    surveyVertMarkers.forEach(m => map.removeLayer(m));
    surveyVertMarkers = [];
    if (surveyPolyLayer) { map.removeLayer(surveyPolyLayer); surveyPolyLayer = null; }
    if (app.surveyPolygon.length === 0) return;
    const gcjPts = app.surveyPolygon.map(p => toGcj(p.lat, p.lon));
    if (gcjPts.length >= 3) {
      surveyPolyLayer = L.polygon(gcjPts, {
        color: '#ab47bc', fillColor: '#ab47bc', fillOpacity: 0.12, weight: 2, dashArray: '6,4',
      }).addTo(map);
    } else if (gcjPts.length >= 2) {
      surveyPolyLayer = L.polyline(gcjPts, { color: '#ab47bc', weight: 2, dashArray: '6,4' }).addTo(map);
    }
    gcjPts.forEach((pt, i) => {
      const cm = L.circleMarker(pt, {
        radius: 5, color: '#ab47bc', fillColor: i === 0 ? '#fff' : '#ab47bc', fillOpacity: 1, weight: 2,
      }).addTo(map);
      surveyVertMarkers.push(cm);
    });
  });

  // Fence polygon rendering
  $effect(() => {
    if (!map) return;
    fenceVertMarkers.forEach(m => map.removeLayer(m));
    fenceVertMarkers = [];
    if (fencePolyLayer) { map.removeLayer(fencePolyLayer); fencePolyLayer = null; }
    if (app.fencePolygon.length === 0) return;
    const uploaded = app.fenceUploaded;
    const gcjPts = app.fencePolygon.map(p => toGcj(p.lat, p.lon));
    if (gcjPts.length >= 3) {
      fencePolyLayer = L.polygon(gcjPts, {
        color: '#f44336', fillColor: '#f44336',
        fillOpacity: uploaded ? 0.15 : 0.06,
        weight: uploaded ? 2.5 : 2,
        dashArray: uploaded ? undefined : '6,4',
      }).addTo(map);
    } else if (gcjPts.length >= 2) {
      fencePolyLayer = L.polyline(gcjPts, {
        color: '#f44336', weight: 2,
        dashArray: uploaded ? undefined : '6,4',
      }).addTo(map);
    }
    gcjPts.forEach((pt, i) => {
      const cm = L.circleMarker(pt, {
        radius: 5, color: '#f44336', fillColor: i === 0 ? '#fff' : '#f44336', fillOpacity: 1, weight: 2,
      }).addTo(map);
      fenceVertMarkers.push(cm);
    });
  });

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
</script>

<div class="relative flex-1 min-w-0">
  <div bind:this={mapEl} class="h-full rounded-lg border border-border"></div>
  <div class="absolute top-2.5 left-2.5 z-[1000] flex gap-1">
    <button class="map-btn" onclick={toggleMapType} title={isSat ? '切换到街道地图' : '切换到卫星地图'}>
      <Layers size={13} />{isSat ? '卫星' : '地图'}
    </button>
    <button class="map-btn {measuring ? '!text-destructive !border-destructive' : ''}" onclick={toggleMeasure} title="测量距离">
      <Ruler size={13} />{measuring ? '取消' : '测距'}
    </button>
    {#if app.drone.connected && app.drone.armed}
      <button class="map-btn {app.guidedMode ? '!text-warning !border-warning' : ''}" onclick={() => app.guidedMode = !app.guidedMode} title="点击地图飞往指定位置">
        <Navigation size={13} />{app.guidedMode ? '引导中' : '引导'}
      </button>
    {/if}
    <button class="map-btn {app.showSurvey || app.drawingPolygon ? '!text-purple-400 !border-purple-400' : ''}"
            onclick={() => app.showSurvey = !app.showSurvey} title="测绘航线规划">
      <Grid3x3 size={13} />测绘
    </button>
    <button class="map-btn {app.showFence || app.drawingFence ? '!text-destructive !border-destructive' : ''}"
            onclick={() => app.showFence = !app.showFence} title="电子围栏">
      <ShieldAlert size={13} />围栏
    </button>
    {#if trail.length > 10}
      <button class="map-btn" onclick={exportTrack} title="导出飞行轨迹KML">
        <Download size={13} />轨迹
      </button>
    {/if}
  </div>
  <div class="absolute top-2.5 right-2.5 z-[1000] flex gap-1">
    <button class="map-btn {follow ? '!text-destructive !border-destructive' : ''}" onclick={() => follow = !follow} title={follow ? '停止跟随' : '跟随飞机'}>
      <Crosshair size={13} />{follow ? '跟随' : '自由'}
    </button>
    <button class="map-btn" onclick={centerHome} title="定位到起飞点">
      <Home size={13} />起飞点
    </button>
    <button class="map-btn" onclick={fitRoute} title="全览航线">
      <Maximize2 size={13} />全览
    </button>
  </div>
  <div class="absolute bottom-1.5 left-2.5 z-[1000] bg-card/85 backdrop-blur text-muted-foreground px-2 py-0.5 rounded text-[11px] font-mono">{mouseCoord || '---'}</div>
  <MapControls />

  {#if showHud && app.drone.connected}
    <HudOverlay />
  {/if}
</div>

<style>
  .map-btn { display:inline-flex; align-items:center; gap:3px; padding:4px 10px; background:hsl(var(--card) / 0.92); border:1px solid hsl(var(--border)); border-radius:6px; cursor:pointer; font-size:12px; font-weight:600; color:hsl(var(--muted-foreground)); backdrop-filter:blur(4px); transition:all 0.15s; }
  .map-btn:hover { color:hsl(var(--primary)); border-color:hsl(var(--primary)); }
</style>
