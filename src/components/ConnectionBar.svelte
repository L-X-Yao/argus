<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from '../lib/stores.svelte';
  import { sendConnect, sendDisconnect } from '../lib/ws';

  let port = $state('tcp:localhost:5770');
  let baud = $state(57600);
  let portHistory: string[] = $state([]);
  let showHistory = $state(false);

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
      const detected: string[] = data.ports || [];
      detected.forEach(p => {
        if (!portHistory.includes(p)) portHistory.push(p);
      });
    } catch {}
  }

  function savePortHistory() {
    if (port && !portHistory.includes(port)) {
      portHistory = [port, ...portHistory].slice(0, 10);
    } else if (port) {
      portHistory = [port, ...portHistory.filter(p => p !== port)].slice(0, 10);
    }
    try {
      localStorage.setItem('pllink_port_history', JSON.stringify(portHistory));
      localStorage.setItem('pllink_last_port', port);
      localStorage.setItem('pllink_last_baud', String(baud));
    } catch {}
  }

  function selectPort(p: string) {
    port = p;
    showHistory = false;
  }

  let connecting = $state(false);

  function toggle() {
    if (app.drone.connected) {
      sendDisconnect();
    } else {
      connecting = true;
      savePortHistory();
      sendConnect(port, baud);
      setTimeout(() => connecting = false, 5000);
    }
  }

  $effect(() => {
    if (app.drone.connected) connecting = false;
  });
</script>

<div class="conn-bar">
  <label for="port-input">端口:</label>
  <div class="port-wrap">
    <input id="port-input" bind:value={port} placeholder="COM3 / tcp:ip:port" class="port-input"
           disabled={app.drone.connected}
           onfocus={() => showHistory = true}
           onblur={() => setTimeout(() => showHistory = false, 200)} />
    {#if showHistory && portHistory.length > 0 && !app.drone.connected}
      <div class="port-dropdown">
        {#each portHistory as p}
          <button class="port-opt" onmousedown={() => selectPort(p)}>{p}</button>
        {/each}
      </div>
    {/if}
  </div>
  <label for="baud-select">波特率:</label>
  <select id="baud-select" bind:value={baud} disabled={app.drone.connected}>
    <option value={57600}>57600</option>
    <option value={115200}>115200</option>
  </select>
  <button class:connected={app.drone.connected} class:connecting disabled={connecting && !app.drone.connected} onclick={toggle}>
    {app.drone.connected ? '断开' : connecting ? '连接中...' : '连接'}
  </button>
</div>

<style>
  .conn-bar { background:var(--bg-panel); padding:8px 20px; display:flex; gap:10px; align-items:center; border-bottom:1px solid var(--border); }
  label { font-size:13px; color:var(--text-dim); }
  input, select { background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); padding:5px 8px; border-radius:3px; font-size:13px; }
  .port-wrap { position:relative; }
  .port-input { width:180px; }
  .port-dropdown { position:absolute; top:100%; left:0; right:0; background:var(--bg-panel); border:1px solid var(--border-light); border-radius:0 0 4px 4px; z-index:100; max-height:160px; overflow-y:auto; }
  .port-opt { display:block; width:100%; text-align:left; padding:5px 8px; background:none; border:none; border-bottom:1px solid var(--border); color:var(--text-main); cursor:pointer; font-size:12px; font-family:monospace; }
  .port-opt:hover { background:var(--bg-card); color:var(--text-accent); }
  button { padding:5px 15px; border-radius:3px; border:none; cursor:pointer; font-size:13px; background:#4caf50; color:white; }
  button.connected { background:#f44336; }
  button:disabled { opacity:0.6; cursor:wait; }
  button.connecting { background:#f57f17; animation:pulse 1s infinite; }
  input:disabled, select:disabled { opacity:0.5; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.6; } }
</style>
