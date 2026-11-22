<script lang="ts">
  import { logState, startDownload, cancelDownload, MAX_LOG_SIZE } from '../../lib/logStore.svelte';
  import { sendCommand } from '../../lib/ws';
  import { isSerialConnected, serialLogList, serialLogDownload, serialLogCancel, dispatch } from '../../lib/transport';
  import { addToast, app, showConfirm } from '../../lib/stores.svelte';
  import { t } from '../../lib/i18n.svelte';
  import { apiUrl } from '../../lib/backend';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, RefreshCw } from '@lucide/svelte';

  function requestList() {
    if (isSerialConnected()) {
      serialLogList().then((res) => {
        if (!res.ok) addToast(`${t('log.fetchList')}: ${res.error}`, 'error', 4000);
      });
      return;
    }
    sendCommand('log_list');
  }

  function downloadLog(id: number, size: number) {
    if (isSerialConnected()) {
      // serialLogDownload calls startDownload internally; calling it twice
      // would clear _chunks mid-stream.
      serialLogDownload(id).then((res) => {
        if (!res.ok) addToast(`${t('log.download')}: ${res.error}`, 'error', 4000);
      });
      return;
    }
    if (size <= 0) return; // nothing to download; the FC keeps a zero-length entry after erase
    if (size > MAX_LOG_SIZE) {
      // The backend refuses this too; do not leave the panel's optimistic download state hanging.
      addToast(t('log.tooLarge'), 'error', 4000);
      return;
    }
    startDownload(id, size);
    sendCommand('log_download', undefined, { id });
  }

  function cancel() {
    if (isSerialConnected()) {
      serialLogCancel();
      return;
    }
    sendCommand('log_cancel');
    cancelDownload();
  }

  function fmtSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  function fmtDate(utc: number): string {
    if (utc === 0) return '---';
    const d = new Date(utc * 1000);
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  let { onclose }: { onclose: () => void } = $props();

  let tab = $state<'fc' | 'local'>('fc');

  interface LocalLog {
    name: string;
    size: number;
    mtime: number;
    active: boolean;
  }
  let localFiles = $state<LocalLog[]>([]);
  let localLoading = $state(false);
  let localDeleting = $state(false);
  let selectedLocal = $state<Record<string, boolean>>({});
  let localSelectedCount = $derived(localFiles.filter((f) => selectedLocal[f.name] && !f.active).length);

  async function loadLocal() {
    localLoading = true;
    try {
      const r = await fetch(apiUrl('/api/logs'));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      localFiles = data.files || [];
    } catch {
      addToast(t('log.localLoadFailed'), 'error');
    } finally {
      localLoading = false;
    }
  }

  function showLocal() {
    tab = 'local';
    void loadLocal();
  }

  function toggleLocal(name: string) {
    selectedLocal = { ...selectedLocal, [name]: !selectedLocal[name] };
  }

  function selectAllLocal() {
    const next: Record<string, boolean> = {};
    for (const f of localFiles) if (!f.active) next[f.name] = true;
    selectedLocal = next;
  }

  async function deleteLocal() {
    const names = localFiles.filter((f) => selectedLocal[f.name] && !f.active).map((f) => f.name);
    if (!names.length) return;
    const ok = await showConfirm(t('log.deleteConfirm').replace('{n}', String(names.length)), true);
    if (!ok) return;
    localDeleting = true;
    try {
      const r = await fetch(apiUrl('/api/logs/delete'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names }),
      });
      const data = await r.json();
      if (!data.ok) {
        addToast(data.error || t('log.deleteFailed'), 'error');
        return;
      }
      if (data.deleted.length) {
        addToast(
          t('log.deleted').replace('{n}', String(data.deleted.length)),
          data.refused.length ? 'warn' : 'success',
        );
      } else if (data.refused.length) {
        addToast(t('log.deleteRefused'), 'error');
      }
      selectedLocal = {};
      await loadLocal();
    } catch {
      addToast(t('log.deleteFailed'), 'error');
    } finally {
      localDeleting = false;
    }
  }

  async function eraseFcLogs() {
    const ok = await showConfirm(t('log.eraseConfirm'), true);
    if (!ok) return;
    dispatch('log_erase');
    // No "sent" toast: a refused command (armed, busy, no link) already surfaces its own
    // error, and the list refresh is the result of a successful one.
    setTimeout(requestList, 4000);
  }
</script>

<div
  role="dialog"
  aria-modal="true"
  aria-label={t('log.title')}
  tabindex="-1"
  class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
  onclick={(e) => {
    if (e.target === e.currentTarget) onclose();
  }}
  onkeydown={(e) => {
    if (e.key === 'Escape') onclose();
  }}
