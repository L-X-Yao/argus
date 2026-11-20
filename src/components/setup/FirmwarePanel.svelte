<script lang="ts">
  import { app, showConfirm, addToast } from '../../lib/stores.svelte';
  import { dispatch } from '../../lib/transport';
  import { t } from '../../lib/i18n.svelte';
  import { apiUrl } from '../../lib/backend';
  import Button from '$lib/components/ui/button/button.svelte';
  import { Upload, RotateCw, HardDriveDownload, Zap } from '@lucide/svelte';

  let files: { name: string; size: number }[] = $state([]);
  let uploading = $state(false);

  interface FwVersion {
    version: string;
    date: string;
    url: string;
    size: number;
  }
  let onlineVersions: FwVersion[] = $state([]);
  let loadingOnline = $state(false);
  let showOnline = $state(false);

  let canFlash = $derived(
    !app.fwFlash.active &&
      !app.drone.armed &&
      app.wsConnected &&
      app.activeTransport !== 'serial' &&
      (app.drone.connected || app.fwFlash.phase === 'failed'),
  );
  let flashBlock = $derived.by(() => {
    if (app.fwFlash.active) return t('fw.flashBusy');
    if (app.drone.armed) return t('fw.armed');
    if (app.activeTransport === 'serial') return t('fw.notBackend');
    if (!app.wsConnected) return t('fw.noBackend');
    if (!app.drone.connected && app.fwFlash.phase !== 'failed') return t('fw.noLink');
    return '';
  });
  let flashPercent = $derived(
    app.fwFlash.total > 0 ? Math.min(100, Math.round((app.fwFlash.done / app.fwFlash.total) * 100)) : 0,
  );
  // Literal keys: the locale contract test sees a key only when it appears in the source.
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

  async function fetchOnlineVersions() {
    if (onlineVersions.length > 0) {
      showOnline = !showOnline;
      return;
    }
    loadingOnline = true;
    showOnline = true;
    try {
      const boardId = app.drone.board_id;
      const r = await fetch(apiUrl(`/api/firmware/online?board_id=${boardId}`));
      const data = await r.json();
      onlineVersions = data.versions || [];
      if (data.error) addToast(t('fw.fetchFailed'), 'error');
    } catch {
      addToast(t('fw.fetchFailed'), 'error');
    } finally {
      loadingOnline = false;
    }
  }

  async function downloadFirmware(fw: FwVersion) {
    addToast(`${t('fw.downloading')} ${fw.version}...`, 'info');
    try {
      const r = await fetch(apiUrl('/api/firmware/download'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: fw.url, filename: `firmware_${fw.version}.apj` }),
      });
      const data = await r.json();
      if (data.ok) {
        addToast(`${t('fw.downloaded')}: ${fw.version}`, 'success');
        await loadList();
      } else {
        addToast(data.error || t('fw.downloadFailed'), 'error');
      }
    } catch {
      addToast(t('fw.downloadFailed'), 'error');
    }
  }

  async function loadList() {
    try {
      const r = await fetch(apiUrl('/api/firmware/list'));
      const data = await r.json();
      files = data.files || [];
    } catch {}
  }

  async function uploadFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.apj';
    input.onchange = async () => {
      const f = input.files?.[0];
      if (!f) return;
      uploading = true;
      try {
        const form = new FormData();
        form.append('file', f);
        const r = await fetch(apiUrl('/api/firmware/upload'), { method: 'POST', body: form });
        const data = await r.json();
        if (data.ok) {
          addToast(`${t('fw.uploaded')}: ${data.filename} (${(data.size / 1024).toFixed(0)} KB)`, 'success');
          await loadList();
        } else {
          addToast(data.error || t('fw.uploadFailed'), 'error');
        }
      } catch (e) {
        addToast(t('fw.uploadFailed'), 'error');
      } finally {
        uploading = false;
      }
    };
    input.click();
  }

  async function flash(f: { name: string; size: number }) {
    const ok = await showConfirm(`${t('fw.flashConfirm')} ${f.name}. ${t('fw.flashWarn')}`, true);
    if (!ok) return;
    dispatch('firmware_flash', undefined, { file: f.name });
  }

  async function rebootBootloader() {
    if (await showConfirm(t('fw.reboot') + '?', true)) {
      dispatch('reboot_bootloader');
    }
  }

  async function rebootNormal() {
    if (await showConfirm(t('fw.rebootNormal') + '?', false)) {
      dispatch('reboot');
    }
  }

  $effect(() => {
    if (app.drone.connected) loadList();
  });
