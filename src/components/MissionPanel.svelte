<script lang="ts">
  import { app, pushUndo, deleteWaypoint, clearWaypoints, saveSettings } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import { toGcj } from '../lib/gcj02';

  function toggleDrop(i: number) { pushUndo(); app.waypoints[i].drop = !app.waypoints[i].drop; }
  function setAlt(i: number, v: string) { app.waypoints[i].alt = parseFloat(v) || 30; saveSettings(); }
  function applyAltAll() { pushUndo(); app.waypoints.forEach(w => w.alt = app.defaultAlt); }
  function reverseRoute() { if (!app.waypoints.length) return; pushUndo(); app.waypoints.reverse(); }
  function moveWp(i: number, dir: number) {
    const j = i + dir;
    if (j < 0 || j >= app.waypoints.length) return;
    pushUndo();
    [app.waypoints[i], app.waypoints[j]] = [app.waypoints[j], app.waypoints[i]];
  }

  function uploadMission() {
    if (!app.waypoints.length) return;
    sendCommand('mission_upload', undefined, {
      waypoints: app.waypoints,
      takeoff_alt: app.defaultAlt,
    });
  }

  async function armAndFly() {
    if (!app.waypoints.length) return;
    uploadMission();
    await new Promise(r => setTimeout(r, 1000));
    sendCommand('arm');
    await new Promise(r => setTimeout(r, 2000));
    sendCommand('takeoff', undefined, { alt: app.defaultAlt });
    await new Promise(r => setTimeout(r, 3000));
    sendCommand('mission_start');
  }

  function saveMission() {
    const data = JSON.stringify({ waypoints: app.waypoints, alt: app.defaultAlt }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '任务_' + new Date().toISOString().slice(0, 10) + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function loadMission() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.json';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev: any) => {
        try {
          const d = JSON.parse(ev.target.result);
          pushUndo();
          app.waypoints = d.waypoints || [];
          if (d.alt) app.defaultAlt = d.alt;
        } catch (err) { alert('加载失败'); }
      };
      reader.readAsText(file);
    };
    input.click();
  }

  function exportKml() {
    if (!app.waypoints.length) return;
    let coords = app.waypoints.map(w => `${w.lon},${w.lat},${w.alt}`).join('\n');
    const kml = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>PL-Link任务</name>
<Placemark><name>航线</name><LineString><coordinates>${coords}</coordinates></LineString></Placemark>
</Document></kml>`;
    const blob = new Blob([kml], { type: 'application/vnd.google-earth.kml+xml' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '任务_' + new Date().toISOString().slice(0, 10) + '.kml';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function importKml() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.kml';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev: any) => {
        try {
          const doc = new DOMParser().parseFromString(ev.target.result, 'text/xml');
          const coords: any[] = [];
          const els = doc.getElementsByTagName('coordinates');
          for (let i = 0; i < els.length; i++) {
            els[i].textContent!.trim().split(/\s+/).forEach((c: string) => {
              const p = c.split(',');
              if (p.length >= 2) {
                const lon = parseFloat(p[0]), lat = parseFloat(p[1]);
                const alt = parseFloat(p[2]) || app.defaultAlt;
                if (Math.abs(lat) > 0.001 && Math.abs(lon) > 0.001)
                  coords.push({ lat, lon, alt, drop: false, delay: 0 });
              }
            });
          }
          if (coords.length > 1 && Math.abs(coords[0].lat - coords[coords.length - 1].lat) < 0.00001)
            coords.pop();
          if (!coords.length) throw new Error('无坐标');
          pushUndo();
          app.waypoints = coords;
        } catch (err: any) { alert('KML导入失败: ' + err.message); }
      };
      reader.readAsText(file);
    };
    input.click();
  }

  function totalDist(): string {
    let d = 0;
    for (let i = 1; i < app.waypoints.length; i++) {
      const a = app.waypoints[i - 1], b = app.waypoints[i];
      const dlat = (b.lat - a.lat) * 111320;
      const dlon = (b.lon - a.lon) * 111320 * Math.cos(a.lat * Math.PI / 180);
      d += Math.sqrt(dlat * dlat + dlon * dlon);
    }
    return d < 1000 ? d.toFixed(0) + 'm' : (d / 1000).toFixed(1) + 'km';
  }
</script>

<div class="panel wp-panel">
  <h2>航点 <span class="count">({app.waypoints.length})</span></h2>
  <div class="wp-list">
    {#each app.waypoints as wp, i}
      <div class="wp-item">
        <span class="wp-num">{i + 1}</span>
        <button class="wp-type" class:drop={wp.drop} onclick={() => toggleDrop(i)}>
          {wp.drop ? '投放' : '航点'}
        </button>
        <span class="wp-coords">{wp.lat.toFixed(5)}, {wp.lon.toFixed(5)}</span>
        <input type="number" class="wp-alt" value={wp.alt} onchange={(e) => setAlt(i, (e.target as HTMLInputElement).value)} />
        <button class="wp-mv" onclick={() => moveWp(i, -1)}>&uarr;</button>
        <button class="wp-mv" onclick={() => moveWp(i, 1)}>&darr;</button>
        <button class="wp-del" onclick={() => deleteWaypoint(i)}>&times;</button>
      </div>
    {:else}
      <div class="empty">点击地图添加航点</div>
    {/each}
  </div>
  {#if app.waypoints.length > 0}
    <div class="wp-stats">总距离: {totalDist()} | {app.waypoints.filter(w => w.drop).length} 投放</div>
  {/if}
  <div class="toolbar">
    <label for="def-alt">高度:</label>
    <input id="def-alt" type="number" bind:value={app.defaultAlt} min="5" max="200" step="5" onchange={saveSettings} />
    <label>m</label>
    <button class="btn-sm" onclick={applyAltAll}>全部</button>
    <button class="btn-upload" onclick={uploadMission}>上传</button>
    <button class="btn-fly" onclick={armAndFly}>解锁+起飞</button>
  </div>
  <div class="toolbar">
    <button class="btn-sm" onclick={saveMission}>保存</button>
    <button class="btn-sm" onclick={loadMission}>加载</button>
    <button class="btn-sm" onclick={exportKml}>导出</button>
    <button class="btn-sm" onclick={importKml}>导入</button>
    <button class="btn-sm" onclick={reverseRoute}>反转</button>
    <button class="btn-sm warn" onclick={clearWaypoints}>清除</button>
  </div>
</div>

<style>
  .panel { background:var(--bg-panel); border-radius:8px; padding:15px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0 0 8px; text-transform:uppercase; letter-spacing:1px; }
  .count { font-size:12px; color:var(--text-dim); font-weight:normal; }
  .wp-panel { width:280px; flex-shrink:0; overflow:hidden; display:flex; flex-direction:column; }
  .wp-list { flex:1; overflow-y:auto; max-height:300px; }
  .wp-item { display:flex; align-items:center; gap:4px; padding:4px 0; border-bottom:1px solid var(--border); font-size:12px; }
  .wp-num { width:22px; text-align:center; color:var(--text-dim); font-weight:bold; }
  .wp-type { padding:1px 6px; border-radius:3px; cursor:pointer; font-size:10px; font-weight:bold; border:none; color:white; background:#1565c0; }
  .wp-type.drop { background:#e65100; }
  .wp-coords { flex:1; color:var(--text-dim); font-size:10px; overflow:hidden; white-space:nowrap; }
  .wp-alt { width:40px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); padding:2px 3px; border-radius:3px; font-size:11px; text-align:right; }
  .wp-mv { background:none; border:none; color:var(--text-dim); cursor:pointer; font-size:12px; padding:0 1px; }
  .wp-del { background:none; border:none; color:#f44336; cursor:pointer; font-size:16px; padding:0 2px; line-height:1; }
  .empty { color:var(--text-dim); font-size:12px; padding:8px 0; }
  .wp-stats { font-size:12px; color:#ffa726; margin:6px 0; }
  .toolbar { display:flex; gap:4px; margin-top:6px; align-items:center; flex-wrap:wrap; }
  .toolbar label { font-size:11px; color:var(--text-dim); }
  .toolbar input[type=number] { width:50px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); padding:3px 4px; border-radius:3px; font-size:12px; }
  .btn-sm { padding:4px 8px; border-radius:3px; border:none; cursor:pointer; font-size:11px; color:white; background:#546e7a; }
  .btn-sm:hover { background:#607d8b; }
  .btn-sm.warn { background:#37474f; }
  .btn-upload { padding:4px 10px; border-radius:3px; border:none; cursor:pointer; font-size:12px; color:white; background:#e65100; font-weight:bold; }
  .btn-fly { padding:4px 10px; border-radius:3px; border:none; cursor:pointer; font-size:12px; color:white; background:#2e7d32; font-weight:bold; }
</style>
