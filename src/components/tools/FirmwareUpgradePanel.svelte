<script lang="ts">
  import { onMount } from 'svelte';
  import { app, addToast, showConfirm } from '../../lib/stores.svelte';
  import { dispatch, disconnectSerial } from '../../lib/transport';
  import { sendConnect, sendDisconnect } from '../../lib/ws';
  import { t } from '../../lib/i18n.svelte';
  import { apiUrl } from '../../lib/backend';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, Upload, Zap, RefreshCw, Plug, Unplug, Check } from '@lucide/svelte';

  let { onclose }: { onclose: () => void } = $props();

  interface FwFile {
    name: string;
    size: number;
  }

  let files = $state<FwFile[]>([]);
  let selected = $state('');
  let info = $state<{ board_id: number; image_size: number } | null>(null);
  let infoError = $state('');
  let ports = $state<string[]>([]);
  let port = $state('');
  let uploading = $state(false);
  let loadingPorts = $state(false);
  let dragOver = $state(false);

  const PHASE_KEYS: Record<string, string> = {
    reboot: 'fw.phase.reboot',
    waiting: 'fw.phase.waiting',
    erase: 'fw.phase.erase',
    write: 'fw.phase.write',
    verify: 'fw.phase.verify',
    reconnecting: 'fw.phase.reconnecting',
    done: 'fw.phase.done',
    failed: 'fw.phase.failed',
  };
  let flashPhase = $derived(app.fwFlash.phase ? t(PHASE_KEYS[app.fwFlash.phase] || app.fwFlash.phase) : '');
  let flashPercent = $derived(
    app.fwFlash.total > 0 ? Math.min(100, Math.round((app.fwFlash.done / app.fwFlash.total) * 100)) : 0,
  );
  let usbActive = $derived(app.activeTransport === 'serial');
  let backendLinked = $derived(app.activeTransport === 'ws' && app.drone.connected);
  let canFlash = $derived(
    !!selected && info !== null && !app.fwFlash.active && !app.drone.armed && app.wsConnected && !usbActive,
  );
  let flashHint = $derived.by(() => {
    if (app.fwFlash.active) return t('fw.flashBusy');
    if (usbActive) return t('fw.notBackend');
    if (!app.wsConnected) return t('fw.noBackend');
    if (app.drone.armed) return t('fw.armed');
    if (!selected) return t('fw.noFileSelected');
    if (!info) return t('fw.infoFailed');
    return '';
  });

  async function loadFiles() {
    try {
      const r = await fetch(apiUrl('/api/firmware/list'));
      const data = await r.json();
      files = data.files || [];
      if (selected && !files.some((f) => f.name === selected)) {
        selected = '';
        info = null;
      }
    } catch {
      addToast(t('fw.fetchFailed'), 'error');
    }
  }

  async function loadPorts() {
    loadingPorts = true;
    try {
      const r = await fetch(apiUrl('/api/ports'));
      const data = await r.json();
      ports = data.ports || [];
      if (!port || !ports.includes(port)) port = ports[0] || '';
    } catch {
      ports = [];
    } finally {
      loadingPorts = false;
    }
  }

  async function selectFile(name: string) {
    selected = name;
    info = null;
    infoError = '';
    if (!name) return;
    try {
      const r = await fetch(apiUrl(`/api/firmware/info?name=${encodeURIComponent(name)}`));
      const data = await r.json();
      if (data.ok) info = { board_id: data.board_id, image_size: data.image_size };
      else infoError = data.error || t('fw.infoFailed');
    } catch {
      infoError = t('fw.infoFailed');
    }
  }

  async function upload(file: File) {
    if (uploading) return;
    if (!file.name.toLowerCase().endsWith('.apj')) {
      addToast(t('fw.uploadFailed'), 'error');
      return;
    }
    uploading = true;
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await fetch(apiUrl('/api/firmware/upload'), { method: 'POST', body: form });
      const data = await r.json();
      if (!data.ok) {
        addToast(data.error || t('fw.uploadFailed'), 'error');
        return;
      }
      addToast(`${t('fw.uploaded')}: ${data.filename}`, 'success');
      await loadFiles();
      await selectFile(data.filename);
    } catch {
      addToast(t('fw.uploadFailed'), 'error');
    } finally {
      uploading = false;
    }
  }

  function pickFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.apj';
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) void upload(file);
    };
    input.click();
  }

  function drop(e: DragEvent) {
    e.preventDefault();
    dragOver = false;
    const file = e.dataTransfer?.files?.[0];
    if (file) void upload(file);
  }

  function connectBackend() {
    if (!port || usbActive) return;
    sendConnect(port, 57600);
    addToast(`${t('fw.connectSent')}: ${port}`, 'info');
  }

  async function disconnectUsb() {
    await disconnectSerial();
  }

  async function flash() {
    if (!canFlash) return;
    const ok = await showConfirm(`${t('fw.flashConfirm')} ${selected}. ${t('fw.flashWarn')}`, true);
    if (ok) dispatch('firmware_flash', undefined, { file: selected });
  }

  onMount(() => {
    void loadFiles();
    void loadPorts();
  });
