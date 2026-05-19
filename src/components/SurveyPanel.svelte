<script lang="ts">
  import { app, pushUndo, saveWaypoints, addToast } from '../lib/stores.svelte';
  import { generateSurveyGrid, polygonArea } from '../lib/survey';

  let angle = $state(0);
  let spacing = $state(20);
  let overshoot = $state(10);

  let polyPts = $derived(app.surveyPolygon);
  let area = $derived(polygonArea(polyPts));
  let previewCount = $derived.by(() => {
    if (polyPts.length < 3) return 0;
    return generateSurveyGrid(polyPts, { angle, spacing, alt: app.defaultAlt, overshoot }).length;
  });

  function generate() {
    if (polyPts.length < 3) return;
    const wps = generateSurveyGrid(polyPts, { angle, spacing, alt: app.defaultAlt, overshoot });
    if (wps.length === 0) {
      addToast('无法生成航线，请检查区域和间距', 'warn');
      return;
    }
    pushUndo();
    app.waypoints = [...app.waypoints, ...wps];
    saveWaypoints();
    addToast(`已生成 ${wps.length} 个测绘航点`, 'success');
  }

  function clearPoly() {
    app.surveyPolygon = [];
    app.drawingPolygon = false;
  }

  function fmtArea(m2: number): string {
    if (m2 < 10000) return m2.toFixed(0) + ' m²';
    return (m2 / 10000).toFixed(2) + ' 公顷';
  }
</script>

<div class="survey-panel">
  <h2>测绘规划</h2>

  {#if !app.drawingPolygon && polyPts.length < 3}
    <button class="draw-btn" onclick={() => { app.surveyPolygon = []; app.drawingPolygon = true; }}>
      在地图上绘制区域
    </button>
    <div class="hint">点击地图添加顶点，至少 3 个点</div>
  {:else if app.drawingPolygon}
    <div class="drawing-info">
      <span>已添加 {polyPts.length} 个顶点</span>
      {#if polyPts.length >= 3}
        <button class="btn-sm done" onclick={() => app.drawingPolygon = false}>完成绘制</button>
      {/if}
      <button class="btn-sm" onclick={clearPoly}>取消</button>
    </div>
  {:else}
    <div class="poly-info">
      <span>区域: {fmtArea(area)} | {polyPts.length} 顶点</span>
      <button class="btn-sm" onclick={() => app.drawingPolygon = true}>编辑</button>
      <button class="btn-sm warn" onclick={clearPoly}>清除</button>
    </div>
    <div class="config">
      <div class="row">
        <label for="sv-angle">航线角度</label>
        <input id="sv-angle" type="range" min="0" max="180" step="5" bind:value={angle} />
        <span class="val">{angle}°</span>
      </div>
      <div class="row">
        <label for="sv-spacing">航线间距</label>
        <input id="sv-spacing" type="number" min="5" max="200" step="5" bind:value={spacing} />
        <span class="val">m</span>
      </div>
      <div class="row">
        <label for="sv-over">超越距离</label>
        <input id="sv-over" type="number" min="0" max="100" step="5" bind:value={overshoot} />
        <span class="val">m</span>
      </div>
      <div class="preview">
        预计生成 <b>{previewCount}</b> 个航点 | 高度 {app.defaultAlt}m
      </div>
      <button class="gen-btn" onclick={generate} disabled={previewCount === 0}>生成航线</button>
    </div>
  {/if}
</div>

<style>
  .survey-panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0 0 8px; text-transform:uppercase; letter-spacing:1px; }
  .draw-btn { width:100%; padding:12px; background:transparent; border:2px dashed var(--border-light); border-radius:6px; cursor:pointer; color:var(--text-accent); font-size:14px; font-weight:bold; }
  .draw-btn:hover { border-color:var(--text-accent); }
  .hint { font-size:11px; color:var(--text-dim); margin-top:4px; text-align:center; }
  .drawing-info { display:flex; align-items:center; gap:8px; font-size:13px; }
  .poly-info { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-dim); margin-bottom:8px; }
  .btn-sm { padding:3px 8px; border-radius:3px; border:none; cursor:pointer; font-size:11px; color:white; background:#546e7a; }
  .btn-sm.done { background:#2e7d32; }
  .btn-sm.warn { background:#37474f; }
  .config { display:flex; flex-direction:column; gap:6px; }
  .row { display:flex; align-items:center; gap:6px; }
  .row label { font-size:12px; color:var(--text-dim); width:70px; flex-shrink:0; }
  .row input[type=range] { flex:1; accent-color:#4fc3f7; }
  .row input[type=number] { width:60px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); padding:3px 6px; border-radius:3px; font-size:12px; }
  .val { font-size:12px; color:var(--text-dim); min-width:30px; }
  .preview { font-size:12px; color:var(--text-dim); margin-top:4px; }
  .gen-btn { width:100%; padding:8px; background:#1565c0; color:white; border:none; border-radius:4px; cursor:pointer; font-size:13px; font-weight:bold; margin-top:6px; }
  .gen-btn:disabled { opacity:0.5; cursor:not-allowed; }
  .gen-btn:hover:not(:disabled) { background:#1976d2; }
</style>
