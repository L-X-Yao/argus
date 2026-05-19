<script lang="ts">
  import { app, addToast } from '../lib/stores.svelte';

  let drawingFence = $state(false);

  function startDraw() {
    app.fencePolygon = [];
    drawingFence = true;
    app.drawingFence = true;
  }

  function finishDraw() {
    drawingFence = false;
    app.drawingFence = false;
  }

  function clearFence() {
    app.fencePolygon = [];
    app.drawingFence = false;
    drawingFence = false;
  }

  function fmtArea(): string {
    if (app.fencePolygon.length < 3) return '---';
    const pts = app.fencePolygon;
    const origin = pts[0];
    let area = 0;
    for (let i = 0; i < pts.length; i++) {
      const j = (i + 1) % pts.length;
      const x1 = (pts[i].lon - origin.lon) * 111320 * Math.cos(origin.lat * Math.PI / 180);
      const y1 = (pts[i].lat - origin.lat) * 111320;
      const x2 = (pts[j].lon - origin.lon) * 111320 * Math.cos(origin.lat * Math.PI / 180);
      const y2 = (pts[j].lat - origin.lat) * 111320;
      area += x1 * y2 - x2 * y1;
    }
    const m2 = Math.abs(area) / 2;
    return m2 < 10000 ? m2.toFixed(0) + ' m²' : (m2 / 10000).toFixed(2) + ' 公顷';
  }

  function saveFence() {
    const data = JSON.stringify(app.fencePolygon, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '围栏_' + new Date().toISOString().slice(0, 10) + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
    addToast('围栏已导出', 'success');
  }

  function loadFence() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev: any) => {
        try {
          const pts = JSON.parse(ev.target.result);
          if (Array.isArray(pts) && pts.length >= 3) {
            app.fencePolygon = pts;
            addToast(`已加载围栏 (${pts.length} 顶点)`, 'success');
          }
        } catch { addToast('加载失败', 'error'); }
      };
      reader.readAsText(file);
    };
    input.click();
  }

  function exportKml() {
    if (app.fencePolygon.length < 3) return;
    const coords = [...app.fencePolygon, app.fencePolygon[0]]
      .map(p => `${p.lon},${p.lat},0`).join('\n');
    const kml = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>围栏</name>
<Style id="fence"><LineStyle><color>ff4444ff</color><width>2</width></LineStyle>
<PolyStyle><color>224444ff</color></PolyStyle></Style>
<Placemark><name>围栏区域</name><styleUrl>#fence</styleUrl>
<Polygon><outerBoundaryIs><LinearRing><coordinates>${coords}</coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark></Document></kml>`;
    const blob = new Blob([kml], { type: 'application/vnd.google-earth.kml+xml' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '围栏_' + new Date().toISOString().slice(0, 10) + '.kml';
    a.click();
    URL.revokeObjectURL(a.href);
  }
</script>

<div class="fence-panel">
  <h2>电子围栏</h2>
  {#if app.fencePolygon.length < 3 && !drawingFence}
    <div class="actions">
      <button class="draw-btn" onclick={startDraw}>绘制围栏</button>
      <button class="btn-sm" onclick={loadFence}>加载</button>
    </div>
    <div class="hint">在地图上点击添加围栏顶点（至少 3 个）</div>
  {:else if drawingFence}
    <div class="drawing-info">
      <span>已添加 {app.fencePolygon.length} 个顶点</span>
      {#if app.fencePolygon.length >= 3}
        <button class="btn-sm done" onclick={finishDraw}>完成</button>
      {/if}
      <button class="btn-sm" onclick={clearFence}>取消</button>
    </div>
  {:else}
    <div class="fence-info">
      <span>{app.fencePolygon.length} 顶点 | {fmtArea()}</span>
    </div>
    <div class="toolbar">
      <button class="btn-sm" onclick={startDraw}>重新绘制</button>
      <button class="btn-sm" onclick={saveFence}>保存</button>
      <button class="btn-sm" onclick={loadFence}>加载</button>
      <button class="btn-sm" onclick={exportKml}>KML</button>
      <button class="btn-sm warn" onclick={clearFence}>清除</button>
    </div>
  {/if}
</div>

<style>
  .fence-panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  h2 { font-size:14px; color:#f44336; margin:0 0 8px; text-transform:uppercase; letter-spacing:1px; }
  .actions { display:flex; gap:6px; }
  .draw-btn { flex:1; padding:10px; background:transparent; border:2px dashed #f44336; border-radius:6px; cursor:pointer; color:#f44336; font-size:13px; font-weight:bold; }
  .draw-btn:hover { background:rgba(244,67,54,0.08); }
  .hint { font-size:11px; color:var(--text-dim); margin-top:4px; text-align:center; }
  .drawing-info { display:flex; align-items:center; gap:8px; font-size:13px; }
  .fence-info { font-size:12px; color:var(--text-dim); margin-bottom:6px; }
  .toolbar { display:flex; gap:4px; flex-wrap:wrap; }
  .btn-sm { padding:4px 8px; border-radius:3px; border:none; cursor:pointer; font-size:11px; color:white; background:#546e7a; }
  .btn-sm.done { background:#2e7d32; }
  .btn-sm.warn { background:#37474f; }
</style>
