<script lang="ts">
  import { app } from '../lib/stores.svelte';

  const LABELS = ['横滚', '俯仰', '油门', '偏航', 'CH5', 'CH6', 'CH7', 'CH8',
                  'CH9', 'CH10', 'CH11', 'CH12', 'CH13', 'CH14', 'CH15', 'CH16'];

  function barWidth(v: number): number {
    return Math.max(0, Math.min(100, (v - 800) / 12));
  }
  function barColor(v: number): string {
    if (v < 900 || v > 2100) return '#f44336';
    if (v < 1000 || v > 2000) return '#ff9800';
    return '#4fc3f7';
  }
</script>

<div class="rc-panel">
  <h2>遥控通道 <span class="rssi">RSSI: {app.drone.rc_rssi}</span></h2>
  {#if app.drone.rc.length > 0}
    <div class="ch-grid">
      {#each app.drone.rc as val, i}
        {#if i < 16}
          <div class="ch-row">
            <span class="ch-label">{LABELS[i]}</span>
            <div class="ch-bar-bg">
              <div class="ch-bar" style="width:{barWidth(val)}%;background:{barColor(val)}"></div>
              <div class="ch-center"></div>
            </div>
            <span class="ch-val">{val}</span>
          </div>
        {/if}
      {/each}
    </div>
  {:else}
    <div class="empty">未收到遥控数据</div>
  {/if}
</div>

<style>
  .rc-panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0 0 8px; text-transform:uppercase; letter-spacing:1px; }
  .rssi { font-size:11px; color:var(--text-dim); font-weight:normal; }
  .ch-grid { display:grid; grid-template-columns:1fr 1fr; gap:3px 12px; }
  .ch-row { display:flex; align-items:center; gap:4px; font-size:11px; }
  .ch-label { width:30px; color:var(--text-dim); font-size:10px; text-align:right; flex-shrink:0; }
  .ch-bar-bg { flex:1; height:10px; background:var(--bg-card); border-radius:2px; position:relative; overflow:hidden; }
  .ch-bar { height:100%; border-radius:2px; transition:width 0.15s; }
  .ch-center { position:absolute; left:50%; top:0; width:1px; height:100%; background:#555; }
  .ch-val { width:32px; text-align:right; font-family:monospace; color:var(--text-dim); font-size:10px; flex-shrink:0; }
  .empty { color:var(--text-dim); font-size:12px; text-align:center; padding:10px; }
</style>
