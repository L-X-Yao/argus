<script lang="ts">
  import { app, saveSettings } from '../lib/stores.svelte';
  let { toggleTheme, onSettings }: { toggleTheme: () => void; onSettings: () => void } = $props();

  let linkClass = $derived(
    !app.drone.connected ? 'link-off' :
    app.drone.link_age < 0 ? 'link-off' :
    app.drone.link_age < 1 ? 'link-good' :
    app.drone.link_age < 3 ? 'link-warn' : 'link-bad'
  );

  function downloadLog() {
    window.open('/api/log', '_blank');
  }
</script>

<div class="status-bar">
  <h1>PL-Link 地面站 <span class="ver">v3.0</span></h1>
  <div class="right">
    <span class="dot" class:on={app.drone.connected} class:off={!app.drone.connected}></span>
    <span>{app.drone.connected ? '已连接' : '未连接'}</span>
    {#if app.drone.connected}
      <span class="link-icon {linkClass}" title="链路延迟 {app.drone.link_age.toFixed(1)}s">
        {#if app.drone.link_age < 1}●{:else if app.drone.link_age < 3}◐{:else}○{/if}
      </span>
    {/if}
    {#if app.drone.frames > 0}
      <span class="dim"> | {app.drone.frames} 帧</span>
    {/if}
    {#if app.drone.log_active}
      <button class="hdr-btn log-btn" onclick={downloadLog}>日志</button>
    {/if}
    <button class="hdr-btn" onclick={() => { app.audioMuted = !app.audioMuted; saveSettings(); }}
      style:opacity={app.audioMuted ? 0.4 : 1}>声音</button>
    <button class="hdr-btn" onclick={() => { app.voiceEnabled = !app.voiceEnabled; }}
      style:opacity={app.voiceEnabled ? 1 : 0.4}>语音</button>
    <button class="hdr-btn" onclick={toggleTheme}>主题</button>
    <button class="hdr-btn" onclick={onSettings}>设置</button>
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
  .log-btn { color:#69f0ae; border-color:#69f0ae; }
  .link-icon { font-size:14px; }
  .link-good { color:#69f0ae; }
  .link-warn { color:#ffa726; }
  .link-bad { color:#ff5252; }
  .link-off { color:#555; }
</style>
