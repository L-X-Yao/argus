<script lang="ts">
  import { onMount } from 'svelte';
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();
  let error = $state<string | null>(null);

  onMount(() => {
    const handler = (e: ErrorEvent) => {
      error = `${e.message} (${e.filename}:${e.lineno})`;
    };
    const rejectionHandler = (e: PromiseRejectionEvent) => {
      error = `Unhandled: ${e.reason}`;
    };
    window.addEventListener('error', handler);
    window.addEventListener('unhandledrejection', rejectionHandler);
    return () => {
      window.removeEventListener('error', handler);
      window.removeEventListener('unhandledrejection', rejectionHandler);
    };
  });
</script>

{#if error}
  <div class="fixed inset-0 z-[99999] bg-black/80 flex items-center justify-center p-4">
    <div class="bg-card border border-destructive rounded-xl p-6 max-w-md text-center">
      <h2 class="text-lg font-bold text-destructive mb-2">Application Error</h2>
      <p class="text-sm text-muted-foreground mb-4 font-mono break-all">{error}</p>
      <button class="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-bold"
              onclick={() => error = null}>Dismiss</button>
      <button class="px-4 py-2 ml-2 bg-destructive text-white rounded-lg text-sm font-bold"
              onclick={() => window.location.reload()}>Reload</button>
    </div>
  </div>
{/if}

{@render children()}
