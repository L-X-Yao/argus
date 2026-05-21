<script lang="ts">
  import { onMount } from 'svelte';
  import { connectWs, sendCommand } from './lib/ws';
  import { app, loadSettings, saveSettings, isPlane } from './lib/stores.svelte';
  import { checkAlerts, beep, speak } from './lib/audio';
  import { t, loadLocale, i18nState } from './lib/i18n.svelte';
  import LazyPanelHost from './components/core/LazyPanelHost.svelte';
  import StatusBar from './components/core/StatusBar.svelte';
  import ControlPanel from './components/core/ControlPanel.svelte';
  import MapView from './components/core/MapView.svelte';
  import EventLog from './components/core/EventLog.svelte';
  import MissionPanel from './components/mission/MissionPanel.svelte';
  import FlightSummary from './components/shared/FlightSummary.svelte';
  import ChartPanel from './components/core/ChartPanel.svelte';
  import SettingsPanel from './components/shared/SettingsPanel.svelte';
  import ToastContainer from './components/core/ToastContainer.svelte';
  import PreflightPanel from './components/shared/PreflightPanel.svelte';
  import MissionProgress from './components/mission/MissionProgress.svelte';
  import SurveyPanel from './components/mission/SurveyPanel.svelte';
  import FencePanel from './components/mission/FencePanel.svelte';
  import ParamPanel from './components/params/ParamPanel.svelte';
  import RcPanel from './components/telemetry/RcPanel.svelte';
  import VibrationPanel from './components/telemetry/VibrationPanel.svelte';
  import ServoPanel from './components/telemetry/ServoPanel.svelte';
  import EkfPanel from './components/telemetry/EkfPanel.svelte';
  import TelemetryOverlay from './components/telemetry/TelemetryOverlay.svelte';
  import ConfirmDialog from './components/shared/ConfirmDialog.svelte';
  import SlideConfirm from './components/shared/SlideConfirm.svelte';
  import CommandPalette from './components/shared/CommandPalette.svelte';
  import ReplayPanel from './components/tools/ReplayPanel.svelte';
  let Map3DViewModule: any = $state(null);
  $effect(() => {
    if (app.mapMode === '3d' && !Map3DViewModule) {
      import('./components/map/Map3DView.svelte').then(m => Map3DViewModule = m.default);
    }
  });
  import { showConfirm, showSlide, undo } from './lib/stores.svelte';
  import { migrateLocalStorage } from './lib/migrate';
  import { panels, type PanelId } from './lib/panels.svelte';
  import { ChevronUp, ChevronDown, CornerDownLeft, Pause, HardDrive, Wrench, Video, SlidersHorizontal, PanelLeftClose, Plane, MapPinned, Activity, Settings2, X as XIcon, Globe } from '@lucide/svelte';
  import type { Component } from 'svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  type View = 'fly' | 'plan' | 'monitor' | 'params';
  let view = $state<View>('fly');
  let flyEventsOpen = $state(false);
  let seenEventCount = $state(0);
  let controlsOpen = $state(false);
  let unseenEvents = $derived(app.events.length - seenEventCount);
  const URGENT_TYPES = new Set(['rtl', 'force_disarm', 'cmd_ack_fail', 'mission_ack_fail', 'fence_ack_fail', 'link_lost', 'connect_fail']);
  let hasUrgentEvent = $derived(unseenEvents > 0 && app.events.slice(-unseenEvents).some(
    e => URGENT_TYPES.has(e.event_type) || e.text.includes('!!!')
  ));
  let showCmdPalette = $state(false);
  const p = panels;

  onMount(() => {
    migrateLocalStorage();
    loadLocale();
    loadSettings();
    connectWs();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  $effect(() => {
    if (app.darkTheme) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  });

  $effect(() => {
    document.documentElement.dir = i18nState.locale === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.lang = i18nState.locale;
  });

  $effect(() => {
    const d = app.drone;
    checkAlerts(d.connected, d.armed, d.remaining, d.link_age);
    if (d.flight_summary && !app.summaryShown) app.summaryShown = true;
  });

  $effect(() => {
    if (view === 'monitor') app.chartsOpen = true;
  });

  let prevWsConnected = true;
  $effect(() => {
    const ws = app.wsConnected;
    if (!ws && prevWsConnected) {
      beep(150, 1000, 2, 300);
      speak(t('conn.serviceDown'));
    }
    prevWsConnected = ws;
  });

  $effect(() => {
    const d = app.drone;
    if (d.connected) {
      const parts = [d.mode];
      if (d.armed) parts.push('已解锁');
      parts.push(`${d.voltage.toFixed(1)}V`);
      if (d.gps_fix) parts.push(d.gps_fix);
      let warn = '';
      if ((d.remaining >= 0 && d.remaining < 10) || (d.ekf_flags & 0x480)) warn = '[!!] ';
      else if ((d.remaining >= 0 && d.remaining < 20) || d.link_age > 3) warn = '[!] ';
      document.title = `${warn}Argus — ${parts.join(' | ')}`;
    } else {
      document.title = `${t('app.name')} ${t('welcome.subtitle')}`;
    }
  });

  function onKey(e: KeyboardEvent) {
    if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'SELECT') return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); sendCommand('mode', isPlane() ? 19 : 5); }
    else if (k === 'r') { showConfirm(t('slide.rtl') + '?', true).then(ok => ok && sendCommand('rtl')); }
    else if (k === 'a') { showConfirm(t('slide.arm') + '?', true).then(ok => ok && sendCommand('arm')); }
    else if (k === 'd') sendCommand('disarm');
    else if (k === 'l') { app.darkTheme = !app.darkTheme; saveSettings(); }
    else if (k === 'm') app.mapExpanded = !app.mapExpanded;
    else if (k === 'f' && !e.ctrlKey) {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen().catch(() => {});
    }
    else if (k === 'escape') { p.close('shortcuts'); }
    else if (k === '?' || (k === '/' && e.shiftKey)) { p.toggle('shortcuts'); }
    else if (k === 'k' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); showCmdPalette = !showCmdPalette; }
    else if (k === 's' && e.ctrlKey) { e.preventDefault(); app.showSettings = !app.showSettings; }
    else if (k === 'z' && e.ctrlKey) { e.preventDefault(); undo(); }
    else if (e.ctrlKey && k >= '1' && k <= '4') {
      e.preventDefault();
      const views: View[] = ['fly', 'plan', 'monitor', 'params'];
      view = views[parseInt(k) - 1];
    }
    else if (k >= '1' && k <= '9') {
      const btns = app.drone.mode_btns;
      const idx = parseInt(k) - 1;
      if (idx < btns.length) sendCommand('mode', btns[idx][0]);
    }
  }

  function toggleTheme() { app.darkTheme = !app.darkTheme; saveSettings(); }

  const tabKeys: { id: View; key: string; icon: Component }[] = [
    { id: 'fly', key: 'tab.fly', icon: Plane },
    { id: 'plan', key: 'tab.plan', icon: MapPinned },
    { id: 'monitor', key: 'tab.monitor', icon: Activity },
    { id: 'params', key: 'tab.params', icon: Settings2 },
  ];

  let monitorWarn = $derived(
    app.drone.connected && (
      Math.max(app.drone.vibe[0], app.drone.vibe[1], app.drone.vibe[2]) > 30 ||
      (app.drone.ekf_flags & 0x480) !== 0 ||
      Math.max(app.drone.ekf_vel, app.drone.ekf_pos_h, app.drone.ekf_pos_v, app.drone.ekf_compass) > 0.8
    )
  );
  let planCount = $derived(app.waypoints.length);
  let paramProgress = $derived(app.drone.param_fetching);
  let isMobile = $state(false);
  import { onMount as onMountApp } from 'svelte';
  onMountApp(() => {
    const check = () => { isMobile = window.innerWidth < 768; };
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  });
</script>

