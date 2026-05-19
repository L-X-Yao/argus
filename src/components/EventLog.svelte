<script lang="ts">
  import { app } from '../lib/stores.svelte';

  let logEl: HTMLDivElement;
  let filter = $state('');

  let filtered = $derived(
    filter ? app.events.filter(e => e.text.includes(filter) || e.time.includes(filter)) : app.events
  );

  function severity(text: string): string {
    if (text.includes('!!!') || text.includes('失控') || text.includes('碰撞') || text.includes('紧急'))
      return 'crit';
    if (text.includes('失败') || text.includes('异常') || text.includes('丢失') || text.includes('极低'))
      return 'err';
    if (text.includes('警告') || text.includes('低电') || text.includes('未校准') || text.includes('链路'))
      return 'warn';
    if (text.includes('成功') || text.includes('就绪') || text.includes('已连接') || text.includes('已解锁'))
      return 'ok';
    return '';
  }

  function exportLog() {
    if (!app.events.length) return;
    const lines = app.events.map(e => `${e.time}\t${e.text}`).join('\n');
    const blob = new Blob([lines], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '事件_' + new Date().toISOString().slice(0, 16).replace(':', '') + '.txt';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  $effect(() => {
    if (app.events.length && logEl) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  });
</script>

<div class="panel">
  <h2>
    事件日志
    <span class="actions">
      <button class="export-btn" onclick={exportLog} title="导出日志">导出</button>
      <input class="filter" placeholder="筛选..." bind:value={filter} />
    </span>
  </h2>
  <div bind:this={logEl} class="log">
    {#each filtered as ev}
      <div class="line {severity(ev.text)}"><span class="time">{ev.time}</span> {ev.text}</div>
    {:else}
      <div class="empty">暂无事件</div>
    {/each}
  </div>
</div>

<style>
  .panel { background:var(--bg-panel); border-radius:8px; padding:10px 15px; margin:0 10px 10px; }
  h2 { font-size:14px; color:var(--text-accent); margin:0 0 6px; text-transform:uppercase; letter-spacing:1px; display:flex; align-items:center; justify-content:space-between; }
  .actions { display:flex; align-items:center; gap:6px; }
  .export-btn { padding:1px 6px; background:none; border:1px solid var(--border-light); color:var(--text-dim); border-radius:3px; cursor:pointer; font-size:10px; }
  .export-btn:hover { color:var(--text-accent); border-color:var(--text-accent); }
  .filter { width:80px; padding:2px 5px; background:var(--bg-input); color:var(--text-main); border:1px solid var(--border-light); border-radius:3px; font-size:11px; }
  .log { background:var(--bg-log); border-radius:6px; padding:8px; height:100px; overflow-y:auto; font-size:12px; font-family:Consolas,monospace; }
  .line { padding:2px 4px; border-bottom:1px solid #222; border-radius:2px; }
  .line.crit { background:rgba(211,47,47,0.15); color:#ff5252; }
  .line.err { background:rgba(211,47,47,0.08); color:#ef9a9a; }
  .line.warn { color:#ffa726; }
  .line.ok { color:#69f0ae; }
  .time { color:#666; }
  .empty { color:var(--text-dim); }
</style>
