<script lang="ts">
  import { panels, PANEL_LOADERS } from '../../lib/panels.svelte';

  let loaded: Record<string, any> = $state({});

  $effect(() => {
    for (const id of panels._open) {
      if (!loaded[id] && PANEL_LOADERS[id]) {
        PANEL_LOADERS[id]().then(mod => {
          if (mod.default) {
            loaded = { ...loaded, [id]: mod.default };
          }
        });
      }
    }
  });
</script>

{#each [...panels._open] as id (id)}
  {#if loaded[id] && id !== 'shortcuts'}
    {@const Comp = loaded[id]}
    <Comp onclose={() => panels.close(id)} />
  {/if}
{/each}
