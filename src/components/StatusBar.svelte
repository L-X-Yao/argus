<script lang="ts">
  import { onMount } from 'svelte';
  import { app, saveSettings } from '../lib/stores.svelte';
  import { sendConnect, sendDisconnect, sendCommand } from '../lib/ws';
  import { apiUrl } from '../lib/backend';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';
  import { Volume2, VolumeOff, Sun, Moon, Settings, Wifi, WifiOff, Signal } from '@lucide/svelte';

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
      const r = await fetch(apiUrl('/api/ports'));
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

  let linkColor = $derived(
    !app.drone.connected || app.drone.link_age < 0 ? 'text-muted-foreground' :
    app.drone.link_age < 1 ? 'text-success' :
    app.drone.link_age < 3 ? 'text-warning' : 'text-destructive'
  );

  let battColor = $derived(
    app.drone.remaining < 20 ? 'text-destructive' :
    app.drone.remaining < 40 ? 'text-warning' : 'text-success'
  );

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
    ekfLevel === 'red' ? '导航异常' :
    ekfLevel === 'yellow' ? '导航警告' : '导航'
  );

  let ekfTooltip = $derived(
    `速度: ${app.drone.ekf_vel.toFixed(3)}\n水平: ${app.drone.ekf_pos_h.toFixed(3)}\n垂直: ${app.drone.ekf_pos_v.toFixed(3)}\n罗盘: ${app.drone.ekf_compass.toFixed(3)}\n标志: 0x${app.drone.ekf_flags.toString(16).toUpperCase()}`
  );

  function downloadLog() { window.open(apiUrl('/api/log'), '_blank'); }
</script>

<header class="flex items-center justify-between gap-3 px-3 py-1.5 bg-card border-b-2 border-border shrink-0">
  <div class="flex items-center gap-2">
    <span class="text-sm font-bold text-primary tracking-wider">PL-Link</span>

    <div class="flex items-center gap-1.5">
      {#if !app.drone.connected}
        <div class="relative">
          <input bind:value={port} placeholder="tcp:ip:port"
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
        <select bind:value={baud}
                class="h-7 px-1 text-xs bg-input border border-border rounded-md text-foreground cursor-pointer">
          <option value={57600}>57600</option>
          <option value={115200}>115200</option>
        </select>
      {/if}
      <Button
        variant={app.drone.connected ? 'destructive' : 'default'}
        size="sm"
        disabled={connecting && !app.drone.connected}
        onclick={toggle}
        class={connecting ? 'animate-pulse' : ''}
      >
        {app.drone.connected ? '断开' : connecting ? '连接中...' : '连接'}
      </Button>
    </div>
  </div>

  <div class="flex items-center gap-2 text-xs">
    {#if app.drone.connected}
      <Badge variant="default" class="text-xs font-bold">{app.drone.mode}</Badge>

      <span class="{linkColor}" title="链路 {app.drone.link_age >= 0 ? app.drone.link_age.toFixed(1) + 's' : ''}">
        {#if app.drone.link_age >= 0 && app.drone.link_age < 3}
          <Signal size={14} />
        {:else}
          <WifiOff size={14} />
        {/if}
      </span>

      <Badge variant="outline" class="font-mono text-[11px]">GPS {app.drone.gps_fix} {app.drone.gps_sats}</Badge>

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

      <span class="{battColor} font-bold tabular-nums">
        {app.drone.voltage.toFixed(1)}V {app.drone.remaining >= 0 ? app.drone.remaining + '%' : ''}
      </span>

      {#if app.drone.fw_version}
        <span class="text-muted-foreground text-[10px]">{app.drone.fw_version}</span>
      {/if}

      {#if app.drone.log_active}
        <Button variant="outline" size="xs" onclick={downloadLog} class="text-success border-success/50">日志</Button>
      {/if}
    {:else}
      <span class="text-muted-foreground">未连接</span>
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
