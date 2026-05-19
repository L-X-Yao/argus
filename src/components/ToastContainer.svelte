<script lang="ts">
  import { app, dismissToast } from '../lib/stores.svelte';
</script>

{#if app.toasts.length > 0}
  <div class="toast-container">
    {#each app.toasts as t (t.id)}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="toast {t.level}" onclick={() => dismissToast(t.id)}>
        <span class="icon">
          {#if t.level === 'success'}✓{:else if t.level === 'warn'}⚠{:else if t.level === 'error'}✕{:else}ℹ{/if}
        </span>
        {t.text}
      </div>
    {/each}
  </div>
{/if}

<style>
  .toast-container { position:fixed; top:60px; right:20px; z-index:10000; display:flex; flex-direction:column; gap:6px; pointer-events:none; }
  .toast { pointer-events:auto; padding:8px 16px; border-radius:6px; font-size:13px; cursor:pointer; animation:slideIn 0.3s ease; display:flex; align-items:center; gap:8px; max-width:350px; box-shadow:0 4px 12px rgba(0,0,0,0.4); }
  .icon { font-size:16px; flex-shrink:0; }
  .info { background:#1565c0; color:white; }
  .warn { background:#f57f17; color:white; }
  .error { background:#d32f2f; color:white; }
  .success { background:#2e7d32; color:white; }
  @keyframes slideIn { from { opacity:0; transform:translateX(40px); } to { opacity:1; transform:translateX(0); } }
</style>
