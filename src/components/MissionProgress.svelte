<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let d = $derived(app.drone);

  let isAutoMode = $derived(
    (d.vtype === '多旋翼' && d.mode_id === 3) ||
    (d.vtype === '固定翼' && d.mode_id === 10)
  );

  let wpCount = $derived(app.waypoints.length);
  let currentWpIdx = $derived(Math.max(0, d.wp - 2));
  let progress = $derived(wpCount > 0 ? Math.min(100, (currentWpIdx / wpCount) * 100) : 0);

  let remainingDist = $derived.by(() => {
    if (wpCount === 0 || currentWpIdx >= wpCount) return 0;
    let dist = 0;
    if (currentWpIdx < wpCount && d.lat !== 0) {
      const wp = app.waypoints[currentWpIdx];
      const dlat = (wp.lat - d.lat) * 111320;
      const dlon = (wp.lon - d.lon) * 111320 * Math.cos(d.lat * Math.PI / 180);
      dist += Math.sqrt(dlat * dlat + dlon * dlon);
    }
    for (let i = currentWpIdx + 1; i < wpCount; i++) {
      const a = app.waypoints[i - 1], b = app.waypoints[i];
      const dlat = (b.lat - a.lat) * 111320;
      const dlon = (b.lon - a.lon) * 111320 * Math.cos(a.lat * Math.PI / 180);
      dist += Math.sqrt(dlat * dlat + dlon * dlon);
    }
    return dist;
  });

  let eta = $derived(d.gs > 0.5 ? Math.round(remainingDist / d.gs) : -1);

  function fmtDist(m: number): string {
    return m < 1000 ? `${m.toFixed(0)}m` : `${(m / 1000).toFixed(1)}km`;
  }
  function fmtEta(s: number): string {
    if (s < 0) return '---';
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
</script>

{#if isAutoMode && d.armed && wpCount > 0}
  <div class="progress-bar-wrap">
    <div class="progress-header">
      <span>任务进度 #{d.wp}</span>
      <span>{currentWpIdx}/{wpCount} 航点</span>
    </div>
    <div class="progress-track">
      <div class="progress-fill" style="width:{progress}%"></div>
      {#each Array(wpCount) as _, i}
        <div class="wp-tick" style="left:{((i + 1) / wpCount) * 100}%"
             class:done={i < currentWpIdx}
             class:active={i === currentWpIdx}></div>
      {/each}
    </div>
    <div class="progress-footer">
      <span>剩余 {fmtDist(remainingDist)}</span>
      <span>预计 {fmtEta(eta)}</span>
      <span>{d.gs.toFixed(1)} m/s</span>
    </div>
  </div>
{/if}

<style>
  .progress-bar-wrap { background:var(--bg-panel); border-radius:8px; padding:8px 15px; margin:0 10px 10px; }
  .progress-header { display:flex; justify-content:space-between; font-size:12px; color:var(--text-dim); margin-bottom:4px; }
  .progress-track { position:relative; height:8px; background:#333; border-radius:4px; overflow:visible; }
  .progress-fill { height:100%; background:linear-gradient(90deg, #1565c0, #4fc3f7); border-radius:4px; transition:width 0.5s; }
  .wp-tick { position:absolute; top:-2px; width:4px; height:12px; background:#555; border-radius:2px; transform:translateX(-50%); }
  .wp-tick.done { background:#4fc3f7; }
  .wp-tick.active { background:#ffa726; width:6px; }
  .progress-footer { display:flex; justify-content:space-between; font-size:11px; color:var(--text-dim); margin-top:4px; }
</style>