</script>

<div class="space-y-2">
  <div class="flex items-center gap-1.5 mb-2">
    <HardDriveDownload size={14} class="text-primary" />
    <span class="text-[11px] font-semibold text-primary uppercase tracking-wider">{t('fw.title')}</span>
  </div>
  <p class="text-[11px] text-muted-foreground/60">{t('fw.storeOnly')}</p>

  <div class="flex gap-2">
    <Button
      variant="outline"
      size="sm"
      class="gap-1 h-7 text-xs flex-1"
      onclick={uploadFile}
      disabled={uploading || app.fwFlash.active}
    >
      <Upload size={13} />{t('fw.upload')}
    </Button>
    <Button
      variant="outline"
      size="sm"
      class="gap-1 h-7 text-xs"
      onclick={fetchOnlineVersions}
      disabled={loadingOnline || app.fwFlash.active}
    >
      <HardDriveDownload size={13} />{loadingOnline ? '...' : t('fw.browse')}
    </Button>
  </div>

  {#if showOnline && onlineVersions.length > 0}
    <div class="space-y-1 max-h-32 overflow-y-auto border border-border rounded-lg p-1.5">
      <div class="text-[10px] text-muted-foreground/60 font-semibold">
        {t('fw.available')} ({onlineVersions.length})
      </div>
      {#each onlineVersions as fw}
        <div
          class="flex justify-between items-center text-xs text-muted-foreground px-1 py-0.5 hover:bg-muted/50 rounded"
        >
          <div class="flex-1 min-w-0">
            <span class="font-mono text-foreground">{fw.version}</span>
            <span class="text-[10px] ml-1">{fw.date}</span>
          </div>
          <Button variant="ghost" size="xs" class="text-[10px] shrink-0" onclick={() => downloadFirmware(fw)}>
            <HardDriveDownload size={11} />
          </Button>
        </div>
      {/each}
    </div>
  {:else if showOnline && !loadingOnline}
    <p class="text-[11px] text-muted-foreground/60 text-center py-1">{t('fw.noOnline')}</p>
  {/if}

  {#if files.length > 0}
    <div class="space-y-1 max-h-24 overflow-y-auto">
      {#each files as f}
        <div class="flex justify-between items-center gap-1.5 text-xs text-muted-foreground px-1">
          <span class="truncate">{f.name}</span>
          <span class="text-[10px] shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
          <Button
            variant="outline"
            size="xs"
            class="text-[10px] gap-0.5 shrink-0"
            onclick={() => flash(f)}
            disabled={!canFlash}
          >
            <Zap size={11} />{t('fw.flash')}
          </Button>
        </div>
      {/each}
    </div>
  {:else}
    <p class="text-[11px] text-muted-foreground/60 text-center py-1">{t('fw.noFiles')}</p>
  {/if}

  {#if flashBlock && !app.fwFlash.active}
    <p class="text-[10px] text-muted-foreground/60">{flashBlock}</p>
  {/if}

  {#if app.fwFlash.active || app.fwFlash.phase === 'done' || app.fwFlash.phase === 'failed'}
    <div class="mt-1 p-2 rounded-lg border border-border bg-muted/20 space-y-1">
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
        <Button
          variant="outline"
          size="xs"
          class="text-[10px] gap-0.5"
          onclick={() => flash({ name: app.fwFlash.file, size: 0 })}
          disabled={!canFlash}
        >
          <RotateCw size={11} />{t('fw.flashRetry')}
        </Button>
      {/if}
    </div>
  {/if}

  <div class="flex gap-2 pt-1">
    <Button
      variant="destructive"
      size="sm"
      class="gap-1 h-7 text-xs flex-1"
      onclick={rebootBootloader}
      disabled={!app.drone.connected || app.fwFlash.active}
    >
      <RotateCw size={13} />{t('fw.reboot')}
    </Button>
    <Button
      variant="outline"
      size="sm"
      class="gap-1 h-7 text-xs"
      onclick={rebootNormal}
      disabled={!app.drone.connected || app.fwFlash.active}
    >
      <RotateCw size={13} />{t('fw.rebootNormal')}
    </Button>
  </div>
</div>
