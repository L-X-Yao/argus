<script lang="ts">
  import { app, pushUndo, saveWaypoints, addToast } from '../lib/stores.svelte';
  import { generateSurveyGrid, polygonArea } from '../lib/survey';
  import Button from '$lib/components/ui/button/button.svelte';

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
    if (wps.length === 0) { addToast('无法生成航线，请检查区域和间距', 'warn'); return; }
    pushUndo();
    app.waypoints = [...app.waypoints, ...wps];
    saveWaypoints();
    addToast(`已生成 ${wps.length} 个测绘航点`, 'success');
  }

  function clearPoly() { app.surveyPolygon = []; app.drawingPolygon = false; }

  function fmtArea(m2: number): string {
    if (m2 < 10000) return m2.toFixed(0) + ' m²';
    return (m2 / 10000).toFixed(2) + ' 公顷';
  }
</script>

<div class="bg-card border border-border rounded-xl p-3 mx-2 mb-2">
  <h2 class="text-sm font-semibold text-primary uppercase tracking-wider mb-2">测绘规划</h2>

  {#if !app.drawingPolygon && polyPts.length < 3}
    <button class="w-full py-3 bg-transparent border-2 border-dashed border-border rounded-lg cursor-pointer
                    text-sm font-bold text-primary hover:border-primary transition-colors"
            onclick={() => { app.surveyPolygon = []; app.drawingPolygon = true; }}>
      在地图上绘制区域
    </button>
    <div class="text-[11px] text-muted-foreground mt-1 text-center">点击地图添加顶点，至少 3 个点</div>
  {:else if app.drawingPolygon}
    <div class="flex items-center gap-2 text-sm">
      <span>已添加 {polyPts.length} 个顶点</span>
      {#if polyPts.length >= 3}
        <Button variant="default" size="xs" onclick={() => app.drawingPolygon = false}>完成绘制</Button>
      {/if}
      <Button variant="ghost" size="xs" onclick={clearPoly}>取消</Button>
    </div>
  {:else}
    <div class="flex items-center gap-2 text-xs text-muted-foreground mb-2">
      <span>区域: {fmtArea(area)} | {polyPts.length} 顶点</span>
      <Button variant="outline" size="xs" onclick={() => app.drawingPolygon = true}>编辑</Button>
      <Button variant="ghost" size="xs" onclick={clearPoly}>清除</Button>
    </div>
    <div class="flex flex-col gap-2">
      <div class="flex items-center gap-2">
        <label for="sv-angle" class="text-xs text-muted-foreground w-16 shrink-0">航线角度</label>
        <input id="sv-angle" type="range" min="0" max="180" step="5" bind:value={angle} class="flex-1 accent-primary" />
        <span class="text-xs text-muted-foreground min-w-[30px]">{angle}°</span>
      </div>
      <div class="flex items-center gap-2">
        <label for="sv-spacing" class="text-xs text-muted-foreground w-16 shrink-0">航线间距</label>
        <input id="sv-spacing" type="number" min="5" max="200" step="5" bind:value={spacing}
               class="w-16 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground" />
        <span class="text-xs text-muted-foreground">m</span>
      </div>
      <div class="flex items-center gap-2">
        <label for="sv-over" class="text-xs text-muted-foreground w-16 shrink-0">超越距离</label>
        <input id="sv-over" type="number" min="0" max="100" step="5" bind:value={overshoot}
               class="w-16 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground" />
        <span class="text-xs text-muted-foreground">m</span>
      </div>
      <div class="text-xs text-muted-foreground mt-1">
        预计生成 <b class="text-foreground">{previewCount}</b> 个航点 | 高度 {app.defaultAlt}m
      </div>
      <Button variant="default" class="w-full mt-1" onclick={generate} disabled={previewCount === 0}>
        生成航线
      </Button>
    </div>
  {/if}
</div>
