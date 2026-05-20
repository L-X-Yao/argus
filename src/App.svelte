<script lang="ts">
  import { onMount } from 'svelte';
  import { connectWs, sendCommand } from './lib/ws';
  import { app, loadSettings, saveSettings } from './lib/stores.svelte';
  import { checkAlerts, beep, speak } from './lib/audio';
  import StatusBar from './components/StatusBar.svelte';
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
  import EkfPanel from './components/EkfPanel.svelte';
  import TelemetryOverlay from './components/TelemetryOverlay.svelte';
  import LogPanel from './components/LogPanel.svelte';
  import VideoOverlay from './components/VideoOverlay.svelte';
  import CalibrationPanel from './components/CalibrationPanel.svelte';
  import ConfirmDialog from './components/ConfirmDialog.svelte';
  import { showConfirm } from './lib/stores.svelte';
  import { ChevronUp, ChevronDown, CornerDownLeft, Pause, HardDrive, Wrench, Video, SlidersHorizontal, PanelLeftClose, Plane, MapPinned, Activity, Settings2, X as XIcon } from '@lucide/svelte';
  import type { Component } from 'svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  type View = 'fly' | 'plan' | 'monitor' | 'params';
  let view = $state<View>('fly');
  let flyEventsOpen = $state(false);
  let controlsOpen = $state(false);
  let showLogPanel = $state(false);
  let showVideo = $state(false);
  let showCalibration = $state(false);
  let showShortcuts = $state(false);

  onMount(() => {
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
      speak('服务连接中断');
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
      document.title = `PL-Link — ${parts.join(' | ')}`;
    } else {
      document.title = 'PL-Link 地面站';
    }
  });

  function onKey(e: KeyboardEvent) {
    if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'SELECT') return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); sendCommand('mode', app.drone.vtype === '固定翼' ? 19 : 5); }
    else if (k === 'r') { showConfirm('切换到返航模式？', true).then(ok => ok && sendCommand('rtl')); }
    else if (k === 'a') { showConfirm('确认解锁电机？\n请确保周围无人员。', true).then(ok => ok && sendCommand('arm')); }
    else if (k === 'd') sendCommand('disarm');
    else if (k === 'l') { app.darkTheme = !app.darkTheme; saveSettings(); }
    else if (k === 'm') app.mapExpanded = !app.mapExpanded;
    else if (k === 'f' && !e.ctrlKey) {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen().catch(() => {});
    }
    else if (k === 'escape') { showShortcuts = false; }
    else if (k === '?' || (k === '/' && e.shiftKey)) { showShortcuts = !showShortcuts; }
    else if (k === 's' && e.ctrlKey) { e.preventDefault(); app.showSettings = !app.showSettings; }
    else if (k >= '1' && k <= '9') {
      const btns = app.drone.mode_btns;
      const idx = parseInt(k) - 1;
      if (idx < btns.length) sendCommand('mode', btns[idx][0]);
    }
  }

  function toggleTheme() { app.darkTheme = !app.darkTheme; saveSettings(); }

  const tabs: { id: View; label: string; icon: Component }[] = [
    { id: 'fly', label: '飞行', icon: Plane },
    { id: 'plan', label: '规划', icon: MapPinned },
    { id: 'monitor', label: '监控', icon: Activity },
    { id: 'params', label: '参数', icon: Settings2 },
  ];
</script>

