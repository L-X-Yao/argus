<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';

  function rtl() { if (confirm('切换到返航模式？')) sendCommand('rtl'); }
  function pause() { sendCommand('mode', app.drone.vtype === '固定翼' ? 19 : 5); }
  function forceDisarm() { if (confirm('强制锁定？')) sendCommand('force_disarm'); }

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
</script>

{#if app.mapExpanded && app.drone.connected}
  <div class="mc">
    <div class="mc-status">
      <span class="mc-mode">{app.drone.mode}</span>
      <span class="mc-armed" class:armed={app.drone.armed}>{app.drone.armed ? '解锁' : '锁定'}</span>
      {#if app.drone.flight_time > 0}
        <span class="mc-timer">{fmtTime(app.drone.flight_time)}</span>
      {/if}
    </div>
    <div class="mc-btns">
      <button class="mc-btn rtl" onclick={rtl}>返航</button>
      <button class="mc-btn pause" onclick={pause}>悬停</button>
      {#if !app.drone.armed}
        <button class="mc-btn arm" onclick={() => sendCommand('arm')}>解锁</button>
      {:else}
        <button class="mc-btn disarm" onclick={() => sendCommand('disarm')}>锁定</button>
      {/if}
      {#if app.drone.armed}
        <button class="mc-btn force" onclick={forceDisarm}>强制</button>
      {/if}
    </div>
    <div class="mc-modes">
      {#each app.drone.mode_btns.slice(0, 4) as [id, name]}
        <button class="mc-mode-btn" class:active={app.drone.mode_id === id}
                onclick={() => sendCommand('mode', id)}>{name}</button>
      {/each}
    </div>
  </div>
{/if}

<style>
  .mc { position:absolute; bottom:36px; left:10px; z-index:1000; background:rgba(15,15,15,0.92); border:1px solid #444; border-radius:8px; padding:8px 12px; display:flex; flex-direction:column; gap:6px; min-width:220px; }
  .mc-status { display:flex; align-items:center; gap:8px; }
  .mc-mode { font-size:16px; font-weight:bold; color:#4fc3f7; }
  .mc-armed { padding:2px 8px; border-radius:10px; font-size:11px; font-weight:bold; background:#2e7d32; color:white; }
  .mc-armed.armed { background:#d32f2f; }
  .mc-timer { font-size:13px; color:#ffa726; margin-left:auto; }
  .mc-btns { display:flex; gap:4px; }
  .mc-btn { padding:6px 12px; border:none; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold; color:white; }
  .mc-btn.rtl { background:#d32f2f; }
  .mc-btn.rtl:hover { background:#b71c1c; }
  .mc-btn.pause { background:#f57f17; }
  .mc-btn.arm { background:#e65100; }
  .mc-btn.disarm { background:#558b2f; }
  .mc-btn.force { background:#880e4f; font-size:10px; }
  .mc-modes { display:flex; gap:3px; }
  .mc-mode-btn { padding:4px 8px; border:1px solid #555; border-radius:3px; cursor:pointer; font-size:11px; color:#aaa; background:transparent; }
  .mc-mode-btn:hover { color:#4fc3f7; border-color:#4fc3f7; }
  .mc-mode-btn.active { color:#4fc3f7; border-color:#4fc3f7; background:rgba(79,195,247,0.1); }
</style>
