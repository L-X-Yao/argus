<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';

  function rtl() { if (confirm('切换到返航模式？')) sendCommand('rtl'); }
  function forceDisarm() { if (confirm('强制锁定 — 电机立即停转！\n仅在已着陆时使用。继续？')) sendCommand('force_disarm'); }
  function pause() { sendCommand('mode', app.drone.vtype === '固定翼' ? 19 : 5); }
</script>

<div class="panel controls">
  <button class="btn-rtl" onclick={rtl}>!! 返航 !!</button>
  <button class="btn-pause" onclick={pause}>悬停</button>
  <button class="btn btn-arm" onclick={() => sendCommand('arm')}>解锁</button>
  <button class="btn btn-disarm" onclick={() => sendCommand('disarm')}>锁定</button>
  <button class="btn btn-force" onclick={forceDisarm}>强制锁定</button>

  <div class="section-label">模式</div>
  {#each app.drone.mode_btns as [id, name]}
    <button class="btn btn-mode" class:active={app.drone.mode_id === id}
            onclick={() => sendCommand('mode', id)}>{name}</button>
  {/each}

  <div class="section-label">载荷</div>
  <button class="btn" style="background:#ff6f00;font-size:15px;font-weight:bold" onclick={() => sendCommand('drop')}>投放</button>
  <button class="btn" style="background:#33691e" onclick={() => sendCommand('drop_stop')}>停止</button>

  <div class="section-label">任务</div>
  <button class="btn" style="background:#1565c0" onclick={() => sendCommand('mission_start')}>开始任务</button>
  <button class="btn" style="background:#1565c0" onclick={() => sendCommand('mission_clear')}>清除任务</button>

  <div class="section-label">起飞</div>
  <button class="btn" style="background:#00695c" onclick={() => sendCommand('takeoff', undefined, { alt: app.defaultAlt })}>
    起飞 {app.defaultAlt}m
  </button>
</div>

<style>
  .panel { background:var(--bg-panel); border-radius:8px; padding:15px; width:180px; flex-shrink:0; }
  .btn-rtl { width:100%; padding:14px; background:#d32f2f; color:white; font-size:18px; font-weight:bold; border:none; border-radius:6px; cursor:pointer; margin-bottom:5px; }
  .btn-rtl:hover { background:#b71c1c; }
  .btn-pause { width:100%; padding:10px; background:#f57f17; color:white; font-size:15px; font-weight:bold; border:none; border-radius:6px; cursor:pointer; margin-bottom:10px; }
  .btn { width:100%; padding:8px; margin:3px 0; border:none; border-radius:4px; cursor:pointer; font-size:13px; color:white; }
  .btn-arm { background:#e65100; }
  .btn-disarm { background:#558b2f; }
  .btn-force { background:#b71c1c; font-size:11px; }
  .btn-mode { background:#37474f; }
  .btn-mode:hover { background:#455a64; }
  .btn-mode.active { background:#1565c0; }
  .section-label { font-size:12px; color:var(--text-dim); margin-top:12px; margin-bottom:4px; }
</style>
