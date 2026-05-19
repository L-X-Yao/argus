<script lang="ts">
  import { untrack } from 'svelte';
  import { app } from '../lib/stores.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';

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
  function vibeBadgeVariant(v: number): 'default' | 'secondary' | 'destructive' | 'outline' {
    if (v < 15) return 'default';
    if (v < 30) return 'secondary';
    return 'destructive';
  }

  let d = $derived(app.drone);
</script>

<div class="bg-card border border-border rounded-xl p-4">
  <h2 class="text-sm font-semibold text-primary uppercase tracking-wider mb-2">振动监控</h2>
  {#if !app.drone.connected}
    <div class="text-muted-foreground text-xs text-center py-8">连接后显示振动数据曲线</div>
  {:else}
    <div class="flex items-center gap-3 text-xs font-mono mb-2">
      <span class="text-red-400">X: {d.vibe[0]?.toFixed(1)}</span>
      <span class="text-green-400">Y: {d.vibe[1]?.toFixed(1)}</span>
      <span class="text-sky-400">Z: {d.vibe[2]?.toFixed(1)}</span>
      <Badge variant={vibeBadgeVariant(Math.max(...d.vibe))} class="text-[10px]">
        {vibeLevel(Math.max(...d.vibe))}
      </Badge>
      {#if d.vibe_clip[0] + d.vibe_clip[1] + d.vibe_clip[2] > 0}
        <span class="text-destructive text-[10px]">裁剪: {d.vibe_clip[0]}/{d.vibe_clip[1]}/{d.vibe_clip[2]}</span>
      {/if}
    </div>
    <div class="w-full">
      <canvas bind:this={canvas} height="80" class="w-full bg-background rounded-lg"></canvas>
    </div>
    <div class="text-center mt-1 text-[9px] text-muted-foreground">
      红线=30 (阈值) │
      <span class="text-red-400">━ X</span>
      <span class="text-green-400"> ━ Y</span>
      <span class="text-sky-400"> ━ Z</span>
    </div>
  {/if}
</div>
