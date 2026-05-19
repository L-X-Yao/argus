<script lang="ts">
  import { app, dismissToast } from '../lib/stores.svelte';

  function toastClass(level: string): string {
    if (level === 'success') return 'bg-green-700 text-white';
    if (level === 'warn') return 'bg-amber-600 text-white';
    if (level === 'error') return 'bg-red-700 text-white';
    return 'bg-primary text-primary-foreground';
  }

  function toastIcon(level: string): string {
    if (level === 'success') return '✓';
    if (level === 'warn') return '⚠';
    if (level === 'error') return '✕';
    return 'ℹ';
  }
</script>

{#if app.toasts.length > 0}
  <div class="fixed top-16 right-5 z-[10000] flex flex-col gap-1.5 pointer-events-none">
    {#each app.toasts as t (t.id)}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="pointer-events-auto flex items-center gap-2 px-4 py-2 rounded-lg text-sm cursor-pointer
                  max-w-[350px] shadow-lg animate-in slide-in-from-right {toastClass(t.level)}"
           onclick={() => dismissToast(t.id)}>
        <span class="text-base shrink-0">{toastIcon(t.level)}</span>
        {t.text}
      </div>
    {/each}
  </div>
{/if}

<style>
  @keyframes slide-in-from-right {
    from { opacity: 0; transform: translateX(40px); }
    to { opacity: 1; transform: translateX(0); }
  }
  .animate-in { animation: slide-in-from-right 0.3s ease; }
</style>
