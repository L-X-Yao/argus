<script lang="ts">
  import { app, addToast } from '../lib/stores.svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let drawingFence = $state(false);

  function startDraw() { app.fencePolygon = []; drawingFence = true; app.drawingFence = true; }
  function finishDraw() { drawingFence = false; app.drawingFence = false; }
  function clearFence() { app.fencePolygon = []; app.drawingFence = false; drawingFence = false; }

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

<div class="bg-card border border-border rounded-xl p-3 mx-2 mb-2">
  <h2 class="text-sm font-semibold text-destructive uppercase tracking-wider mb-2">电子围栏</h2>
  {#if app.fencePolygon.length < 3 && !drawingFence}
    <div class="flex gap-2">
      <button class="flex-1 py-2.5 bg-transparent border-2 border-dashed border-destructive/50 rounded-lg cursor-pointer
                      text-sm font-bold text-destructive hover:bg-destructive/5 transition-colors"
              onclick={startDraw}>绘制围栏</button>
      <Button variant="outline" size="sm" onclick={loadFence}>加载</Button>
    </div>
    <div class="text-[11px] text-muted-foreground mt-1 text-center">在地图上点击添加围栏顶点（至少 3 个）</div>
  {:else if drawingFence}
    <div class="flex items-center gap-2 text-sm">
      <span>已添加 {app.fencePolygon.length} 个顶点</span>
      {#if app.fencePolygon.length >= 3}
        <Button variant="default" size="xs" onclick={finishDraw}>完成</Button>
      {/if}
      <Button variant="ghost" size="xs" onclick={clearFence}>取消</Button>
    </div>
  {:else}
    <div class="text-xs text-muted-foreground mb-2">{app.fencePolygon.length} 顶点 | {fmtArea()}</div>
    <div class="flex flex-wrap gap-1">
      <Button variant="outline" size="xs" onclick={startDraw}>重新绘制</Button>
      <Button variant="outline" size="xs" onclick={saveFence}>保存</Button>
      <Button variant="outline" size="xs" onclick={loadFence}>加载</Button>
      <Button variant="outline" size="xs" onclick={exportKml}>KML</Button>
      <Button variant="ghost" size="xs" onclick={clearFence}>清除</Button>
    </div>
  {/if}
</div>
