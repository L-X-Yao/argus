<script lang="ts">
  import { app, saveSettings } from '../lib/stores.svelte';
  let { toggleTheme }: { toggleTheme: () => void } = $props();
</script>

<div class="status-bar">
  <h1>PL-Link 地面站 <span class="ver">v3.0</span></h1>
  <div class="right">
    <span class="dot" class:on={app.drone.connected} class:off={!app.drone.connected}></span>
    <span>{app.drone.connected ? '已连接' : '未连接'}</span>
    {#if app.drone.frames > 0}
      <span class="dim"> | {app.drone.frames} 帧</span>
    {/if}
    <button class="hdr-btn" onclick={() => { app.audioMuted = !app.audioMuted; saveSettings(); }}
      style:opacity={app.audioMuted ? 0.4 : 1}>声音</button>
    <button class="hdr-btn" onclick={() => { app.voiceEnabled = !app.voiceEnabled; }}
      style:opacity={app.voiceEnabled ? 1 : 0.4}>语音</button>
    <button class="hdr-btn" onclick={toggleTheme}>主题</button>
    {#if !app.wsConnected}
      <span class="warn">WS断开</span>
    {/if}
  </div>
</div>

<style>
  .status-bar { background:var(--bg-panel); padding:8px 20px; display:flex; align-items:center; justify-content:space-between; border-bottom:2px solid var(--border); }
  h1 { font-size:18px; color:var(--text-accent); margin:0; }
  .ver { font-size:11px; color:var(--text-dim); font-weight:normal; }
  .right { display:flex; align-items:center; gap:8px; font-size:13px; }
  .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
  .dot.on { background:#69f0ae; }
  .dot.off { background:#ff5252; }
  .dim { color:var(--text-dim); }
  .warn { color:#ffc107; }
  .hdr-btn { padding:2px 8px; background:none; border:1px solid var(--border-light); color:var(--text-dim); border-radius:3px; cursor:pointer; font-size:11px; }
</style>
