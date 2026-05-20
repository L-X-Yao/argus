<script lang="ts">
  import { onMount } from 'svelte';
  import { app, saveSettings } from '../lib/stores.svelte';
  import { sendConnect, sendDisconnect, sendCommand } from '../lib/ws';
  import { t } from '../lib/i18n.svelte';
  import { apiUrl } from '../lib/backend';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';
  import { Volume2, VolumeOff, Sun, Moon, Settings, Satellite } from '@lucide/svelte';

  let { toggleTheme, onSettings }: { toggleTheme: () => void; onSettings: () => void } = $props();

  let port = $state('tcp:localhost:5770');
  let baud = $state(57600);
  let protocol = $state('auto');
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

  const PRESETS = ['tcp:localhost:5770', 'udp:14550', 'udp:14551'];

  async function fetchPorts() {
    try {
      const r = await fetch(apiUrl('/api/ports'));
      const data = await r.json();
      (data.ports || []).forEach((p: string) => { if (!portHistory.includes(p)) portHistory.push(p); });
    } catch {}
    PRESETS.forEach(p => { if (!portHistory.includes(p)) portHistory.push(p); });
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

  let connectTimeout = $state(false);

  function toggle() {
    if (app.drone.connected) { sendDisconnect(); }
    else {
      connecting = true;
      connectTimeout = false;
      savePortHistory();
      sendConnect(port, baud, protocol);
      setTimeout(() => {
        if (connecting && !app.drone.connected) {
          connectTimeout = true;
          connecting = false;
        }
      }, 8000);
    }
  }

  $effect(() => { if (app.drone.connected) { connecting = false; connectTimeout = false; } });

  let linkBars = $derived(
    !app.drone.connected || app.drone.link_age < 0 ? 0 :
    app.drone.link_age < 0.5 ? 4 :
    app.drone.link_age < 1 ? 3 :
    app.drone.link_age < 2 ? 2 :
    app.drone.link_age < 3 ? 1 : 0
  );
  let barColor = $derived(linkBars >= 3 ? '#22c55e' : linkBars >= 2 ? '#eab308' : linkBars >= 1 ? '#ef4444' : '#666');

  let prevFrames = $state(0);
  let msgRate = $state(0);
  $effect(() => {
    const timer = setInterval(() => {
      const f = app.drone.frames;
      msgRate = Math.round((f - prevFrames) / 2);
      prevFrames = f;
      if (app.drone.connected) {
        app.linkHistory.push({ t: Date.now(), rate: msgRate, age: app.drone.link_age });
        if (app.linkHistory.length > 120) app.linkHistory.splice(0, app.linkHistory.length - 90);
      }
    }, 2000);
    return () => clearInterval(timer);
  });

  let battColor = $derived(
    app.drone.remaining < 20 ? 'text-destructive' :
    app.drone.remaining < 40 ? 'text-warning' : 'text-success'
  );

  const EMERGENCY_MODES = ['返航', '着陆', '智能RTL', '刹车', 'QRTL', 'QLAND', '自降'];
  const MANUAL_MODES = ['手动', '增稳', '特技', '训练', '运动', '翻转', '抛飞'];
  let modeVariant = $derived.by((): 'default' | 'secondary' | 'destructive' => {
    const m = app.drone.mode;
    if (EMERGENCY_MODES.some(e => m.includes(e))) return 'destructive';
    if (MANUAL_MODES.some(e => m.includes(e))) return 'secondary';
    return 'default';
  });

  let gpsOk = $derived(
    app.drone.gps_fix === '3D' || app.drone.gps_fix === 'RTK固定' || app.drone.gps_fix === 'RTK浮动' || app.drone.gps_fix === '差分'
  );
  let gpsVariant = $derived.by((): 'default' | 'secondary' | 'destructive' => {
    if (app.drone.gps_fix === 'RTK固定') return 'default';
    if (gpsOk && app.drone.gps_sats >= 10) return 'default';
    if (gpsOk) return 'secondary';
    return 'destructive';
  });

  const EKF_CONST_POS = 128;
  const EKF_UNINITIALIZED = 1024;

  let ekfLevel = $derived.by(() => {
    const f = app.drone.ekf_flags;
    if ((f & EKF_CONST_POS) || (f & EKF_UNINITIALIZED)) return 'red';
    const vars = [app.drone.ekf_vel, app.drone.ekf_pos_h, app.drone.ekf_pos_v, app.drone.ekf_compass];
    if (vars.some(v => v > 0.8)) return 'yellow';
    if (vars.every(v => v < 0.5)) return 'green';
    return 'yellow';
  });

  let ekfVariant = $derived(
    ekfLevel === 'red' ? 'destructive' as const :
    ekfLevel === 'yellow' ? 'secondary' as const : 'default' as const
  );

  let ekfLabel = $derived(
    ekfLevel === 'red' ? t('status.navError') :
    ekfLevel === 'yellow' ? t('status.navWarn') : t('status.nav')
  );

  let ekfTooltip = $derived(
    `速度: ${app.drone.ekf_vel.toFixed(3)}\n水平: ${app.drone.ekf_pos_h.toFixed(3)}\n垂直: ${app.drone.ekf_pos_v.toFixed(3)}\n罗盘: ${app.drone.ekf_compass.toFixed(3)}\n标志: 0x${app.drone.ekf_flags.toString(16).toUpperCase()}`
  );

  function fmtBatTime(s: number): string {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h > 0 ? `~${h}时${m}分` : `~${m}分`;
  }

  function downloadLog() { window.open(apiUrl('/api/log'), '_blank'); }
</script>

<header class="flex items-center justify-between gap-3 px-3 py-1.5 shrink-0 min-w-0 overflow-x-auto scrollbar-hide transition-colors duration-300
  {app.drone.armed ? 'bg-destructive/8 border-b-2 border-destructive/60' : 'bg-card border-b-2 border-border'}">
  <div class="flex items-center gap-2">
    <span class="text-sm font-bold text-primary tracking-wider">{t('app.name')}</span>

    <div class="flex items-center gap-1.5">
      {#if !app.drone.connected}
        <div class="relative">
          <input bind:value={port} placeholder={t('conn.placeholder')}
                 class="w-40 h-7 px-2 text-xs font-mono bg-input border border-border rounded-md text-foreground
                        placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/50 port-input"
                 onfocus={() => showHistory = true}
                 onblur={() => setTimeout(() => showHistory = false, 200)} />
          {#if showHistory && portHistory.length > 0}
            <div class="absolute top-full left-0 right-0 z-[9999] mt-1 bg-popover border border-border rounded-md shadow-lg overflow-hidden">
              {#each portHistory as p}
                <button class="block w-full text-left px-2 py-1.5 text-xs font-mono text-popover-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
                        onmousedown={() => { port = p; showHistory = false; }}>{p}</button>
              {/each}
            </div>
          {/if}
        </div>
        {#if !port.startsWith('tcp:') && !port.startsWith('udp:')}
          <select bind:value={baud}
                  class="h-7 px-1 text-xs bg-input border border-border rounded-md text-foreground cursor-pointer"
                  title="串口波特率">
            <option value={57600}>57600</option>
            <option value={115200}>115200</option>
          </select>
        {/if}
        <select bind:value={protocol}
                class="h-7 px-1 text-xs bg-input border border-border rounded-md text-foreground cursor-pointer"
                title={t('conn.protocol')}>
          <option value="auto">{t('conn.auto')}</option>
          <option value="standard">{t('conn.standard')}</option>
          <option value="pllink">{t('conn.pllink')}</option>
        </select>
      {/if}
      <Button
        variant={app.drone.connected ? 'destructive' : 'default'}
        size="sm"
        disabled={connecting && !app.drone.connected}
        onclick={toggle}
        class={connecting ? 'animate-pulse' : ''}
      >
        {app.drone.connected ? t('conn.disconnect') : connecting ? t('conn.connecting') : t('conn.connect')}
      </Button>
      {#if !app.drone.connected && !connecting}
        <Button variant="outline" size="sm" class="text-[10px] px-2 opacity-60 hover:opacity-100"
                onclick={() => { port = 'udp:14550'; protocol = 'standard'; toggle(); }}
                title="Quick connect to SITL (udp:14550)">SITL</Button>
      {/if}
    </div>
  </div>

  <div class="flex items-center gap-2 text-xs">
    {#if app.drone.connected}
      <Badge variant={modeVariant} class="text-xs font-bold">{app.drone.mode}</Badge>
      {#if app.drone.armed}
        <Badge variant="destructive" class="text-[10px] font-bold animate-pulse">{t('status.armed')}</Badge>
      {/if}

      <span class="flex items-center gap-0.5" title="链路 {app.drone.link_age >= 0 ? app.drone.link_age.toFixed(1) + 's' : '---'} · {msgRate} Hz">
        <svg width="16" height="12" viewBox="0 0 16 12" class="shrink-0">
          <rect x="0" y="9" width="3" height="3" rx="0.5" fill={linkBars >= 1 ? barColor : '#555'} />
          <rect x="4.5" y="6" width="3" height="6" rx="0.5" fill={linkBars >= 2 ? barColor : '#555'} />
          <rect x="9" y="3" width="3" height="9" rx="0.5" fill={linkBars >= 3 ? barColor : '#555'} />
          <rect x="13" y="0" width="3" height="12" rx="0.5" fill={linkBars >= 4 ? barColor : '#555'} />
        </svg>
        {#if app.drone.connected && msgRate > 0}
          <span class="text-[10px] font-mono tabular-nums" style="color:{barColor}">{msgRate}</span>
        {/if}
        {#if app.linkHistory.length > 3}
          {@const pts = app.linkHistory.slice(-20)}
          {@const maxR = Math.max(...pts.map(p => p.rate), 1)}
          <svg width="30" height="10" viewBox="0 0 30 10" class="shrink-0 opacity-50">
            <polyline fill="none" stroke={barColor} stroke-width="1"
              points={pts.map((p, i) => `${(i / (pts.length - 1)) * 30},${10 - (p.rate / maxR) * 9}`).join(' ')} />
          </svg>
        {/if}
      </span>

      <Badge variant={gpsVariant} class="font-mono text-[11px] gap-0.5">
        <Satellite size={11} />{app.drone.gps_fix} {app.drone.gps_sats}
      </Badge>

      <Badge variant={ekfVariant} class="text-[11px]" title={ekfTooltip}>
        {#if ekfLevel === 'green'}
          <span class="inline-block w-1.5 h-1.5 rounded-full bg-green-400 mr-0.5"></span>
        {:else if ekfLevel === 'yellow'}
          <span class="inline-block w-1.5 h-1.5 rounded-full bg-yellow-400 mr-0.5"></span>
        {:else}
          <span class="inline-block w-1.5 h-1.5 rounded-full bg-red-400 mr-0.5 animate-pulse"></span>
        {/if}
        {ekfLabel}
      </Badge>

      <span class="{battColor} font-bold tabular-nums flex items-center gap-1" title="{app.drone.voltage.toFixed(2)}V | {app.drone.current.toFixed(1)}A">
        <svg width="22" height="12" viewBox="0 0 22 12" class="shrink-0">
          <rect x="0.5" y="0.5" width="18" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1"/>
          <rect x="19" y="3" width="2.5" height="6" rx="1" fill="currentColor" opacity="0.5"/>
          {#if app.drone.remaining >= 0}
            <rect x="2" y="2" width="{Math.max(0, Math.min(15, app.drone.remaining / 100 * 15))}" height="8" rx="1"
                  fill="{app.drone.remaining < 20 ? '#ef4444' : app.drone.remaining < 40 ? '#eab308' : '#22c55e'}"/>
          {/if}
        </svg>
        {app.drone.voltage.toFixed(1)}V{app.drone.remaining >= 0 ? ' ' + app.drone.remaining + '%' : ''}{app.drone.current > 0.1 ? ' ' + app.drone.current.toFixed(1) + 'A' : ''}{app.drone.bat_time > 0 ? ' ' + fmtBatTime(app.drone.bat_time) : ''}
      </span>

      {#if app.drone.fw_version}
        <span class="text-muted-foreground text-[10px]">{app.drone.fw_version}</span>
      {/if}

      {#if app.drone.log_active}
        <Button variant="outline" size="xs" onclick={downloadLog} class="text-success border-success/50">{t('status.log')}</Button>
      {/if}
    {:else}
      {#if connectTimeout}
        <span class="text-destructive text-[11px] font-bold">{t('conn.timeout')}</span>
      {:else}
        <span class="text-muted-foreground">{t('conn.disconnected')}</span>
      {/if}
    {/if}
    {#if !app.wsConnected}
      <span class="text-destructive text-[10px] font-bold animate-pulse" title="与后端服务器的连接已断开，正在重连...">
        {t('conn.serviceDown')}
      </span>
    {/if}

    <Button variant="ghost" size="icon-xs" onclick={() => { app.audioMuted = !app.audioMuted; saveSettings(); }}
            class={app.audioMuted ? 'opacity-40' : ''} title={app.audioMuted ? '取消静音' : '静音'}>
      {#if app.audioMuted}<VolumeOff size={14} />{:else}<Volume2 size={14} />{/if}
    </Button>
    <Button variant="ghost" size="icon-xs" onclick={toggleTheme} title={app.darkTheme ? '浅色主题' : '深色主题'}>
      {#if app.darkTheme}<Sun size={14} />{:else}<Moon size={14} />{/if}
    </Button>
    <Button variant="ghost" size="icon-xs" onclick={onSettings} title="设置">
      <Settings size={14} />
    </Button>
  </div>
</header>
