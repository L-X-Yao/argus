<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let logEl: HTMLDivElement;
  let filter = $state('');

  let filtered = $derived(
    filter ? app.events.filter(e => e.text.includes(filter) || e.time.includes(filter)) : app.events
  );

  $effect(() => {
    if (app.events.length && logEl) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  });
</script>

<div class="panel">
  <h2>
    事件日志
    <input class="filter" placeholder="筛选..." bind:value={filter} />
  </h2>
  <div bind:this={logEl} class="log">
    {#each filtered as ev}
      <div class="line"><span class="time">{ev.time}</span> {ev.text}</div>
    {:else}
      <div class="empty">暂无事件</div>
    {/each}
  </div>
</div>

<style>
  .panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0 0 6px; text-transform:uppercase; letter-spacing:1px; display:flex; align-items:center; justify-content:space-between; }
  .filter { width:80px; padding:2px 5px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); border-radius:3px; font-size:11px; }
  .log { background:var(--bg-log); border-radius:6px; padding:8px; height:100px; overflow-y:auto; font-size:12px; font-family:Consolas,monospace; }
  .line { padding:2px 0; border-bottom:1px solid #222; }
  .time { color:#666; }
  .empty { color:var(--text-dim); }
</style>