<a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:z-[99999] focus:bg-primary focus:text-primary-foreground focus:p-2 focus:rounded-md focus:top-2 focus:left-2">
  Skip to content
</a>
<div class="flex flex-col h-screen overflow-hidden" role="application">
  <StatusBar {toggleTheme} onSettings={() => app.showSettings = !app.showSettings} />

  <nav class="flex items-center gap-1 px-3 py-1 bg-card border-b border-border shrink-0 overflow-x-auto scrollbar-hide max-md:hidden">
    {#each tabKeys as tab}
      <button
        class="flex items-center gap-1.5 px-4 max-sm:px-2.5 py-1.5 text-xs font-semibold tracking-wide uppercase rounded-md transition-all
          {view === tab.id
            ? 'bg-primary text-primary-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
        onclick={() => view = tab.id}
      >
        <tab.icon size={14} />
        {t(tab.key)}
        {#if tab.id === 'monitor' && monitorWarn && view !== 'monitor'}
          <span class="w-2 h-2 rounded-full bg-destructive animate-pulse"></span>
        {/if}
        {#if tab.id === 'plan' && planCount > 0 && view !== 'plan'}
          <span class="px-1 py-px rounded-full bg-primary/20 text-primary text-[9px] font-bold leading-none">{planCount}</span>
        {/if}
        {#if tab.id === 'params' && paramProgress}
          <span class="w-2 h-2 rounded-full bg-warning animate-pulse"></span>
        {/if}
      </button>
    {/each}

    {#if app.drone.connected}
      <div class="ml-auto flex items-center gap-1.5 shrink-0">
        <Button size="sm" class="bg-red-600 hover:bg-red-700 text-white font-bold gap-1"
                onclick={() => showSlide(t('slide.rtl'), 'red', () => sendCommand('rtl'))}
                title="{t('ctrl.rtl')} (R)">
          <CornerDownLeft size={13} />{t('nav.rtl')}
        </Button>
        <Button size="sm" class="bg-amber-600 hover:bg-amber-700 text-white font-bold gap-1"
                onclick={() => sendCommand('mode', isPlane() ? 19 : 5)}
                title="{t('ctrl.pause')} (Space)">
          <Pause size={13} />{t('nav.pause')}
        </Button>
        <Button variant="secondary" size="sm" class="gap-1" onclick={() => p.open('logPanel')}
                title={t('nav.logs')}>
          <HardDrive size={13} />{t('nav.logs')}
        </Button>
        <Button variant="secondary" size="sm" class="gap-1" onclick={() => p.open('calibration')}
                title={t('nav.calibrate')}>
          <Wrench size={13} />{t('nav.calibrate')}
        </Button>
        {#if view === 'fly'}
          <Button variant={app.mapMode === '3d' ? 'default' : 'secondary'} size="sm" class="gap-1"
                  onclick={() => app.mapMode = app.mapMode === '3d' ? '2d' : '3d'}
                  title={app.mapMode === '3d' ? '2D Map' : '3D Globe'}>
            <Globe size={13} />{app.mapMode === '3d' ? '3D' : '2D'}
          </Button>
          <Button variant={p.isOpen('video') ? 'default' : 'secondary'} size="sm" class="gap-1"
                  onclick={() => p.toggle('video')} title="RTSP Video">
            <Video size={13} />{t('nav.video')}
          </Button>
          <Button variant={controlsOpen ? 'default' : 'secondary'} size="sm" class="gap-1"
                  onclick={() => controlsOpen = !controlsOpen} title={t('nav.controls')}>
            {#if controlsOpen}<PanelLeftClose size={13} />{t('nav.collapse')}{:else}<SlidersHorizontal size={13} />{t('nav.controls')}{/if}
          </Button>
        {/if}
      </div>
    {/if}
  </nav>

  {#if view === 'fly'}
    <div id="main-content" class="flex-1 flex overflow-hidden">
      {#if app.drone.connected && controlsOpen}
        <div class="shrink-0 border-r border-border bg-card z-[1002] overflow-y-auto">
          <ControlPanel />
        </div>
      {/if}
      <div class="flex-1 relative min-h-0 flex flex-col min-w-0">
        {#if app.mapMode === '3d' && Map3DViewModule}
          <Map3DViewModule />
        {:else}
          <MapView />
        {/if}
        {#if app.drone.connected}
          <TelemetryOverlay />
        {:else}
          <div class="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[1001] pointer-events-none">
            <div class="bg-card/90 backdrop-blur-md border border-border rounded-2xl shadow-2xl px-8 py-6 text-center min-w-[280px]">
              <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary/15 mb-3">
                <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" class="text-primary">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" />
                </svg>
              </div>
              <h2 class="text-lg font-bold text-primary tracking-wide">{t('app.name')}</h2>
              <p class="text-xs text-muted-foreground mt-1">{t('welcome.subtitle')}</p>
              <div class="mt-4 pt-3 border-t border-border/50">
                <p class="text-xs text-muted-foreground">{t('welcome.hint')}</p>
                <div class="flex items-center justify-center gap-3 mt-2 text-[11px] text-muted-foreground/70">
                  <span><kbd class="px-1 py-px bg-muted border border-border rounded text-[10px] font-mono">Ctrl+K</kbd> {t('cmd.openPalette')}</span>
                  <span><kbd class="px-1 py-px bg-muted border border-border rounded text-[10px] font-mono">?</kbd> {t('welcome.shortcuts')}</span>
                  <span><kbd class="px-1 py-px bg-muted border border-border rounded text-[10px] font-mono">Ctrl+S</kbd> {t('welcome.settings')}</span>
                </div>
              </div>
              {#if !app.wsConnected}
                <div class="mt-3 text-destructive text-[11px] font-bold animate-pulse">{t('welcome.backendDown')}</div>
              {/if}
            </div>
          </div>
        {/if}
        <MissionProgress />
        {#if app.drone.connected && !app.drone.armed}
          <div class="absolute bottom-12 right-3 z-[1001] w-[400px] max-h-56 overflow-auto bg-popover/95 backdrop-blur border border-border rounded-xl shadow-lg">
            <PreflightPanel />
          </div>
        {/if}
        <div class="absolute bottom-0 left-0 right-0 z-[1001]" class:max-h-52={flyEventsOpen}>
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div class="backdrop-blur flex items-center justify-center gap-1 py-1 text-[11px] cursor-pointer border-t hover:text-primary transition-colors
            {hasUrgentEvent ? 'bg-destructive/15 border-destructive/40 text-destructive animate-pulse' : 'bg-card/90 border-border text-muted-foreground'}"
               onclick={() => { flyEventsOpen = !flyEventsOpen; if (flyEventsOpen) seenEventCount = app.events.length; }}>
            {t('event.title')} ({app.events.length})
            {#if unseenEvents > 0 && !flyEventsOpen}
              <span class="px-1.5 py-px rounded-full text-[10px] font-bold {hasUrgentEvent ? 'bg-destructive text-white' : 'bg-primary text-primary-foreground'}">{unseenEvents}</span>
            {/if}
            {#if flyEventsOpen}<ChevronDown size={12} />{:else}<ChevronUp size={12} />{/if}
          </div>
          {#if flyEventsOpen}
            <EventLog />
          {/if}
        </div>
      </div>
    </div>

  {:else if view === 'plan'}
    <div class="flex-1 flex flex-col overflow-auto">
      <div class="flex max-md:flex-col gap-2 p-2 flex-1 min-h-72">
        <MapView showHud={false} />
        <MissionPanel />
      </div>
      {#if app.showSurvey}<SurveyPanel />{/if}
      {#if app.showFence}<FencePanel />{/if}
    </div>

  {:else if view === 'monitor'}
    <div class="flex-1 overflow-auto p-3">
      <div class="grid grid-cols-3 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
        <RcPanel />
        <ServoPanel />
        <VibrationPanel />
        <EkfPanel />
        <div class="max-lg:col-span-2 max-md:col-span-1 col-span-2">
          <ChartPanel />
        </div>
      </div>
    </div>

  {:else if view === 'params'}
    <div class="flex-1 flex flex-col overflow-hidden p-3">
      <ParamPanel />
    </div>
  {/if}

  {#if !app.drone.connected && view === 'fly'}
    <ReplayPanel onposition={(lat, lon, yaw) => app.replayPos = { lat, lon, yaw }} />
  {/if}

  <ToastContainer />
  {#if app.summaryShown && app.drone.flight_summary}
    <FlightSummary summary={app.drone.flight_summary} onclose={() => { app.summaryShown = false; sendCommand('clear_summary'); }} />
  {/if}
  {#if app.showSettings}
    <SettingsPanel onclose={() => app.showSettings = false} />
  {/if}
  <ConfirmDialog />
  <SlideConfirm />
  {#if showCmdPalette}
    <CommandPalette
      onclose={() => showCmdPalette = false}
      onnavigate={(v) => { view = v; showCmdPalette = false; }}
    />
  {/if}
  <LazyPanelHost />
  {#if p.isOpen('shortcuts')}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
         onclick={() => p.close('shortcuts')}>
      <div class="bg-card border border-border rounded-xl shadow-2xl p-5 w-[380px]" onclick={(e) => e.stopPropagation()}>
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('shortcuts.title')}</h2>
          <Button variant="ghost" size="icon-xs" onclick={() => p.close('shortcuts')}>
            <XIcon size={16} />
          </Button>
        </div>
        <div class="space-y-1 text-xs">
          {#each [
            ['Space', t('shortcut.hold')],
            ['R', t('shortcut.rtl')],
            ['A', t('shortcut.arm')],
            ['D', t('shortcut.disarm')],
            ['1-9', t('shortcut.modes')],
            ['Ctrl+1~4', t('shortcut.views')],
            ['M', t('shortcut.mapExpand')],
            ['G', t('shortcut.guided')],
            ['F', t('shortcut.fullscreen')],
            ['L', t('shortcut.theme')],
            ['Ctrl+Z', t('shortcut.undo')],
            ['Ctrl+S', t('shortcut.settings')],
            ['?', t('shortcut.showPanel')],
            ['Ctrl+K', t('cmd.openPalette')],
            ['Esc', t('shortcut.close')],
          ] as [key, desc]}
            <div class="flex items-center gap-3 py-1 border-b border-border/50">
              <kbd class="min-w-[60px] px-2 py-0.5 bg-muted border border-border rounded text-[11px] font-mono font-bold text-center">{key}</kbd>
              <span class="text-muted-foreground">{desc}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/if}

  <!-- Mobile bottom navigation -->
  {#if isMobile}
    <nav class="md:hidden fixed bottom-0 left-0 right-0 z-[2000] bg-card border-t border-border flex items-center justify-around py-1.5 safe-area-bottom">
      {#each tabKeys as tab}
        <button class="flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg transition-all min-w-[56px]
          {view === tab.id ? 'text-primary' : 'text-muted-foreground'}"
          onclick={() => view = tab.id}>
          <tab.icon size={20} />
          <span class="text-[9px] font-semibold">{t(tab.key)}</span>
        </button>
      {/each}
    </nav>
  {/if}
</div>
