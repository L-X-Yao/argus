<script lang="ts">
  import { panels, PANEL_LOADERS } from '../../lib/panels.svelte';

  let loaded: Record<string, any> = $state({});
  let errors: Record<string, string> = $state({});

  $effect(() => {
    for (const id of panels._open) {
      if (!loaded[id] && !errors[id] && PANEL_LOADERS[id]) {
        PANEL_LOADERS[id]().then(mod => {
          if (mod.default) {
            loaded = { ...loaded, [id]: mod.default };
          }
        }).catch(err => {
          errors = { ...errors, [id]: String(err?.message || 'Load failed') };
        });
      }
    }
  });

  function retry(id: string) {
    const { [id]: _, ...rest } = errors;
    errors = rest;
  }
</script>

{#each [...panels._open] as id (id)}
  {#if loaded[id] && id !== 'shortcuts'}
    {@const Comp = loaded[id]}
    <Comp onclose={() => panels.close(id)} />
  {:else if errors[id]}
    <div class="fixed top-20 right-4 z-50 p-4 bg-red-900/90 text-red-200 rounded-lg shadow-lg max-w-sm">
      <p class="font-semibold text-sm">Failed to load: {id}</p>
      <p class="text-xs mt-1 opacity-75">{errors[id]}</p>
      <div class="flex gap-2 mt-2">
        <button class="text-xs underline hover:text-white" onclick={() => retry(id)}>Retry</button>
        <button class="text-xs underline hover:text-white" onclick={() => panels.close(id)}>Close</button>
      </div>
    </div>
  {/if}
{/each}
