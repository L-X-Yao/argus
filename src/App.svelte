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
  import SurveyPanel from './components/SurveyPanel.svelte';
  import FencePanel from './components/FencePanel.svelte';
  import ParamPanel from './components/ParamPanel.svelte';
  import RcPanel from './components/RcPanel.svelte';
  import VibrationPanel from './components/VibrationPanel.svelte';
  import ServoPanel from './components/ServoPanel.svelte';
  import DiagToolbar from './components/DiagToolbar.svelte';

  onMount(() => {
    loadSettings();
    connectWs();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  $effect(() => {
    const d = app.drone;
    checkAlerts(d.connected, d.armed, d.remaining, d.link_age);
    if (d.flight_summary && !app.summaryShown) app.summaryShown = true;
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
    else if (k === 'p') app.showParams = !app.showParams;
    else if (k === 'i') app.showRc = !app.showRc;
    else if (k === 'v' && !e.ctrlKey) app.showVibe = !app.showVibe;
    else if (k === 'o') app.showServo = !app.showServo;
    else if (k === 's' && e.ctrlKey) { e.preventDefault(); app.showSettings = !app.showSettings; }
    else if (k === 'f' && !e.ctrlKey) {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen().catch(() => {});
    }
    else if (k >= '1' && k <= '9') {
      const btns = app.drone.mode_btns;
      const idx = parseInt(k) - 1;
      if (idx < btns.length) sendCommand('mode', btns[idx][0]);
    }
  }

  function toggleTheme() { app.darkTheme = !app.darkTheme; saveSettings(); }
</script>

<div class="app" class:light={!app.darkTheme} class:map-expanded={app.mapExpanded}>
  <StatusBar {toggleTheme} onSettings={() => app.showSettings = !app.showSettings} />
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
  <DiagToolbar />
  {#if app.showSurvey}<SurveyPanel />{/if}
  {#if app.showFence}<FencePanel />{/if}
  {#if app.showParams}<ParamPanel />{/if}
  {#if app.showRc}<RcPanel />{/if}
  {#if app.showVibe}<VibrationPanel />{/if}
  {#if app.showServo}<ServoPanel />{/if}
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
  {#if app.showSettings}
    <SettingsPanel onclose={() => app.showSettings = false} />
  {/if}
</div>

<style>
  :global(body) { margin:0; padding:0; font-family:'Segoe UI',Consolas,monospace; background:var(--bg-body); color:var(--text-main); }
  :global(:root) { --bg-body:#121212; --bg-panel:#1e1e1e; --bg-card:#252525; --bg-input:#2d2d2d; --bg-log:#1a1a1a; --text-main:#e0e0e0; --text-dim:#888; --text-accent:#4fc3f7; --border:#333; --border-light:#555; }
  .light { --bg-body:#f0f0f0; --bg-panel:#fff; --bg-card:#f5f5f5; --bg-input:#e8e8e8; --bg-log:#fafafa; --text-main:#212121; --text-dim:#757575; --text-accent:#1565c0; --border:#ddd; --border-light:#bbb; }
  .app { display:flex; flex-direction:column; height:100vh; }
  .main-row { display:flex; gap:10px; padding:10px; flex-shrink:0; }
  .map-row { display:flex; gap:10px; padding:0 10px 10px; flex:1; min-height:200px; }
  .map-expanded .map-row { flex:1; height:calc(100vh - 100px); }
  @media(max-width:800px) { .main-row { flex-direction:column; } .map-row { flex-direction:column; } }
</style>
