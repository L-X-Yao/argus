<script lang="ts">
  import { untrack } from 'svelte';
  import { app } from '../lib/stores.svelte';

  const MAX = 60;
  let xData: number[] = [];
  let yData: number[] = [];
  let zData: number[] = [];

  $effect(() => {
    if (!app.drone.connected) return;
    const [vx, vy, vz] = app.drone.vibe;
    untrack(() => {
      xData.push(vx); yData.push(vy); zData.push(vz);
      if (xData.length > MAX) xData.shift();
      if (yData.length > MAX) yData.shift();
      if (zData.length > MAX) zData.shift();
      draw();
    });
  });

  let canvas: HTMLCanvasElement;

  function draw() {
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const w = canvas.width = canvas.parentElement!.clientWidth;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const all = [...xData, ...yData, ...zData];
    if (all.length < 2) return;
    let mx = Math.max(...all, 30);
    const thresh = 30;

    ctx.fillStyle = 'rgba(244,67,54,0.08)';
    const ty = (1 - thresh / mx) * (h - 8) + 4;
    ctx.fillRect(0, 0, w, ty);

    ctx.strokeStyle = '#333'; ctx.lineWidth = 0.5;
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(0, ty); ctx.lineTo(w, ty); ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = '#666'; ctx.font = '9px monospace';
    ctx.fillText(mx.toFixed(0), 2, 10);
    ctx.fillText('30', w - 18, ty - 2);
    ctx.fillText('0', 2, h - 2);

    const colors = ['#ff5252', '#69f0ae', '#4fc3f7'];
    const datasets = [xData, yData, zData];
    for (let d = 0; d < 3; d++) {
      const data = datasets[d];
      if (data.length < 2) continue;
      ctx.strokeStyle = colors[d]; ctx.lineWidth = 1.5; ctx.beginPath();
      for (let i = 0; i < data.length; i++) {
        const x = i / (data.length - 1) * w;
        const y = (1 - data[i] / mx) * (h - 8) + 4;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }

  function vibeLevel(v: number): string {
    if (v < 15) return '优';
    if (v < 30) return '良';
    if (v < 60) return '差';
    return '危';
  }
  function vibeColor(v: number): string {
    if (v < 15) return '#69f0ae';
    if (v < 30) return '#ffa726';
    if (v < 60) return '#ff5252';
    return '#d32f2f';
  }

  let d = $derived(app.drone);
</script>

<div class="vibe-panel">
  <h2>振动监控</h2>
  <div class="vibe-row">
    <span class="axis" style="color:#ff5252">X: {d.vibe[0]?.toFixed(1)}</span>
    <span class="axis" style="color:#69f0ae">Y: {d.vibe[1]?.toFixed(1)}</span>
    <span class="axis" style="color:#4fc3f7">Z: {d.vibe[2]?.toFixed(1)}</span>
    <span class="level" style="color:{vibeColor(Math.max(...d.vibe))}">
      {vibeLevel(Math.max(...d.vibe))}
    </span>
    {#if d.vibe_clip[0] + d.vibe_clip[1] + d.vibe_clip[2] > 0}
      <span class="clip">裁剪: {d.vibe_clip[0]}/{d.vibe_clip[1]}/{d.vibe_clip[2]}</span>
    {/if}
  </div>
  <div class="chart"><canvas bind:this={canvas} height="80"></canvas></div>
  <div class="legend">
    <span style="color:#666;font-size:9px">红线=30 (阈值) │ </span>
    <span style="color:#ff5252;font-size:9px">━ X</span>
    <span style="color:#69f0ae;font-size:9px"> ━ Y</span>
    <span style="color:#4fc3f7;font-size:9px"> ━ Z</span>
  </div>
</div>

<style>
  .vibe-panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0 0 6px; text-transform:uppercase; letter-spacing:1px; }
  .vibe-row { display:flex; gap:10px; align-items:center; font-size:12px; font-family:monospace; margin-bottom:6px; }
  .level { font-weight:bold; font-size:14px; }
  .clip { color:#f44336; font-size:10px; }
  .chart canvas { width:100%; background:var(--bg-card); border-radius:4px; }
  .legend { text-align:center; margin-top:2px; }
</style>
