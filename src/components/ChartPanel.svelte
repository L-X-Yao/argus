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
    untrack(() => {
      draw(cAlt, altData, '#4fc3f7');
      draw(cSpd, spdData, '#69f0ae');
      draw(cBat, batData, '#ffa726');
      draw(cCur, curData, '#ff5252');
    });
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

<div class="bg-card border border-border rounded-xl p-4">
  <h2 class="text-sm font-semibold text-primary uppercase tracking-wider mb-2">实时图表</h2>
  <div class="grid grid-cols-2 gap-2">
      <div>
        <div class="text-[11px] text-muted-foreground mb-0.5">高度 (m)</div>
        <canvas bind:this={cAlt} height="80" class="w-full bg-background rounded-lg"></canvas>
      </div>
      <div>
        <div class="text-[11px] text-muted-foreground mb-0.5">速度 (m/s)</div>
        <canvas bind:this={cSpd} height="80" class="w-full bg-background rounded-lg"></canvas>
      </div>
      <div>
        <div class="text-[11px] text-muted-foreground mb-0.5">电压 (V)</div>
        <canvas bind:this={cBat} height="80" class="w-full bg-background rounded-lg"></canvas>
      </div>
      <div>
        <div class="text-[11px] text-muted-foreground mb-0.5">电流 (A)</div>
        <canvas bind:this={cCur} height="80" class="w-full bg-background rounded-lg"></canvas>
      </div>
    </div>
</div>
