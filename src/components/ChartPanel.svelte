<script lang="ts">
  import { untrack } from 'svelte';
  import { app } from '../lib/stores.svelte';

  const MAX = 120;
  let altData: number[] = [];
  let spdData: number[] = [];
  let batData: number[] = [];
  let curData: number[] = [];

  $effect(() => {
    if (!app.drone.connected) return;
    const alt = app.drone.alt_rel;
    const spd = app.drone.gs;
    const bat = app.drone.voltage;
    const cur = app.drone.current;
    untrack(() => {
      altData.push(alt); spdData.push(spd); batData.push(bat); curData.push(cur);
      if (altData.length > MAX) altData.shift();
      if (spdData.length > MAX) spdData.shift();
      if (batData.length > MAX) batData.shift();
      if (curData.length > MAX) curData.shift();
    });
    if (app.chartsOpen) {
      untrack(() => {
        draw(cAlt, altData, '#4fc3f7');
        draw(cSpd, spdData, '#69f0ae');
        draw(cBat, batData, '#ffa726');
        draw(cCur, curData, '#ff5252');
      });
    }
  });

  function draw(canvas: HTMLCanvasElement | null, data: number[], color: string) {
    if (!canvas || data.length < 2) return;
    const ctx = canvas.getContext('2d')!;
    const w = canvas.width = canvas.parentElement!.clientWidth;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    let mn = Math.min(...data), mx = Math.max(...data);
    if (mx === mn) { mx += 1; mn -= 1; }
    const rng = mx - mn;
    ctx.strokeStyle = '#333'; ctx.lineWidth = 0.5;
    for (let i = 0; i < 4; i++) { const y = h * i / 3; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
    ctx.fillStyle = '#666'; ctx.font = '9px monospace';
    ctx.fillText(mx.toFixed(1), 2, 10);
    ctx.fillText(mn.toFixed(1), 2, h - 3);
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
      const x = i / (data.length - 1) * w, y = (1 - (data[i] - mn) / rng) * (h - 4) + 2;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.fillStyle = color; ctx.font = 'bold 11px monospace';
    ctx.fillText(data[data.length - 1].toFixed(1), w - 45, 12);
  }

  let cAlt: HTMLCanvasElement;
  let cSpd: HTMLCanvasElement;
  let cBat: HTMLCanvasElement;
  let cCur: HTMLCanvasElement;
</script>

<div class="panel" style="margin:0 10px 10px">
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <h2 style="cursor:pointer" onclick={() => app.chartsOpen = !app.chartsOpen}>
    实时图表 <span class="toggle">{app.chartsOpen ? '▼' : '▶'}</span>
  </h2>
  {#if app.chartsOpen}
    <div class="charts">
      <div><div class="label">高度 (m)</div><canvas bind:this={cAlt} height="80"></canvas></div>
      <div><div class="label">速度 (m/s)</div><canvas bind:this={cSpd} height="80"></canvas></div>
      <div><div class="label">电压 (V)</div><canvas bind:this={cBat} height="80"></canvas></div>
      <div><div class="label">电流 (A)</div><canvas bind:this={cCur} height="80"></canvas></div>
    </div>
  {/if}
</div>

<style>
  .panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0; text-transform:uppercase; letter-spacing:1px; }
  .toggle { font-size:10px; }
  .charts { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }
  .label { font-size:11px; color:var(--text-dim); }
  canvas { width:100%; background:var(--bg-card); border-radius:4px; }
</style>
