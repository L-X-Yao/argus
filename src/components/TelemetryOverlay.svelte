<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let d = $derived(app.drone);
  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
</script>

<div class="absolute bottom-8 left-1/2 -translate-x-1/2 z-[1001]
  flex items-center bg-card/90 backdrop-blur-sm border border-border rounded-full
  px-4 py-1 shadow-lg pointer-events-auto">
  <div class="flex flex-col items-center px-2.5 min-w-[40px]">
    <span class="text-base font-bold text-foreground leading-tight tabular-nums">{d.alt_rel.toFixed(1)}<span class="text-[10px] text-muted-foreground ml-0.5">m</span></span>
    <span class="text-[9px] text-muted-foreground uppercase tracking-wider">H</span>
  </div>
  <div class="w-px h-6 bg-border"></div>
  <div class="flex flex-col items-center px-2.5 min-w-[40px]">
    <span class="text-base font-bold text-foreground leading-tight tabular-nums">{d.alt_msl.toFixed(0)}<span class="text-[10px] text-muted-foreground ml-0.5">m</span></span>
    <span class="text-[9px] text-muted-foreground uppercase tracking-wider">MSL</span>
  </div>
  <div class="w-px h-6 bg-border"></div>
  <div class="flex flex-col items-center px-2.5 min-w-[40px]">
    <span class="text-base font-bold text-foreground leading-tight tabular-nums">{d.gs.toFixed(1)}<span class="text-[10px] text-muted-foreground ml-0.5">m/s</span></span>
    <span class="text-[9px] text-muted-foreground uppercase tracking-wider">HS</span>
  </div>
  <div class="w-px h-6 bg-border"></div>
  <div class="flex flex-col items-center px-2.5 min-w-[40px]">
    <span class="text-base font-bold leading-tight tabular-nums
      {d.vz > 0.3 ? 'text-success' : d.vz < -0.3 ? 'text-destructive' : 'text-foreground'}">{d.vz.toFixed(1)}<span class="text-[10px] text-muted-foreground ml-0.5">m/s</span></span>
    <span class="text-[9px] text-muted-foreground uppercase tracking-wider">VS</span>
  </div>
  <div class="w-px h-6 bg-border"></div>
  <div class="flex flex-col items-center px-2.5 min-w-[40px]">
    <span class="text-base font-bold text-foreground leading-tight tabular-nums">{d.dist_home.toFixed(0)}<span class="text-[10px] text-muted-foreground ml-0.5">m</span></span>
    <span class="text-[9px] text-muted-foreground uppercase tracking-wider">D</span>
  </div>
  <div class="w-px h-6 bg-border"></div>
  <div class="flex flex-col items-center px-2.5 min-w-[40px]">
    <span class="text-base font-bold text-foreground leading-tight tabular-nums">{d.hdg.toFixed(0)}&deg;</span>
    <span class="text-[9px] text-muted-foreground uppercase tracking-wider">HDG</span>
  </div>
  {#if d.flight_time > 0}
    <div class="w-px h-6 bg-border"></div>
    <div class="flex flex-col items-center px-2.5 min-w-[40px]">
      <span class="text-base font-bold text-foreground leading-tight tabular-nums">{fmtTime(d.flight_time)}</span>
      <span class="text-[9px] text-muted-foreground uppercase tracking-wider">T</span>
    </div>
  {/if}
</div>
