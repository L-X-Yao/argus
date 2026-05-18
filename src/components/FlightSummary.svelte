<script lang="ts">
  import type { FlightSummary } from '../lib/types';
  let { summary, onclose }: { summary: FlightSummary; onclose: () => void } = $props();

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
  function fmtDist(d: number): string {
    return d < 1000 ? d + 'm' : (d / 1000).toFixed(1) + 'km';
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="overlay" onclick={onclose}>
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="box" onclick={(e) => e.stopPropagation()}>
    <h3>飞行摘要</h3>
    <div class="row"><span class="l">飞行时间</span><span class="v">{fmtTime(summary.duration)}</span></div>
    <div class="row"><span class="l">最大高度</span><span class="v">{summary.max_alt} m</span></div>
    <div class="row"><span class="l">最大速度</span><span class="v">{summary.max_speed} m/s</span></div>
    <div class="row"><span class="l">飞行距离</span><span class="v">{fmtDist(summary.total_dist)}</span></div>
    {#if summary.bat_used >= 0}
      <div class="row"><span class="l">电量消耗</span><span class="v">{summary.bat_used}%</span></div>
    {/if}
    <button onclick={onclose}>关闭</button>
  </div>
</div>

<style>
  .overlay { position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.7); z-index:9999; display:flex; align-items:center; justify-content:center; }
  .box { background:var(--bg-panel); border:2px solid var(--text-accent); border-radius:12px; padding:25px 35px; min-width:300px; }
  h3 { color:var(--text-accent); margin:0 0 15px; font-size:18px; }
  .row { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--border); }
  .l { color:var(--text-dim); }
  .v { font-weight:bold; font-size:16px; }
  button { margin-top:15px; width:100%; padding:8px; background:#37474f; color:var(--text-main); border:none; border-radius:4px; cursor:pointer; font-size:14px; }
</style>
