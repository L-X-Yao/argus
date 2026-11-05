<script lang="ts">
  import { app, addToast, saveRally, showConfirm } from '../../lib/stores.svelte';
  import { dispatch, isSerialConnected, serialClearRally, serialUploadRally } from '../../lib/transport';
  import { t } from '../../lib/i18n.svelte';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';

  function removePoint(index: number) {
    app.rallyPoints = app.rallyPoints.filter((_, i) => i !== index);
    app.rallyUploaded = false;
    saveRally();
  }

  function clearLocal() {
    app.rallyPoints = [];
    app.rallyUploaded = false;
    app.drawingRally = false;
    saveRally();
  }

  function upload() {
    app.drawingRally = false;
    if (!isSerialConnected()) {
      dispatch('rally_upload', undefined, { points: app.rallyPoints }); // answered by a rally_ack event
      return;
    }
    serialUploadRally(app.rallyPoints).then((res) => {
      if (res.ok) {
        app.rallyUploaded = true;
        addToast(t('rally.uploaded').replace('{n}', String(app.rallyPoints.length)), 'success');
      } else {
        addToast(`${t('rally.upload')}: ${res.error}`, 'error', 5000);
      }
    });
  }

  // Separate from clearLocal, as with the fence: what is on the FC outlives this list.
  async function clearOnFc() {
    if (!(await showConfirm(t('rally.clearFc') + '?', true))) return;
    if (!isSerialConnected()) {
      dispatch('rally_clear'); // answered by a rally_clear event
      return;
    }
    const res = await serialClearRally();
    if (res.ok) {
      app.rallyUploaded = false;
      addToast(t('rally.clearFcDone'), 'success');
    } else {
      addToast(`${t('rally.clearFc')}: ${res.error}`, 'error', 5000);
    }
  }
</script>

<div class="bg-card border border-border rounded-xl p-3 mx-2 mb-2">
  <div class="flex items-center gap-2 mb-2">
    <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('rally.title')}</h2>
    {#if app.rallyPoints.length > 0}
      <Badge variant={app.rallyUploaded ? 'default' : 'outline'} class="text-[10px]">
        {app.rallyUploaded ? t('fence.uploaded') : t('fence.notUploaded')}
      </Badge>
    {/if}
  </div>

  {#each app.rallyPoints as point, i (i)}
    <div class="flex items-center gap-2 text-xs font-mono py-0.5">
      <span class="text-primary">R{i + 1}</span>
      <span class="flex-1 truncate">{point.lat.toFixed(5)}, {point.lon.toFixed(5)}</span>
      <span class="text-muted-foreground">{point.alt} m</span>
      <Button variant="ghost" size="icon-xs" onclick={() => removePoint(i)} aria-label={t('rally.clear')}>×</Button>
    </div>
  {/each}

  <div class="flex flex-wrap gap-1 mt-2">
    <Button
      variant={app.drawingRally ? 'default' : 'outline'}
      size="xs"
      onclick={() => (app.drawingRally = !app.drawingRally)}
    >
      {app.drawingRally ? t('fence.finish') : t('rally.add')}
    </Button>
    {#if app.rallyPoints.length > 0}
      <Button variant="default" size="xs" onclick={upload}>{t('rally.upload')}</Button>
      <Button variant="ghost" size="xs" onclick={clearLocal}>{t('rally.clear')}</Button>
    {/if}
  </div>
  <div class="text-[11px] text-muted-foreground mt-1">{t('rally.hint')}</div>

  {#if app.drone.connected && !app.drawingRally}
    <Button variant="destructive" size="xs" class="mt-2" onclick={clearOnFc}>{t('rally.clearFc')}</Button>
  {/if}
</div>
