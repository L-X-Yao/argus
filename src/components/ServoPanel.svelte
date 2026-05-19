<script lang="ts">
  import { app } from '../lib/stores.svelte';

  function barWidth(v: number): number {
    return Math.max(0, Math.min(100, (v - 800) / 12));
  }
  function barColor(v: number, armed: boolean): string {
    if (!armed) return '#546e7a';
    if (v < 900 || v > 2100) return '#f44336';
    return '#ffa726';
  }
</script>

<div class="servo-panel">
  <h2>舵机输出</h2>
  {#if app.drone.servo.length > 0}
    <div class="ch-grid">
      {#each app.drone.servo as val, i}
        {#if i < 16 && val > 0}
          <div class="ch-row">
            <span class="ch-label">S{i + 1}</span>
            <div class="ch-bar-bg">
              <div class="ch-bar" style="width:{barWidth(val)}%;background:{barColor(val, app.drone.armed)}"></div>
            </div>
            <span class="ch-val">{val}</span>
          </div>
        {/if}
      {/each}
    </div>
  {:else}
    <div class="empty">未收到舵机数据</div>
  {/if}
</div>

<style>
  .servo-panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0 0 8px; text-transform:uppercase; letter-spacing:1px; }
  .ch-grid { display:grid; grid-template-columns:1fr 1fr; gap:3px 12px; }
  .ch-row { display:flex; align-items:center; gap:4px; font-size:11px; }
  .ch-label { width:22px; color:var(--text-dim); font-size:10px; text-align:right; flex-shrink:0; }
  .ch-bar-bg { flex:1; height:10px; background:var(--bg-card); border-radius:2px; overflow:hidden; }
  .ch-bar { height:100%; border-radius:2px; transition:width 0.15s; }
  .ch-val { width:32px; text-align:right; font-family:monospace; color:var(--text-dim); font-size:10px; flex-shrink:0; }
  .empty { color:var(--text-dim); font-size:12px; text-align:center; padding:10px; }
</style>