<div class="flex flex-col h-screen overflow-hidden">
  <StatusBar {toggleTheme} onSettings={() => app.showSettings = !app.showSettings} />

  <nav class="flex items-center gap-1 px-3 py-1 bg-card border-b border-border shrink-0 overflow-x-auto scrollbar-hide">
    {#each tabs as tab}
      <button
        class="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold tracking-wide uppercase rounded-md transition-all
          {view === tab.id
            ? 'bg-primary text-primary-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
        onclick={() => view = tab.id}
      >
        <tab.icon size={14} />
        {tab.label}
      </button>
    {/each}

    {#if app.drone.connected}
      <div class="ml-auto flex items-center gap-1.5 shrink-0">
        <Button size="sm" class="bg-red-600 hover:bg-red-700 text-white font-bold gap-1"
                onclick={() => showConfirm('切换到返航模式？', true).then(ok => ok && sendCommand('rtl'))}
                title="返航模式 (快捷键 R)">
          <CornerDownLeft size={13} />返航
        </Button>
        <Button size="sm" class="bg-amber-600 hover:bg-amber-700 text-white font-bold gap-1"
                onclick={() => sendCommand('mode', app.drone.vtype === '固定翼' ? 19 : 5)}
                title="悬停/刹车 (快捷键 Space)">
          <Pause size={13} />悬停
        </Button>
        <Button variant="secondary" size="sm" class="gap-1" onclick={() => showLogPanel = true}
                title="查看/下载机载飞行日志">
          <HardDrive size={13} />日志
        </Button>
        <Button variant="secondary" size="sm" class="gap-1" onclick={() => showCalibration = true}
                title="传感器校准 (罗盘/加速度计/陀螺仪)">
          <Wrench size={13} />校准
        </Button>
        {#if view === 'fly'}
          <Button variant={showVideo ? 'default' : 'secondary'} size="sm" class="gap-1"
                  onclick={() => showVideo = !showVideo} title="RTSP视频画面">
            <Video size={13} />视频
          </Button>
          <Button variant={controlsOpen ? 'default' : 'secondary'} size="sm" class="gap-1"
                  onclick={() => controlsOpen = !controlsOpen} title="解锁/模式/任务控制面板">
            {#if controlsOpen}<PanelLeftClose size={13} />收起{:else}<SlidersHorizontal size={13} />操控{/if}
          </Button>
        {/if}
      </div>
    {/if}
  </nav>

  {#if view === 'fly'}
    <div class="flex-1 flex overflow-hidden">
      {#if app.drone.connected && controlsOpen}
        <div class="shrink-0 border-r border-border bg-card z-[1002] overflow-y-auto">
          <ControlPanel />
        </div>
      {/if}
      <div class="flex-1 relative min-h-0 flex flex-col min-w-0">
        <MapView />
        {#if app.drone.connected}
          <TelemetryOverlay />
        {:else}
          <div class="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[1001]
                      bg-card/90 backdrop-blur border border-border rounded-xl shadow-lg px-6 py-4 text-center pointer-events-none">
            <p class="text-sm font-semibold text-foreground">未连接飞控</p>
            <p class="text-xs text-muted-foreground mt-1">在顶部输入连接地址后点击"连接"</p>
            <p class="text-[11px] text-muted-foreground mt-0.5">按 <kbd class="px-1 py-px bg-muted border border-border rounded text-[10px] font-mono">?</kbd> 查看快捷键</p>
          </div>
        {/if}
        {#if showVideo && app.drone.connected}
          <VideoOverlay onclose={() => showVideo = false} />
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
          <div class="bg-card/90 backdrop-blur text-muted-foreground flex items-center justify-center gap-1 py-1 text-[11px] cursor-pointer border-t border-border hover:text-primary transition-colors"
               onclick={() => flyEventsOpen = !flyEventsOpen}>
            事件 ({app.events.length}) {#if flyEventsOpen}<ChevronDown size={12} />{:else}<ChevronUp size={12} />{/if}
          </div>
          {#if flyEventsOpen}
            <EventLog />
          {/if}
        </div>
      </div>
    </div>

  {:else if view === 'plan'}
    <div class="flex-1 flex flex-col overflow-auto">
      <div class="flex gap-2 p-2 flex-1 min-h-72">
        <MapView showHud={false} />
        <MissionPanel />
      </div>
      {#if app.showSurvey}<SurveyPanel />{/if}
      {#if app.showFence}<FencePanel />{/if}
    </div>

  {:else if view === 'monitor'}
    <div class="flex-1 overflow-auto p-3">
      <div class="grid grid-cols-3 gap-3 max-lg:grid-cols-2 max-md:grid-cols-1">
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
  {#if showLogPanel}
    <LogPanel onclose={() => showLogPanel = false} />
  {/if}
  {#if showCalibration}
    <CalibrationPanel onclose={() => showCalibration = false} />
  {/if}
  <ConfirmDialog />
  {#if showShortcuts}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
         onclick={() => showShortcuts = false}>
      <div class="bg-card border border-border rounded-xl shadow-2xl p-5 w-[380px]" onclick={(e) => e.stopPropagation()}>
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">键盘快捷键</h2>
          <Button variant="ghost" size="icon-xs" onclick={() => showShortcuts = false}>
            <XIcon size={16} />
          </Button>
        </div>
        <div class="space-y-1 text-xs">
          {#each [
            ['Space', '悬停/刹车'],
            ['R', '返航 (需确认)'],
            ['A', '解锁 (需确认)'],
            ['D', '锁定'],
            ['1-9', '切换飞行模式'],
            ['M', '地图展开/收起'],
            ['F', '全屏切换'],
            ['L', '深色/浅色主题'],
            ['Ctrl+S', '设置'],
            ['?', '显示/隐藏此面板'],
            ['Esc', '关闭弹窗'],
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
</div>
