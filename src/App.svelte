<script lang="ts">
  import { onMount } from 'svelte';
  import { connectWs, sendCommand } from './lib/ws';
  import { app, loadSettings, saveSettings } from './lib/stores.svelte';
  import { checkAlerts } from './lib/audio';
  import StatusBar from './components/StatusBar.svelte';
  import ConnectionBar from './components/ConnectionBar.svelte';
  import TelemetryPanel from './components/TelemetryPanel.svelte';
  import ControlPanel from './components/ControlPanel.svelte';
  import MapView from './components/MapView.svelte';
  import EventLog from './components/EventLog.svelte';
  import MissionPanel from './components/MissionPanel.svelte';
  import FlightSummary from './components/FlightSummary.svelte';
  import ChartPanel from './components/ChartPanel.svelte';
  import SettingsPanel from './components/SettingsPanel.svelte';
  import ToastContainer from './components/ToastContainer.svelte';
  import PreflightPanel from './components/PreflightPanel.svelte';
  import MissionProgress from './components/MissionProgress.svelte';
  import ReplayPanel from './components/ReplayPanel.svelte';

  let showSettings = $state(false);

  onMount(() => {
    loadSettings();
    connectWs();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  $effect(() => {
    const d = app.drone;
    checkAlerts(d.connected, d.armed, d.remaining, d.link_age);
    if (d.flight_summary && !app.summaryShown) {
      app.summaryShown = true;
    }
  });

  function onKey(e: KeyboardEvent) {
    if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'SELECT') return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); sendCommand('mode', app.drone.vtype === '固定翼' ? 19 : 5); }
    else if (k === 'r') sendCommand('rtl');
    else if (k === 'a') sendCommand('arm');
    else if (k === 'd') sendCommand('disarm');
    else if (k === 'l') { app.darkTheme = !app.darkTheme; saveSettings(); }
    else if (k === 'm') app.mapExpanded = !app.mapExpanded;
    else if (k === 'c') app.chartsOpen = !app.chartsOpen;
    else if (k === 's' && e.ctrlKey) { e.preventDefault(); showSettings = !showSettings; }
    else if (k >= '1' && k <= '9') {
      const btns = app.drone.mode_btns;
      const idx = parseInt(k) - 1;
      if (idx < btns.length) sendCommand('mode', btns[idx][0]);
    }
  }

  function toggleTheme() { app.darkTheme = !app.darkTheme; saveSettings(); }
</script>

<div class="app" class:light={!app.darkTheme} class:map-expanded={app.mapExpanded}>
  <StatusBar {toggleTheme} onSettings={() => showSettings = !showSettings} />
  <ConnectionBar />
  {#if !app.mapExpanded}
    <div class="main-row">
      <TelemetryPanel />
      <ControlPanel />
    </div>
  {/if}
  <div class="map-row">
    <MapView />
    <MissionPanel />
  </div>
  <MissionProgress />
  {#if !app.mapExpanded}
    {#if app.drone.connected && !app.drone.armed}
      <PreflightPanel />
    {/if}
    <EventLog />
    <ChartPanel />
    {#if !app.drone.connected}
      <ReplayPanel onposition={(lat, lon, yaw) => app.replayPos = { lat, lon, yaw }} />
    {/if}
  {/if}
  <ToastContainer />
  {#if app.summaryShown && app.drone.flight_summary}
    <FlightSummary summary={app.drone.flight_summary} onclose={() => { app.summaryShown = false; sendCommand('clear_summary'); }} />
  {/if}
  {#if showSettings}
    <SettingsPanel onclose={() => showSettings = false} />
  {/if}
</div>
<div class="shortcut-bar"><kbd>Space</kbd> 悬停 <kbd>R</kbd> 返航 <kbd>A</kbd> 解锁 <kbd>D</kbd> 锁定 <kbd>G</kbd> 引导 <kbd>M</kbd> 展开 <kbd>C</kbd> 图表 <kbd>Esc</kbd> 取消 <kbd>1-9</kbd> 模式</div>

<style>
  :global(body) { margin:0; padding:0; font-family:'Segoe UI',Consolas,monospace; background:var(--bg-body); color:var(--text-main); }
  :global(:root) { --bg-body:#121212; --bg-panel:#1e1e1e; --bg-card:#252525; --bg-input:#2d2d2d; --bg-log:#1a1a1a; --text-main:#e0e0e0; --text-dim:#888; --text-accent:#4fc3f7; --border:#333; --border-light:#555; }
  .light { --bg-body:#f0f0f0; --bg-panel:#fff; --bg-card:#f5f5f5; --bg-input:#e8e8e8; --bg-log:#fafafa; --text-main:#212121; --text-dim:#757575; --text-accent:#1565c0; --border:#ddd; --border-light:#bbb; }
  .app { display:flex; flex-direction:column; height:100vh; }
  .main-row { display:flex; gap:10px; padding:10px; flex-shrink:0; }
  .map-row { display:flex; gap:10px; padding:0 10px 10px; flex:1; min-height:200px; }
  .map-expanded .map-row { flex:1; height:calc(100vh - 100px); }
  .shortcut-bar { position:fixed; bottom:8px; left:50%; transform:translateX(-50%); background:rgba(30,30,30,0.85); border:1px solid #444; border-radius:6px; padding:3px 12px; font-size:11px; color:#666; z-index:999; }
  .shortcut-bar kbd { background:#333; border:1px solid #555; border-radius:3px; padding:0 4px; color:#aaa; margin:0 2px; }
  .light .shortcut-bar { background:rgba(255,255,255,0.9); border-color:#ccc; }
  .light .shortcut-bar kbd { background:#e0e0e0; border-color:#bbb; color:#333; }
  @media(max-width:800px) { .main-row { flex-direction:column; } .map-row { flex-direction:column; } }
</style>
