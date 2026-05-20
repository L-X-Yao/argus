<script lang="ts">
  import { confirmState, resolveConfirm } from '../lib/stores.svelte';
  import { t } from '../lib/i18n.svelte';
  import Button from '$lib/components/ui/button/button.svelte';
  import { AlertTriangle } from '@lucide/svelte';

  function onKey(e: KeyboardEvent) {
    if (!confirmState.visible) return;
    if (e.key === 'Enter') { e.preventDefault(); resolveConfirm(true); }
    if (e.key === 'Escape') resolveConfirm(false);
  }
</script>

<svelte:window onkeydown={onKey} />

{#if confirmState.visible}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm"
       onclick={() => resolveConfirm(false)}>
    <div class="bg-card border border-border rounded-xl shadow-2xl p-5 w-[360px] max-w-[90vw]"
         onclick={(e) => e.stopPropagation()}>
      <div class="flex items-start gap-3 mb-4">
        {#if confirmState.danger}
          <div class="shrink-0 w-9 h-9 rounded-full bg-destructive/15 flex items-center justify-center">
            <AlertTriangle size={18} class="text-destructive" />
          </div>
        {/if}
        <p class="text-sm text-foreground whitespace-pre-line leading-relaxed pt-1.5">{confirmState.message}</p>
      </div>
      <div class="flex justify-end gap-2">
        <Button variant="outline" size="sm" onclick={() => resolveConfirm(false)}>{t('map.cancel')}</Button>
        <Button variant={confirmState.danger ? 'destructive' : 'default'} size="sm"
                onclick={() => resolveConfirm(true)}>{t('summary.confirm')}</Button>
      </div>
    </div>
  </div>
{/if}
