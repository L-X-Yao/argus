<script lang="ts">
  import { app, showConfirm, addToast } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import { t } from '../lib/i18n.svelte';
  import { apiUrl } from '../lib/backend';
  import Button from '$lib/components/ui/button/button.svelte';
  import { Upload, RotateCw, HardDriveDownload } from '@lucide/svelte';

  let files: { name: string; size: number }[] = $state([]);
  let uploading = $state(false);

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
          addToast(data.error || 'Upload failed', 'error');
        }
      } catch (e) {
        addToast('Upload failed', 'error');
      } finally {
        uploading = false;
      }
    };
    input.click();
  }

  async function rebootBootloader() {
    if (await showConfirm(t('fw.reboot') + '?', true)) {
      sendCommand('reboot_bootloader');
    }
  }

  async function rebootNormal() {
    if (await showConfirm(t('fw.rebootNormal') + '?', false)) {
      sendCommand('reboot');
    }
  }

  $effect(() => { if (app.drone.connected) loadList(); });
</script>

<div class="space-y-2">
  <div class="flex items-center gap-1.5 mb-2">
    <HardDriveDownload size={14} class="text-primary" />
    <span class="text-[11px] font-semibold text-primary uppercase tracking-wider">{t('fw.title')}</span>
  </div>

  <div class="flex gap-2">
    <Button variant="outline" size="sm" class="gap-1 h-7 text-xs flex-1" onclick={uploadFile} disabled={uploading}>
      <Upload size={13} />{t('fw.upload')}
    </Button>
  </div>

  {#if files.length > 0}
    <div class="space-y-1 max-h-24 overflow-y-auto">
      {#each files as f}
        <div class="flex justify-between items-center text-xs text-muted-foreground px-1">
          <span class="truncate">{f.name}</span>
          <span class="text-[10px] shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
        </div>
      {/each}
    </div>
  {:else}
    <p class="text-[11px] text-muted-foreground/60 text-center py-1">{t('fw.noFiles')}</p>
  {/if}

  <div class="flex gap-2 pt-1">
    <Button variant="destructive" size="sm" class="gap-1 h-7 text-xs flex-1"
            onclick={rebootBootloader} disabled={!app.drone.connected}>
      <RotateCw size={13} />{t('fw.reboot')}
    </Button>
    <Button variant="outline" size="sm" class="gap-1 h-7 text-xs"
            onclick={rebootNormal} disabled={!app.drone.connected}>
      <RotateCw size={13} />{t('fw.rebootNormal')}
    </Button>
  </div>
</div>
