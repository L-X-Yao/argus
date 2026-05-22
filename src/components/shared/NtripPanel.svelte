<script lang="ts">
  import { app, addToast } from '../../lib/stores.svelte';
  import { sendCommand } from '../../lib/ws';
  import { t } from '../../lib/i18n.svelte';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, Radio, Satellite } from '@lucide/svelte';

  let { onclose }: { onclose: () => void } = $props();

  let host = $state('rtk.ntrip.org.cn');
  let port = $state(8001);
  let mountpoint = $state('RTCM32_GGB');
  let username = $state('');
  let password = $state('');
  let connected = $state(false);
  let connecting = $state(false);
  let bytesInjected = $state(0);
  let rtkFixType = $derived(app.drone.gps_fix_raw);

  function rtkStatusLabel(): string {
    if (rtkFixType >= 6) return 'RTK Fixed';
    if (rtkFixType >= 5) return 'RTK Float';
    if (rtkFixType >= 4) return 'DGPS';
    if (rtkFixType >= 3) return '3D Fix';
    return 'No Fix';
  }

  function rtkStatusColor(): string {
    if (rtkFixType >= 6) return 'text-green-400';
    if (rtkFixType >= 5) return 'text-yellow-400';
    return 'text-muted-foreground';
  }

  async function toggleNtrip() {
    if (connected) {
      sendCommand('ntrip_stop');
      connected = false;
      addToast(t('ntrip.stopped'), 'info');
      return;
    }
    connecting = true;
    try {
      sendCommand('ntrip_start', undefined, {
        host, port, mountpoint, username, password,
      });
      connected = true;
      addToast(t('ntrip.started'), 'success');
    } catch {
      addToast(t('ntrip.failed'), 'error');
    } finally {
      connecting = false;
    }
  }

  function saveConfig() {
    try {
      localStorage.setItem('argus_ntrip', JSON.stringify({ host, port, mountpoint, username }));
    } catch {}
  }

  import { onMount } from 'svelte';
  onMount(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('argus_ntrip') || '{}');
      if (saved.host) host = saved.host;
      if (saved.port) port = saved.port;
      if (saved.mountpoint) mountpoint = saved.mountpoint;
      if (saved.username) username = saved.username;
    } catch {}
  });
</script>

<div role="presentation" class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
     onclick={(e) => { if (e.target === e.currentTarget) onclose(); }}>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[380px] flex flex-col overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <div class="flex items-center gap-2">
        <Satellite size={16} class="text-primary" />
        <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('ntrip.title')}</h2>
      </div>
      <Button variant="ghost" size="icon-xs" onclick={onclose} aria-label="Close"><X size={16} /></Button>
    </div>

    <div class="p-4 space-y-3">
      <!-- RTK Status -->
      <div class="flex items-center justify-between p-2 rounded-lg bg-muted/20 border border-border">
        <span class="text-xs text-muted-foreground">{t('ntrip.rtkStatus')}</span>
        <span class="text-xs font-bold {rtkStatusColor()}">{rtkStatusLabel()}</span>
      </div>

      <!-- Connection form -->
      <div class="space-y-2">
        <div class="flex gap-2">
          <input bind:value={host} placeholder="NTRIP Host" onchange={saveConfig}
                 class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground" />
          <input bind:value={port} type="number" placeholder="Port" onchange={saveConfig}
                 class="w-16 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground text-right" />
        </div>
        <input bind:value={mountpoint} placeholder="Mountpoint" onchange={saveConfig}
               class="w-full h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground" />
        <div class="flex gap-2">
          <input bind:value={username} placeholder={t('ntrip.username')} onchange={saveConfig}
                 class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground" />
          <input bind:value={password} type="password" placeholder={t('ntrip.password')}
                 class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground" />
        </div>
      </div>

      <Button variant={connected ? 'destructive' : 'default'} class="w-full gap-2"
              disabled={connecting} onclick={toggleNtrip}>
        <Radio size={14} />
        {connected ? t('ntrip.stop') : connecting ? t('ntrip.connecting') : t('ntrip.start')}
      </Button>

      {#if connected}
        <div class="text-center text-[11px] text-muted-foreground">
          RTCM → FC: {(bytesInjected / 1024).toFixed(1)} KB
        </div>
      {/if}

      <div class="text-[10px] text-muted-foreground/50 text-center">
        {t('ntrip.hint')}
      </div>
    </div>
  </div>
</div>
