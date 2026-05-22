<script lang="ts">
  import { onMount } from 'svelte';
  import { app, saveSettings, isPlane, addToast } from '../../lib/stores.svelte';
  import { sendConnect, sendDisconnect, sendCommand } from '../../lib/ws';
  import { t } from '../../lib/i18n.svelte';
  import { apiUrl } from '../../lib/backend';
  import { webSerialAvailable, connectSerial, disconnectSerial, isSerialConnected } from '../../lib/transport';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';
  import { Volume2, VolumeOff, Sun, Moon, Settings, Satellite, Usb } from '@lucide/svelte';

  let { toggleTheme, onSettings }: { toggleTheme: () => void; onSettings: () => void } = $props();

  let port = $state('tcp:localhost:5770');
  let baud = $state(57600);
  let protocol = $state('auto');
  let portHistory: string[] = $state([]);
  let showHistory = $state(false);
  let connecting = $state(false);

  interface ConnProfile { name: string; port: string; baud: number; protocol: string; }
  let profiles: ConnProfile[] = $state([]);
  let showProfileSave = $state(false);
  let profileName = $state('');

  onMount(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('argus_port_history') || '[]');
      if (Array.isArray(saved)) portHistory = saved;
      const lastPort = localStorage.getItem('argus_last_port');
      if (lastPort) port = lastPort;
      const lastBaud = localStorage.getItem('argus_last_baud');
      if (lastBaud) baud = parseInt(lastBaud);
      const profs = JSON.parse(localStorage.getItem('argus_profiles') || '[]');
      if (Array.isArray(profs)) profiles = profs;
    } catch {}
    fetchPorts();
  });

  function saveProfile() {
    const name = profileName.trim() || port;
    profiles = [...profiles.filter(p => p.name !== name), { name, port, baud, protocol }];
    try { localStorage.setItem('argus_profiles', JSON.stringify(profiles)); } catch {}
    showProfileSave = false;
    profileName = '';
  }

  function loadProfile(p: ConnProfile) {
    port = p.port; baud = p.baud; protocol = p.protocol;
    showHistory = false;
  }

  function deleteProfile(name: string) {
    profiles = profiles.filter(p => p.name !== name);
    try { localStorage.setItem('argus_profiles', JSON.stringify(profiles)); } catch {}
  }

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
      localStorage.setItem('argus_port_history', JSON.stringify(portHistory));
      localStorage.setItem('argus_last_port', port);
      localStorage.setItem('argus_last_baud', String(baud));
    } catch {}
  }

  let connectTimeout = $state(false);
  let showVehicles = $state(false);

  let connectTimer: ReturnType<typeof setTimeout> | null = null;

  function toggle() {
    if (app.drone.connected) { sendDisconnect(); }
    else {
      connecting = true;
      connectTimeout = false;
      savePortHistory();
      sendConnect(port, baud, protocol);
      if (connectTimer) clearTimeout(connectTimer);
      connectTimer = setTimeout(() => {
        if (connecting && !app.drone.connected) {
          connectTimeout = true;
          connecting = false;
        }
        connectTimer = null;
      }, 8000);
    }
  }

  $effect(() => { if (app.drone.connected) { connecting = false; connectTimeout = false; if (connectTimer) { clearTimeout(connectTimer); connectTimer = null; } } });

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

  const EMERGENCY_MODE_IDS = new Set([6, 9, 11, 17, 20, 21]);
  const MANUAL_MODE_IDS_COPTER = new Set([0, 1, 13, 14]);
  const MANUAL_MODE_IDS_PLANE = new Set([0, 2, 4]);
  let modeVariant = $derived.by((): 'default' | 'secondary' | 'destructive' => {
    const m = app.drone.mode_id;
    if (EMERGENCY_MODE_IDS.has(m)) return 'destructive';
    const manualSet = isPlane() ? MANUAL_MODE_IDS_PLANE : MANUAL_MODE_IDS_COPTER;
    if (manualSet.has(m)) return 'secondary';
    return 'default';
  });

  let gpsOk = $derived(app.drone.gps_fix_raw >= 3);
  let gpsVariant = $derived.by((): 'default' | 'secondary' | 'destructive' => {
    if (app.drone.gps_fix_raw >= 6) return 'default';
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
    `${t('ekf.vel')}: ${app.drone.ekf_vel.toFixed(3)}\n${t('ekf.posH')}: ${app.drone.ekf_pos_h.toFixed(3)}\n${t('ekf.posV')}: ${app.drone.ekf_pos_v.toFixed(3)}\n${t('ekf.compass')}: ${app.drone.ekf_compass.toFixed(3)}\nFlags: 0x${app.drone.ekf_flags.toString(16).toUpperCase()}`
  );

  function fmtBatTime(s: number): string {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    return h > 0 ? `~${h}h${m}m` : `~${m}m`;
  }

  function downloadLog() { window.open(apiUrl('/api/log'), '_blank'); }

  let serialConnecting = $state(false);
  async function toggleSerial() {
    if (isSerialConnected()) {
      await disconnectSerial();
      addToast(t('conn.serialDisconnected'), 'info');
      return;
    }
    serialConnecting = true;
    try {
      const ok = await connectSerial(115200, {
        onHeartbeat: (msg) => {
          if (!app.drone.connected) {
            app.drone.connected = true;
            addToast(t('conn.serialConnected'), 'success');
          }
          app.drone.vtype_raw = msg.type;
          app.drone.armed = (msg.baseMode & 128) !== 0;
          app.drone.mode_id = msg.customMode;
        },
        onGlobalPositionInt: (msg) => {
          app.drone.lat = msg.lat;
          app.drone.lon = msg.lon;
          app.drone.alt_msl = msg.altMsl;
          app.drone.alt_rel = msg.altRel;
          app.drone.vz = -msg.vz;
          app.drone.hdg = msg.hdg;
        },
        onAttitude: (msg) => {
          app.drone.roll = msg.roll;
          app.drone.pitch = msg.pitch;
          app.drone.yaw = msg.yaw;
        },
        onSysStatus: (msg) => {
          app.drone.voltage = msg.voltage;
          app.drone.current = msg.current;
          app.drone.remaining = msg.remaining;
        },
        onGpsRawInt: (msg) => {
          app.drone.gps_fix_raw = msg.fixType;
          app.drone.gps_sats = msg.sats;
        },
        onVfrHud: (msg) => {
          app.drone.gs = msg.groundspeed;
        },
        onRcChannels: (msg) => {
          app.drone.rc = msg.channels;
          app.drone.rc_rssi = msg.rssi;
        },
        onVibration: (msg) => {
          app.drone.vibe = [msg.x, msg.y, msg.z];
          app.drone.vibe_clip = [msg.clip0, msg.clip1, msg.clip2];
        },
        onHomePosition: (msg) => {
          app.drone.home_lat = msg.lat;
          app.drone.home_lon = msg.lon;
        },
        onStatusText: (msg) => {
          app.events.push({ type: 'event', time: new Date().toLocaleTimeString(), text: msg.text, event_type: 'statustext' });
        },
      });
      if (!ok) addToast(t('conn.serialFailed'), 'error');
    } catch {
      addToast(t('conn.serialFailed'), 'error');
    } finally {
      serialConnecting = false;
    }
  }
</script>

<header class="flex items-center justify-between gap-3 px-3 max-sm:px-1.5 py-1.5 shrink-0 min-w-0 overflow-x-auto scrollbar-hide transition-colors duration-300
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
          {#if showHistory && (portHistory.length > 0 || profiles.length > 0)}
            <div class="absolute top-full left-0 right-0 z-[9999] mt-1 bg-popover border border-border rounded-md shadow-lg overflow-hidden min-w-[220px]">
              {#if profiles.length > 0}
                <div class="px-2 pt-1.5 pb-0.5 text-[9px] font-semibold text-muted-foreground/50 uppercase">{t('conn.profiles')}</div>
                {#each profiles as prof}
                  <div class="flex items-center group">
                    <button class="flex-1 text-left px-2 py-1.5 text-xs text-popover-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
                            onmousedown={() => loadProfile(prof)}>
                      <span class="font-semibold">{prof.name}</span>
                      <span class="text-[10px] text-muted-foreground ml-1 font-mono">{prof.port}</span>
                    </button>
                    <button class="px-1.5 opacity-0 group-hover:opacity-60 hover:!opacity-100 text-destructive transition-opacity"
                            onmousedown={() => deleteProfile(prof.name)} title="Delete">×</button>
                  </div>
                {/each}
                <div class="border-t border-border/50"></div>
              {/if}
              {#each portHistory as p}
                <button class="block w-full text-left px-2 py-1.5 text-xs font-mono text-popover-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
                        onmousedown={() => { port = p; showHistory = false; }}>{p}</button>
              {/each}
              <div class="border-t border-border/50">
                <button class="block w-full text-left px-2 py-1.5 text-[11px] text-primary hover:bg-accent transition-colors"
                        onmousedown={() => { showProfileSave = true; showHistory = false; }}>+ {t('conn.saveProfile')}</button>
              </div>
            </div>
          {/if}
          {#if showProfileSave}
            <div class="absolute top-full left-0 z-[9999] mt-1 bg-popover border border-border rounded-md shadow-lg p-2 flex gap-1">
              <input bind:value={profileName} placeholder={t('conn.profileName')}
                     class="w-28 h-6 px-1.5 text-xs bg-input border border-border rounded text-foreground" />
              <button class="px-2 h-6 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90"
                      onclick={saveProfile}>{t('conn.saveProfile')}</button>
              <button class="px-1.5 h-6 text-xs text-muted-foreground hover:text-foreground"
                      onclick={() => showProfileSave = false}>×</button>
            </div>
          {/if}
        </div>
        {#if !port.startsWith('tcp:') && !port.startsWith('udp:')}
          <select bind:value={baud}
                  class="h-7 px-1 text-xs bg-input border border-border rounded-md text-foreground cursor-pointer"
                  title={t('tip.baudRate')}>
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
                title={t('tip.sitl')}>SITL</Button>
        {#if webSerialAvailable()}
          <Button variant="outline" size="sm" class="text-[10px] px-2 gap-1 {serialConnecting ? 'animate-pulse' : ''} {isSerialConnected() ? 'border-success text-success' : 'opacity-60 hover:opacity-100'}"
                  onclick={toggleSerial}
                  title={t('conn.serialTitle')}>
            <Usb size={12} />USB
          </Button>
        {/if}
      {/if}
    </div>
  </div>

  <div class="flex items-center gap-2 text-xs">
    {#if app.drone.connected}
      <Badge variant={modeVariant} class="text-xs font-bold">{app.drone.mode}</Badge>
      {#if app.drone.armed}
        <Badge variant="destructive" class="text-[10px] font-bold animate-pulse">{t('status.armed')}</Badge>
      {/if}

      <span class="flex items-center gap-0.5" title="Link {app.drone.link_age >= 0 ? app.drone.link_age.toFixed(1) + 's' : '---'} · {msgRate} Hz">
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
      {#if app.drone.parse_errors > 0}
        <span class="text-[9px] text-destructive/70 font-mono" title={t('tip.parseErrors')}>E:{app.drone.parse_errors}</span>
      {/if}
      {#if app.drone.vehicles && app.drone.vehicles.length > 0}
        <button class="relative cursor-pointer bg-transparent border-none p-0"
                onclick={() => showVehicles = !showVehicles}>
          <Badge variant="outline" class="text-[9px] font-mono gap-0.5">
            +{app.drone.vehicles.length}
          </Badge>
        </button>
        {#if showVehicles}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div class="absolute top-full right-0 mt-1 bg-card border border-border rounded-lg shadow-xl p-2 z-50 min-w-[200px]"
               onclick={(e) => e.stopPropagation()}>
            {#each app.drone.vehicles as v}
              <div class="flex items-center gap-2 px-2 py-1 text-xs border-b border-border/50 last:border-0">
                <span class="font-mono font-bold text-primary">#{v.sysid}</span>
                <span class="{v.armed ? 'text-warning' : 'text-muted-foreground'}">{v.armed ? t('status.armed') : '---'}</span>
                <span class="text-muted-foreground ml-auto">{v.alt?.toFixed(0) || 0}m</span>
              </div>
            {/each}
          </div>
        {/if}
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
      <span class="text-destructive text-[10px] font-bold animate-pulse" title={t('conn.serviceDown')}>
        {t('conn.serviceDown')}
      </span>
    {/if}

    <Button variant="ghost" size="icon-xs" onclick={() => { app.audioMuted = !app.audioMuted; saveSettings(); }}
            class={app.audioMuted ? 'opacity-40' : ''} title={app.audioMuted ? 'Unmute' : 'Mute'}>
      {#if app.audioMuted}<VolumeOff size={14} />{:else}<Volume2 size={14} />{/if}
    </Button>
    <Button variant="ghost" size="icon-xs" onclick={toggleTheme} title={t('tip.theme')}>
      {#if app.darkTheme}<Sun size={14} />{:else}<Moon size={14} />{/if}
    </Button>
    <Button variant="ghost" size="icon-xs" onclick={onSettings} title={t('settings.title')}>
      <Settings size={14} />
    </Button>
  </div>
</header>
