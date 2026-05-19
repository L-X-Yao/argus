<script lang="ts">
  import { onMount } from 'svelte';
  import { app, saveSettings } from '../lib/stores.svelte';
  import { sendConnect, sendDisconnect, sendCommand } from '../lib/ws';

  let { toggleTheme, onSettings }: { toggleTheme: () => void; onSettings: () => void } = $props();

  let port = $state('tcp:localhost:5770');
  let baud = $state(57600);
  let portHistory: string[] = $state([]);
  let showHistory = $state(false);
  let connecting = $state(false);

  onMount(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('pllink_port_history') || '[]');
      if (Array.isArray(saved)) portHistory = saved;
      const lastPort = localStorage.getItem('pllink_last_port');
      if (lastPort) port = lastPort;
      const lastBaud = localStorage.getItem('pllink_last_baud');
      if (lastBaud) baud = parseInt(lastBaud);
    } catch {}
    fetchPorts();
  });

  async function fetchPorts() {
    try {
      const r = await fetch('/api/ports');
      const data = await r.json();
      (data.ports || []).forEach((p: string) => { if (!portHistory.includes(p)) portHistory.push(p); });
    } catch {}
  }

  function savePortHistory() {
    if (port && !portHistory.includes(port)) portHistory = [port, ...portHistory].slice(0, 10);
    else if (port) portHistory = [port, ...portHistory.filter(p => p !== port)].slice(0, 10);
    try {
      localStorage.setItem('pllink_port_history', JSON.stringify(portHistory));
      localStorage.setItem('pllink_last_port', port);
      localStorage.setItem('pllink_last_baud', String(baud));
    } catch {}
  }

  function toggle() {
    if (app.drone.connected) { sendDisconnect(); }
    else { connecting = true; savePortHistory(); sendConnect(port, baud); setTimeout(() => connecting = false, 5000); }
  }

  $effect(() => { if (app.drone.connected) connecting = false; });

  let linkClass = $derived(
    !app.drone.connected ? 'link-off' :
    app.drone.link_age < 0 ? 'link-off' :
    app.drone.link_age < 1 ? 'link-good' :
    app.drone.link_age < 3 ? 'link-warn' : 'link-bad'
  );

  function downloadLog() { window.open('/api/log', '_blank'); }
</script>

<div class="status-bar">
  <div class="left">
    <span class="brand">PL-Link</span>
    <div class="conn-group">
      {#if !app.drone.connected}
        <div class="port-wrap">
          <input bind:value={port} placeholder="tcp:ip:port" class="port-input"
                 onfocus={() => showHistory = true}
                 onblur={() => setTimeout(() => showHistory = false, 200)} />
          {#if showHistory && portHistory.length > 0}
            <div class="port-dropdown">
              {#each portHistory as p}
                <button class="port-opt" onmousedown={() => { port = p; showHistory = false; }}>{p}</button>
              {/each}
            </div>
          {/if}
        </div>
        <select bind:value={baud} class="baud-sel">
          <option value={57600}>57600</option>
          <option value={115200}>115200</option>
        </select>
      {/if}
      <button class="conn-btn" class:connected={app.drone.connected} class:connecting
              disabled={connecting && !app.drone.connected} onclick={toggle}>
        {app.drone.connected ? '断开' : connecting ? '连接中...' : '连接'}
      </button>
    </div>
  </div>
  <div class="right">
    {#if app.drone.connected}
      <span class="mode-pill" onclick={() => {}} title="当前飞行模式">{app.drone.mode}</span>
      <span class="link-icon {linkClass}" title="链路 {app.drone.link_age >= 0 ? app.drone.link_age.toFixed(1) + 's' : ''}">
        {#if app.drone.link_age < 1}●{:else if app.drone.link_age < 3}◐{:else}○{/if}
      </span>
      <span class="stat">GPS {app.drone.gps_fix} {app.drone.gps_sats}</span>
      <span class="stat" style="color:{app.drone.remaining < 20 ? '#f44336' : app.drone.remaining < 40 ? '#ff9800' : '#69f0ae'}">{app.drone.voltage.toFixed(1)}V {app.drone.remaining >= 0 ? app.drone.remaining + '%' : ''}</span>
      {#if app.drone.fw_version}<span class="dim">{app.drone.fw_version}</span>{/if}
      {#if app.drone.log_active}<button class="hdr-btn log-btn" onclick={downloadLog}>日志</button>{/if}
    {:else}
      <span class="dim">未连接</span>
    {/if}
    <button class="hdr-btn" onclick={() => { app.audioMuted = !app.audioMuted; saveSettings(); }}
      style:opacity={app.audioMuted ? 0.4 : 1}>声音</button>
    <button class="hdr-btn" onclick={toggleTheme}>主题</button>
    <button class="hdr-btn" onclick={onSettings}>设置</button>
  </div>
</div>

<style>
  .status-bar { background:var(--bg-panel); padding:5px 12px; display:flex; align-items:center; justify-content:space-between; border-bottom:2px solid var(--border); gap:8px; }
  .left { display:flex; align-items:center; gap:8px; }
  .brand { font-size:15px; font-weight:bold; color:var(--text-accent); white-space:nowrap; }
  .conn-group { display:flex; align-items:center; gap:4px; }
  .port-wrap { position:relative; }
  .port-input { width:150px; padding:3px 6px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); border-radius:3px; font-size:12px; }
  .port-dropdown { position:absolute; top:100%; left:0; right:0; background:var(--bg-panel); border:1px solid var(--border-light); border-radius:0 0 4px 4px; z-index:9999; max-height:140px; overflow-y:auto; }
  .port-opt { display:block; width:100%; text-align:left; padding:4px 6px; background:none; border:none; border-bottom:1px solid var(--border); color:var(--text-main); cursor:pointer; font-size:11px; font-family:monospace; }
  .port-opt:hover { background:var(--bg-card); color:var(--text-accent); }
  .baud-sel { padding:3px 4px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); border-radius:3px; font-size:11px; }
  .conn-btn { padding:3px 12px; border-radius:3px; border:none; cursor:pointer; font-size:12px; font-weight:bold; background:#4caf50; color:white; }
  .conn-btn.connected { background:#f44336; }
  .conn-btn:disabled { opacity:0.6; cursor:wait; }
  .conn-btn.connecting { background:#f57f17; animation:pulse 1s infinite; }
  .right { display:flex; align-items:center; gap:8px; font-size:12px; }
  .mode-pill { background:#1565c0; color:white; padding:2px 10px; border-radius:10px; font-size:12px; font-weight:bold; cursor:default; }
  .stat { color:#ccc; white-space:nowrap; }
  .dim { color:var(--text-dim); }
  .hdr-btn { padding:2px 6px; background:none; border:1px solid var(--border-light); color:var(--text-dim); border-radius:3px; cursor:pointer; font-size:10px; }
  .log-btn { color:#69f0ae; border-color:#69f0ae; }
  .link-icon { font-size:14px; }
  .link-good { color:#69f0ae; }
  .link-warn { color:#ffa726; }
  .link-bad { color:#ff5252; }
  .link-off { color:#555; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.6; } }
</style>