>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[520px] max-h-[80vh] flex flex-col overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('log.title')}</h2>
      <div class="flex items-center gap-2">
        {#if tab === 'fc'}
          <Button variant="default" size="sm" onclick={requestList} disabled={logState.downloading}>
            {t('log.fetchList')}
          </Button>
        {/if}
        <Button variant="ghost" size="icon-xs" onclick={onclose} aria-label={t('error.close')}><X size={16} /></Button>
      </div>
    </div>

    <div class="flex gap-1 px-4 pt-2 border-b border-border">
      <button
        class="px-3 py-1.5 text-xs font-semibold border-b-2 transition-colors
          {tab === 'fc' ? 'text-primary border-primary' : 'text-muted-foreground border-transparent'}"
        onclick={() => (tab = 'fc')}
      >
        {t('log.fcTab')}
      </button>
      <button
        class="px-3 py-1.5 text-xs font-semibold border-b-2 transition-colors
          {tab === 'local' ? 'text-primary border-primary' : 'text-muted-foreground border-transparent'}"
        onclick={showLocal}
      >
        {t('log.localTab')}
      </button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4">
      {#if tab === 'fc'}
        {#if logState.downloading}
          <div class="mb-3 p-3 bg-muted/50 rounded-lg">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs text-foreground">
                {t('log.downloading')}
                {logState.progress > 0 ? logState.progress + '%' : ''}{logState.downloadSpeed
                  ? ' | ' + logState.downloadSpeed
                  : ''}
              </span>
              <Button variant="destructive" size="xs" onclick={cancel}>{t('log.cancel')}</Button>
            </div>
            <div class="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                class="h-full bg-primary rounded-full transition-all duration-300"
                style="width:{logState.progress > 0 ? logState.progress : 5}%"
              ></div>
            </div>
          </div>
        {/if}

        {#if logState.list.length > 0}
          <div class="rounded-lg border border-border overflow-hidden">
            <div
              class="grid grid-cols-[60px_1fr_100px_80px] gap-2 px-3 py-2 bg-muted/50 text-[11px] text-muted-foreground font-semibold uppercase"
            >
              <span>{t('log.number')}</span>
              <span>{t('log.date')}</span>
              <span class="text-right">{t('log.size')}</span>
              <span class="text-center">{t('log.action')}</span>
            </div>
            {#each logState.list as log (log.id)}
              <div
                class="grid grid-cols-[60px_1fr_100px_80px] gap-2 px-3 py-1.5 items-center text-xs border-t border-border/50 hover:bg-muted/30 transition-colors"
              >
                <span class="font-mono font-bold">#{log.id}</span>
                <span class="text-muted-foreground font-mono">{fmtDate(log.time_utc)}</span>
                <span class="text-right font-mono">{fmtSize(log.size)}</span>
                <div class="text-center">
                  <Button
                    variant="outline"
                    size="xs"
                    disabled={logState.downloading || log.size === 0}
                    onclick={() => downloadLog(log.id, log.size)}
                  >
                    {t('log.download')}
                  </Button>
                </div>
              </div>
            {/each}
          </div>
          <div class="mt-2 text-center text-[10px] text-muted-foreground">
            {t('log.total').replace('{n}', String(logState.list.length))}
          </div>
        {:else if !logState.downloading}
          <div class="text-center py-8 text-muted-foreground text-sm">
            {t('log.hint')}
          </div>
        {/if}

        <div class="mt-3 flex justify-center">
          <Button
            variant="destructive"
            size="xs"
            onclick={eraseFcLogs}
            disabled={app.drone.armed || logState.downloading}
          >
            {t('log.eraseAll')}
          </Button>
        </div>
      {:else}
        <div class="space-y-2">
          <div class="flex items-center justify-between gap-2">
            <span class="text-[11px] text-muted-foreground">{t('log.localTitle')}</span>
            <div class="flex items-center gap-1">
              <Button
                variant="ghost"
                size="xs"
                class="text-[10px]"
                onclick={selectAllLocal}
                disabled={!localFiles.length || localLoading}
              >
                {t('log.selectAll')}
              </Button>
              <Button
                variant="destructive"
                size="xs"
                class="text-[10px]"
                onclick={deleteLocal}
                disabled={!localSelectedCount || localDeleting}
              >
                {t('log.deleteSelected')}
              </Button>
              <Button
                variant="ghost"
                size="icon-xs"
                onclick={loadLocal}
                disabled={localLoading}
                title={t('log.refresh')}
                aria-label={t('log.refresh')}
              >
                <RefreshCw size={12} />
              </Button>
            </div>
          </div>

          {#if localFiles.length > 0}
            <div class="rounded-lg border border-border overflow-hidden">
              {#each localFiles as f (f.name)}
                <label
                  class="flex items-center gap-2 px-3 py-1.5 text-xs border-t border-border/50 first:border-t-0 hover:bg-muted/30 transition-colors cursor-pointer"
                >
                  <input
                    type="checkbox"
                    class="w-3.5 h-3.5 rounded border-border accent-primary"
                    checked={!!selectedLocal[f.name]}
                    disabled={f.active}
                    onchange={() => toggleLocal(f.name)}
                  />
                  <span class="truncate flex-1 font-mono">{f.name}</span>
                  {#if f.active}<span class="text-[10px] text-success shrink-0">{t('log.recording')}</span>{/if}
                  <span class="font-mono text-[10px] text-muted-foreground shrink-0">{fmtSize(f.size)}</span>
                  <span class="font-mono text-[10px] text-muted-foreground shrink-0">{fmtDate(f.mtime)}</span>
                </label>
              {/each}
            </div>
            <p class="text-[10px] text-muted-foreground/60">{t('log.localNote')}</p>
          {:else}
            <p class="text-center py-6 text-xs text-muted-foreground">{t('log.localEmpty')}</p>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</div>
