<script lang="ts">
  import { app, pushUndo, undo, deleteWaypoint, clearWaypoints, saveSettings, saveWaypoints, generateCircle, addToast, showConfirm } from '../lib/stores.svelte';
  import { t } from '../lib/i18n.svelte';
  import type { Waypoint } from '../lib/types';

  function fitAfterLoad() { requestAnimationFrame(() => app.fitRouteFlag++); }
  import { sendCommand } from '../lib/ws';
  import { toGcj } from '../lib/gcj02';
  import Button from '$lib/components/ui/button/button.svelte';

  let showCircleGen = $state(false);
  let circleRadius = $state(50);
  let circleCount = $state(12);

  function genCircle() {
    const center = app.drone.lat !== 0
      ? { lat: app.drone.lat, lon: app.drone.lon }
      : app.waypoints.length > 0
        ? { lat: app.waypoints[app.waypoints.length - 1].lat, lon: app.waypoints[app.waypoints.length - 1].lon }
        : { lat: 34.258, lon: 108.942 };
    generateCircle(center.lat, center.lon, circleRadius, circleCount, app.defaultAlt);
    showCircleGen = false;
    fitAfterLoad();
  }

  function toggleDrop(i: number) { pushUndo(); app.waypoints[i].drop = !app.waypoints[i].drop; saveWaypoints(); }
  function setAlt(i: number, v: string) { app.waypoints[i].alt = parseFloat(v) || 30; saveWaypoints(); saveSettings(); }
  function setSpeed(i: number, v: string) { app.waypoints[i].speed = parseFloat(v) || 0; saveWaypoints(); }
  function cycleType(i: number) {
    pushUndo();
    const types: ('wp' | 'loiter_turns' | 'loiter_time' | 'spline')[] = ['wp', 'spline', 'loiter_turns', 'loiter_time'];
    const cur = types.indexOf(app.waypoints[i].type || 'wp');
    app.waypoints[i].type = types[(cur + 1) % types.length];
    if (app.waypoints[i].type === 'loiter_turns' && !app.waypoints[i].loiter_param) app.waypoints[i].loiter_param = 3;
    if (app.waypoints[i].type === 'loiter_time' && !app.waypoints[i].loiter_param) app.waypoints[i].loiter_param = 10;
    saveWaypoints();
  }
  function typeLabel(tp: string): string {
    if (tp === 'loiter_turns') return t('wp.loiterTurns');
    if (tp === 'loiter_time') return t('wp.loiterTime');
    if (tp === 'spline') return t('wp.spline');
    return t('wp.waypoint');
  }
  function typeColor(t: string): string {
    if (t === 'loiter_turns') return '#ab47bc';
    if (t === 'loiter_time') return '#7e57c2';
    if (t === 'spline') return '#00897b';
    return '#1565c0';
  }
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
    if (!await showConfirm(t('confirm.armAndFly').replace('{alt}', String(app.defaultAlt)), true)) return;
    uploadMission();
    addToast(t('toast.uploading'), 'info', 2000);
    await new Promise(r => setTimeout(r, 1500));
    sendCommand('arm');
    addToast(t('toast.arming'), 'info', 2000);
    await new Promise(r => setTimeout(r, 2500));
    if (!app.drone.armed) { addToast(t('toast.armFail'), 'error'); return; }
    sendCommand('takeoff', undefined, { alt: app.defaultAlt });
    addToast(`${t('ctrl.takeoff')} ${app.defaultAlt}m...`, 'info', 3000);
    await new Promise(r => setTimeout(r, 3000));
    if (app.drone.alt_rel < 1) { addToast(t('toast.takeoffFail'), 'error'); return; }
    sendCommand('mission_start');
    addToast(t('toast.missionStart'), 'success');
  }

  function saveMission() {
    const data = JSON.stringify({ waypoints: app.waypoints, alt: app.defaultAlt }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'mission_' + new Date().toISOString().slice(0, 10) + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function loadMission() {
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.json,.waypoints,.plan';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev: any) => {
        try {
          const text: string = ev.target.result;
          const name = file.name.toLowerCase();
          if (name.endsWith('.waypoints')) {
            parseQgcWaypoints(text);
          } else if (name.endsWith('.plan')) {
            parseQgcPlan(text);
          } else {
            const d = JSON.parse(text);
            pushUndo();
            app.waypoints = d.waypoints || [];
            if (d.alt) app.defaultAlt = d.alt;
          }
          fitAfterLoad();
        } catch (err) { addToast(t('toast.loadFail'), 'error'); }
      };
      reader.readAsText(file);
    };
    input.click();
  }

  function parseQgcWaypoints(text: string) {
    const wps: Waypoint[] = [];
    for (const line of text.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('QGC') || trimmed.startsWith('#')) continue;
      const cols = trimmed.split('\t');
      if (cols.length < 12) continue;
      const cmd = parseInt(cols[3]);
      if (cmd !== 16 && cmd !== 82) continue;
      const lat = parseFloat(cols[8]), lon = parseFloat(cols[9]), alt = parseFloat(cols[10]);
      if (Math.abs(lat) < 0.001) continue;
      wps.push({ lat, lon, alt, drop: false, delay: parseFloat(cols[4]) || 0, speed: 0, type: cmd === 82 ? 'spline' : 'wp', loiter_param: 0 });
    }
    pushUndo();
    app.waypoints = wps;
  }

  function parseQgcPlan(text: string) {
    const plan = JSON.parse(text);
    const items = plan?.mission?.items || [];
    const wps: Waypoint[] = [];
    for (const item of items) {
      const cmd = item.command;
      if (cmd !== 16 && cmd !== 82) continue;
      const params = item.params || [];
      const lat = params[4] ?? 0, lon = params[5] ?? 0, alt = params[6] ?? 30;
      if (Math.abs(lat) < 0.001) continue;
      wps.push({ lat, lon, alt, drop: false, delay: params[0] || 0, speed: 0, type: cmd === 82 ? 'spline' : 'wp', loiter_param: 0 });
    }
    pushUndo();
    app.waypoints = wps;
  }

  function exportKml() {
    if (!app.waypoints.length) return;
    let coords = app.waypoints.map(w => `${w.lon},${w.lat},${w.alt}`).join('\n');
    const kml = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>PL-Link Mission</name>
<Placemark><name>Route</name><LineString><coordinates>${coords}</coordinates></LineString></Placemark>
</Document></kml>`;
    const blob = new Blob([kml], { type: 'application/vnd.google-earth.kml+xml' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'mission_' + new Date().toISOString().slice(0, 10) + '.kml';
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
          if (!coords.length) throw new Error('No coordinates');
          pushUndo();
          app.waypoints = coords;
          fitAfterLoad();
        } catch (err: any) { addToast('KML: ' + err.message, 'error'); }
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

  function estimateTime(): string {
    if (app.waypoints.length < 2) return '--';
    const defaultSpeed = app.defaultSpeed || 5;
    let totalSec = 0;
    for (let i = 1; i < app.waypoints.length; i++) {
      const d = segDist(app.waypoints[i - 1], app.waypoints[i]);
      const spd = app.waypoints[i].speed > 0 ? app.waypoints[i].speed : defaultSpeed;
      totalSec += d / spd;
      if (app.waypoints[i].type === 'loiter_time') totalSec += app.waypoints[i].loiter_param || 0;
      if (app.waypoints[i].type === 'loiter_turns') totalSec += (app.waypoints[i].loiter_param || 0) * 20;
      totalSec += app.waypoints[i].delay || 0;
    }
    const m = Math.floor(totalSec / 60), s = Math.round(totalSec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function fmtSegDist(i: number): string {
    if (i < 1 || i >= app.waypoints.length) return '';
    const d = segDist(app.waypoints[i - 1], app.waypoints[i]);
    return d < 1000 ? d.toFixed(0) + 'm' : (d / 1000).toFixed(1) + 'km';
  }

  function segDist(a: any, b: any): number {
    const dlat = (b.lat - a.lat) * 111320;
    const dlon = (b.lon - a.lon) * 111320 * Math.cos(a.lat * Math.PI / 180);
    return Math.sqrt(dlat * dlat + dlon * dlon);
  }

  let profileCanvas: HTMLCanvasElement = $state(null!);

  $effect(() => {
    if (!profileCanvas || app.waypoints.length < 2) return;
    const wps = app.waypoints;
    const ctx = profileCanvas.getContext('2d')!;
    const w = profileCanvas.width = profileCanvas.parentElement!.clientWidth;
    const h = profileCanvas.height;
    ctx.clearRect(0, 0, w, h);

    const dists: number[] = [0];
    for (let i = 1; i < wps.length; i++) {
      dists.push(dists[i - 1] + segDist(wps[i - 1], wps[i]));
    }
    const totalD = dists[dists.length - 1] || 1;
    const alts = wps.map(wp => wp.alt);
    let mn = Math.min(...alts), mx = Math.max(...alts);
    if (mx === mn) { mx += 5; mn = Math.max(0, mn - 5); }
    const pad = (mx - mn) * 0.1;
    mn -= pad; mx += pad;

    ctx.fillStyle = 'rgba(21,101,192,0.15)';
    ctx.beginPath();
    ctx.moveTo(0, h);
    for (let i = 0; i < wps.length; i++) {
      const x = (dists[i] / totalD) * w;
      const y = (1 - (alts[i] - mn) / (mx - mn)) * (h - 16) + 8;
      if (i === 0) ctx.lineTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = '#1565c0';
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < wps.length; i++) {
      const x = (dists[i] / totalD) * w;
      const y = (1 - (alts[i] - mn) / (mx - mn)) * (h - 16) + 8;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    ctx.fillStyle = '#aaa';
    ctx.font = '9px monospace';
    for (let i = 0; i < wps.length; i++) {
      const x = (dists[i] / totalD) * w;
      const y = (1 - (alts[i] - mn) / (mx - mn)) * (h - 16) + 8;
      ctx.fillStyle = wps[i].drop ? '#e65100' : '#1565c0';
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
      if (i === 0 || i === wps.length - 1 || wps.length <= 6) {
        ctx.fillStyle = '#888';
        ctx.fillText(`${alts[i].toFixed(0)}m`, x + 4, y - 4);
      }
    }

    ctx.fillStyle = '#555';
    ctx.fillText(`${mn.toFixed(0)}m`, 2, h - 2);
    ctx.fillText(`${mx.toFixed(0)}m`, 2, 10);
  });
</script>

<div class="bg-card border border-border rounded-xl p-3 w-72 shrink-0 overflow-hidden flex flex-col">
  <div class="flex items-center gap-2 mb-2">
    <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('wp.title')}</h2>
    <span class="text-xs text-muted-foreground">({app.waypoints.length})</span>
    {#if app.drone.connected && app.drone.wp > 0}
      <span class="text-[11px] text-warning ml-auto">WP #{app.drone.wp}</span>
    {/if}
  </div>
  <div class="flex-1 overflow-y-auto max-h-72 rounded-lg border border-border/50">
    {#each app.waypoints as wp, i}
      <div class="flex items-center gap-1 px-1 py-1 border-b border-border/30 text-xs hover:bg-muted/50 transition-colors
        {app.drone.wp === i + 2 ? 'bg-warning/10 border-l-2 border-l-warning pl-0.5' : ''}">
        <button class="w-5 text-center text-primary font-bold text-[11px] hover:underline cursor-pointer bg-transparent border-none p-0"
                onclick={() => app.focusWp = i} title={t('tip.focusWp')}>{i + 1}</button>
        <button class="px-1 py-px rounded text-[9px] font-bold border-none text-white cursor-pointer whitespace-nowrap"
                style="background:{typeColor(wp.type || 'wp')}" onclick={() => cycleType(i)}
                title={t('tip.cycleType')}>
          {typeLabel(wp.type || 'wp')}
        </button>
        <button class="w-4.5 h-4.5 rounded border shrink-0 text-[10px] font-bold p-0 leading-[18px] text-center cursor-pointer
          {wp.drop ? 'bg-orange-700 text-white border-orange-700' : 'bg-transparent text-muted-foreground border-border'}"
                onclick={() => toggleDrop(i)} title={t('tip.dropToggle')}>
          {wp.drop ? 'D' : '·'}
        </button>
        {#if (wp.type === 'loiter_turns' || wp.type === 'loiter_time')}
          <input type="number" class="w-7 bg-input text-purple-400 border border-border px-0.5 rounded text-[10px] text-right"
                 value={wp.loiter_param}
                 onchange={(e) => { app.waypoints[i].loiter_param = parseFloat((e.target as HTMLInputElement).value) || 0; saveWaypoints(); }}
                 title={wp.type === 'loiter_turns' ? t('tip.turns') : t('tip.seconds')} />
        {/if}
        <span class="flex-1 text-muted-foreground text-[10px] overflow-hidden whitespace-nowrap">{wp.lat.toFixed(5)},{wp.lon.toFixed(5)}
          {#if i > 0}<span class="text-muted-foreground/60 text-[9px] ml-0.5">{fmtSegDist(i)}</span>{/if}
        </span>
        <input type="number" class="w-9 bg-input text-foreground border border-border px-0.5 rounded text-[11px] text-right"
               value={wp.alt} onchange={(e) => setAlt(i, (e.target as HTMLInputElement).value)} title={t('tip.altM')} />
        <input type="number" class="w-9 bg-input text-success border border-border px-0.5 rounded text-[11px] text-right"
               value={wp.speed || ''} placeholder="—"
               onchange={(e) => setSpeed(i, (e.target as HTMLInputElement).value)} title={t('tip.spdMs')} />
        <button class="bg-transparent border-none text-muted-foreground cursor-pointer text-xs px-px" onclick={() => moveWp(i, -1)}>&uarr;</button>
        <button class="bg-transparent border-none text-muted-foreground cursor-pointer text-xs px-px" onclick={() => moveWp(i, 1)}>&darr;</button>
        <button class="bg-transparent border-none text-destructive cursor-pointer text-base px-0.5 leading-none" onclick={() => deleteWaypoint(i)}>&times;</button>
      </div>
    {:else}
      <div class="text-muted-foreground text-xs py-4 text-center">{t('wp.clickToAdd')}</div>
    {/each}
  </div>
  {#if app.waypoints.length > 0}
    <div class="text-xs text-warning mt-1.5 leading-relaxed">
      {t('telem.dist')} {totalDist()} · ETA {estimateTime()} · WP {app.waypoints.length}
      {#if app.waypoints.filter(w => w.drop).length > 0}· {t('ctrl.drop')} {app.waypoints.filter(w => w.drop).length}{/if}
      · {t('telem.alt')} {Math.min(...app.waypoints.map(w => w.alt))}-{Math.max(...app.waypoints.map(w => w.alt))}m
    </div>
  {/if}
  {#if app.waypoints.length >= 2}
    <div class="mt-1.5"><canvas bind:this={profileCanvas} height="50" class="w-full bg-background rounded-lg"></canvas></div>
  {/if}
  <div class="flex gap-1 mt-1.5 items-center flex-wrap">
    <label for="def-alt" class="text-[11px] text-muted-foreground">{t('ctrl.altitude')}:</label>
    <input id="def-alt" type="number" bind:value={app.defaultAlt} min="5" max="200" step="5" onchange={saveSettings}
           class="w-12 h-6 px-1 bg-input border border-border rounded text-xs text-foreground" />
    <span class="text-[11px] text-muted-foreground">m</span>
    {#each [10, 30, 50, 100] as a}
      <button class="px-1.5 py-px text-[10px] rounded border cursor-pointer transition-colors
        {app.defaultAlt === a ? 'text-primary border-primary bg-primary/10' : 'text-muted-foreground border-border hover:text-foreground'}"
              onclick={() => { app.defaultAlt = a; saveSettings(); }}>{a}</button>
    {/each}
    <Button variant="outline" size="xs" onclick={applyAltAll}>{t('cat.all')}</Button>
    <Button size="xs" class="bg-orange-700 hover:bg-orange-800 text-white font-bold" onclick={uploadMission}>{t('wp.upload')}</Button>
  </div>
  <div class="flex gap-1 mt-1.5 items-center flex-wrap">
    <Button variant="secondary" size="xs" onclick={saveMission}>{t('wp.save')}</Button>
    <Button variant="secondary" size="xs" onclick={loadMission}>{t('wp.load')}</Button>
    <Button variant="secondary" size="xs" onclick={exportKml}>{t('wp.export')}</Button>
    <Button variant="secondary" size="xs" onclick={importKml}>{t('wp.import')}</Button>
    <Button variant="secondary" size="xs" onclick={reverseRoute}>{t('wp.reverse')}</Button>
    <Button variant="secondary" size="xs" onclick={() => showCircleGen = !showCircleGen}>{t('wp.circle')}</Button>
    <Button variant="secondary" size="xs" onclick={undo} disabled={app.undoStack.length === 0}>{t('wp.undo')}</Button>
    <Button variant="ghost" size="xs" onclick={async () => { if (app.waypoints.length === 0 || await showConfirm(t('confirm.clearWps').replace('{n}', String(app.waypoints.length)))) clearWaypoints(); }}>{t('wp.clear')}</Button>
  </div>
  {#if showCircleGen}
    <div class="flex gap-1 items-center mt-1.5 p-1.5 bg-muted rounded-lg flex-wrap">
      <label for="cr" class="text-[11px] text-muted-foreground">R:</label>
      <input id="cr" type="number" bind:value={circleRadius} min="10" max="2000" step="10"
             class="w-12 h-6 px-1 bg-input border border-border rounded text-xs text-foreground" />
      <span class="text-[11px] text-muted-foreground">m</span>
      <label for="cc" class="text-[11px] text-muted-foreground">N:</label>
      <input id="cc" type="number" bind:value={circleCount} min="4" max="72" step="1"
             class="w-12 h-6 px-1 bg-input border border-border rounded text-xs text-foreground" />
      <Button size="xs" onclick={genCircle}>Gen</Button>
    </div>
  {/if}
</div>
