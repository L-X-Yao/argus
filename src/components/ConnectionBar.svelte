<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { sendConnect, sendDisconnect } from '../lib/ws';

  let port = $state('tcp:localhost:5770');
  let baud = $state(57600);
  function toggle() {
    if (app.drone.connected) {
      sendDisconnect();
    } else {
      sendConnect(port, baud);
    }
  }
</script>

<div class="conn-bar">
  <label for="port-input">端口:</label>
  <input id="port-input" bind:value={port} placeholder="COM3 / tcp:ip:port" class="port-input"
         disabled={app.drone.connected} />
  <label for="baud-select">波特率:</label>
  <select id="baud-select" bind:value={baud} disabled={app.drone.connected}>
    <option value={57600}>57600</option>
    <option value={115200}>115200</option>
  </select>
  <button class:connected={app.drone.connected} onclick={toggle}>
    {app.drone.connected ? '断开' : '连接'}
  </button>
</div>

<style>
  .conn-bar { background:var(--bg-panel); padding:8px 20px; display:flex; gap:10px; align-items:center; border-bottom:1px solid var(--border); }
  label { font-size:13px; color:var(--text-dim); }
  input, select { background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); padding:5px 8px; border-radius:3px; font-size:13px; }
  .port-input { width:180px; }
  button { padding:5px 15px; border-radius:3px; border:none; cursor:pointer; font-size:13px; background:#4caf50; color:white; }
  button.connected { background:#f44336; }
  button:disabled { opacity:0.6; cursor:wait; }
  input:disabled, select:disabled { opacity:0.5; }
</style>
