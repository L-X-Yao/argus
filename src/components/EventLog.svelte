<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let logEl: HTMLDivElement;
  let filter = $state('');

  let filtered = $derived(
    filter ? app.events.filter(e => e.text.includes(filter) || e.time.includes(filter)) : app.events
  );

  type SevLevel = 'critical' | 'error' | 'warn' | 'ok' | 'info';

  function severity(text: string): SevLevel {
    if (text.includes('!!!') || text.includes('失控') || text.includes('碰撞') || text.includes('紧急'))
      return 'critical';
    if (text.includes('失败') || text.includes('异常') || text.includes('丢失') || text.includes('极低'))
      return 'error';
    if (text.includes('警告') || text.includes('低电') || text.includes('未校准') || text.includes('链路'))
      return 'warn';
    if (text.includes('成功') || text.includes('就绪') || text.includes('已连接') || text.includes('已解锁'))
      return 'ok';
    return 'info';
  }

  const sevStyle: Record<SevLevel, string> = {
    critical: 'bg-destructive/15 text-destructive',
    error: 'bg-destructive/8 text-red-300',
    warn: 'text-warning',
    ok: 'text-success',
    info: '',
  };

  const sevDot: Record<SevLevel, string> = {
    critical: 'bg-red-500',
    error: 'bg-red-400',
    warn: 'bg-yellow-500',
    ok: 'bg-green-500',
    info: 'bg-muted-foreground/30',
  };

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

<div class="bg-card border-t border-border p-2">
  <div class="flex items-center justify-between mb-1.5">
    <h2 class="text-[11px] font-semibold text-primary uppercase tracking-wider">事件日志</h2>
    <div class="flex items-center gap-1.5">
      <Button variant="outline" size="xs" onclick={exportLog}>导出</Button>
      <input bind:value={filter} placeholder="筛选..."
             class="w-20 h-5 px-1.5 text-[11px] bg-input border border-border rounded text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring/50" />
    </div>
  </div>
  <div bind:this={logEl} class="bg-background rounded-lg p-2 h-24 overflow-y-auto text-xs font-mono">
    {#each filtered as ev}
      {@const sev = severity(ev.text)}
      <div class="flex items-start gap-1.5 py-0.5 px-1 border-b border-border/50 rounded {sevStyle[sev]}">
        <span class="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 {sevDot[sev]}"></span>
        <span class="text-muted-foreground shrink-0">{ev.time}</span>
        <span class="min-w-0">{ev.text}</span>
      </div>
    {:else}
      <div class="text-muted-foreground text-center py-3">暂无事件</div>
    {/each}
  </div>
</div>