</script>

<div
  role="dialog"
  aria-modal="true"
  tabindex="-1"
  class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
  onclick={(e) => {
    if (e.target === e.currentTarget) onclose();
  }}
  onkeydown={(e) => {
    if (e.key === 'Escape') onclose();
  }}
>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[640px] max-h-[85vh] flex flex-col overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('fw.upgradeTitle')}</h2>
      <button
        class="text-muted-foreground hover:text-foreground transition-colors"
        onclick={onclose}
        title={t('error.close')}
        aria-label={t('error.close')}
      >
        <X size={16} />
      </button>
    </div>

    <div class="p-4 overflow-y-auto space-y-4">
      <section class="space-y-2">
        <h3 class="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">{t('fw.stepFile')}</h3>
        <div
          role="button"
          tabindex="0"
          class="border border-dashed rounded-lg p-3 text-center transition-colors {dragOver
            ? 'border-primary bg-primary/10'
            : 'border-border hover:border-primary/60'}"
          ondragover={(e) => {
            e.preventDefault();
            dragOver = true;
          }}
          ondragleave={() => (dragOver = false)}
          ondrop={drop}
          onclick={pickFile}
          onkeydown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') pickFile();
          }}
        >
          <div class="flex items-center justify-center gap-2 text-xs text-muted-foreground">
            <Upload size={14} />
            <span>{t('fw.dropHint')}</span>
            <span class="text-primary underline">{t('fw.pickFile')}</span>
          </div>
          {#if uploading}<p class="text-[10px] text-muted-foreground mt-1">{t('fw.uploading')}</p>{/if}
        </div>

        {#if files.length > 0}
          <div class="max-h-32 overflow-y-auto border border-border rounded-lg p-1 space-y-0.5">
            {#each files as f (f.name)}
              <button
                class="w-full flex items-center justify-between gap-2 text-xs px-2 py-1 rounded transition-colors
                  {selected === f.name ? 'bg-primary/15 text-foreground' : 'text-muted-foreground hover:bg-muted/50'}"
                onclick={() => selectFile(f.name)}
              >
                <span class="truncate">{f.name}</span>
                <span class="flex items-center gap-1.5 shrink-0">
                  <span class="text-[10px]">{(f.size / 1024).toFixed(0)} KB</span>
                  {#if selected === f.name}<Check size={12} class="text-primary" />{/if}
                </span>
              </button>
            {/each}
          </div>
        {:else}
          <p class="text-[11px] text-muted-foreground/60 text-center py-1">{t('fw.noFiles')}</p>
        {/if}

        {#if info}
          <p class="text-[11px] text-muted-foreground">
            {t('fw.apjInfo')
              .replace('{board}', String(info.board_id))
              .replace('{size}', String(Math.round(info.image_size / 1024)))}
          </p>
          {#if app.drone.board_id > 0}
            <p class="text-[10px] text-muted-foreground/60">
              {t('fw.fcBoard').replace('{board}', String(app.drone.board_id))} · {t('fw.boardNote')}
            </p>
          {/if}
        {:else if infoError}
          <p class="text-[11px] text-destructive">{infoError}</p>
        {/if}
      </section>

      <section class="space-y-2">
        <h3 class="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">{t('fw.stepConnect')}</h3>
        {#if usbActive}
          <p class="text-[11px] text-amber-500">{t('fw.notBackend')}</p>
          <Button variant="outline" size="sm" class="gap-1 h-7 text-xs" onclick={disconnectUsb}>
            <Unplug size={12} />{t('fw.disconnectUsb')}
          </Button>
        {:else if backendLinked}
          <div class="flex items-center justify-between gap-2">
            <p class="text-[11px] text-success">{t('fw.backendLinked')}</p>
            <Button variant="ghost" size="xs" class="text-[10px] gap-1" onclick={() => sendDisconnect()}>
              <Unplug size={11} />{t('conn.disconnect')}
            </Button>
          </div>
        {:else}
          <p class="text-[11px] text-muted-foreground">{t('fw.backendNotLinked')}</p>
          <div class="flex items-center gap-2">
            <select
              bind:value={port}
              class="flex-1 h-7 text-xs rounded-md border border-border bg-background px-2 text-foreground"
              disabled={loadingPorts || ports.length === 0}
              aria-label={t('fw.portLabel')}
            >
              {#each ports as p (p)}<option value={p}>{p}</option>{/each}
            </select>
            <Button
              variant="outline"
              size="sm"
              class="gap-1 h-7 text-xs"
              onclick={connectBackend}
              disabled={!port || loadingPorts}
            >
              <Plug size={12} />{t('fw.connectPort')}
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              onclick={loadPorts}
              disabled={loadingPorts}
              title={t('fw.refreshPorts')}
              aria-label={t('fw.refreshPorts')}
            >
              <RefreshCw size={12} />
            </Button>
          </div>
          {#if !ports.length && !loadingPorts}
            <p class="text-[10px] text-muted-foreground/60">{t('fw.noPorts')}</p>
          {/if}
        {/if}
      </section>

      <section class="space-y-2">
        <h3 class="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">{t('fw.stepFlash')}</h3>
        <Button variant="destructive" size="sm" class="gap-1 h-8 text-xs" onclick={flash} disabled={!canFlash}>
          <Zap size={13} />{t('fw.flash')}
        </Button>
        {#if flashHint}<p class="text-[10px] text-muted-foreground/60">{flashHint}</p>{/if}

        {#if app.fwFlash.active || app.fwFlash.phase === 'done' || app.fwFlash.phase === 'failed'}
          <div class="p-2 rounded-lg border border-border bg-muted/20 space-y-1">
            <div class="flex items-center justify-between gap-2 text-[11px]">
              <span class="font-semibold text-foreground">{flashPhase}</span>
              <span class="truncate text-muted-foreground">{app.fwFlash.file}</span>
            </div>
            {#if app.fwFlash.total > 0}
              <div class="h-1.5 rounded bg-muted overflow-hidden">
                <div class="h-full bg-primary transition-all" style="width: {flashPercent}%"></div>
              </div>
            {/if}
            {#if app.fwFlash.phase === 'failed' && app.fwFlash.error}
              <p class="text-[10px] text-destructive break-words">{app.fwFlash.error}</p>
            {/if}
            {#if app.fwFlash.phase === 'failed' && app.fwFlash.file}
              <Button variant="outline" size="xs" class="text-[10px] gap-0.5" onclick={flash} disabled={!canFlash}>
                <RefreshCw size={11} />{t('fw.flashRetry')}
              </Button>
            {/if}
          </div>
        {/if}
      </section>
    </div>
  </div>
</div>
