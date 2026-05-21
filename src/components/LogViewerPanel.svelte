<script lang="ts">
  import { addToast } from '../lib/stores.svelte';
  import { t } from '../lib/i18n.svelte';
  import { parseDFLog, getTimeSeries, type DFLog } from '../lib/dflog';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, FileText, Download } from '@lucide/svelte';

  let { onclose, onlog }: { onclose: () => void; onlog?: (log: DFLog) => void } = $props();

  let log = $state<DFLog | null>(null);
  let parsing = $state(false);
  let selectedTypes = $state<Set<string>>(new Set());
  let canvasEl: HTMLCanvasElement = $state(null!);
  let fileName = $state('');

  function openFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.bin,.log';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      fileName = file.name;
      parsing = true;
      const reader = new FileReader();
      reader.onload = (ev: any) => {
        try {
          log = parseDFLog(ev.target.result);
          selectedTypes = new Set(['ATT', 'GPS', 'BARO', 'BAT', 'VIBE'].filter(t => log!.types.includes(t)));
          addToast(t('logview.messages').replace('{n}', String(log.messages.length)), 'success');
          onlog?.(log);
        } catch (err: any) {
          addToast('Parse error: ' + err.message, 'error');
        }
        parsing = false;
      };
      reader.readAsArrayBuffer(file);
    };
    input.click();
  }

  function toggleType(tp: string) {
    const s = new Set(selectedTypes);
    if (s.has(tp)) s.delete(tp); else s.add(tp);
    selectedTypes = s;
  }

  const CHANNEL_COLORS = ['#4fc3f7', '#81c784', '#ffb74d', '#e57373', '#ba68c8', '#4dd0e1', '#aed581', '#ff8a65'];

  $effect(() => {
    if (!canvasEl || !log || selectedTypes.size === 0) return;
    const ctx = canvasEl.getContext('2d')!;
    const w = canvasEl.width = canvasEl.parentElement!.clientWidth;
    const h = canvasEl.height;
    ctx.clearRect(0, 0, w, h);

    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = '#333';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = (i / 4) * h;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }

    let ci = 0;
    for (const tp of selectedTypes) {
      const fmt = log.formats.get(tp);
      if (!fmt) continue;
      const numCols = fmt.columns.filter(c => c !== 'TimeUS' && c !== 'TimeMS');
      const col = numCols[0];
      if (!col) continue;
      const series = getTimeSeries(log, tp, col);
      if (series.t.length < 2) continue;
      const minV = Math.min(...series.v);
      const maxV = Math.max(...series.v);
      const range = maxV - minV || 1;
      const maxT = series.t[series.t.length - 1];
      ctx.strokeStyle = CHANNEL_COLORS[ci % CHANNEL_COLORS.length];
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i < series.t.length; i++) {
        const x = (series.t[i] / maxT) * w;
        const y = h - ((series.v[i] - minV) / range) * (h - 20) - 10;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.fillStyle = CHANNEL_COLORS[ci % CHANNEL_COLORS.length];
      ctx.font = '10px monospace';
      ctx.fillText(`${tp}.${col}`, 4, 12 + ci * 14);
      ci++;
    }

    ctx.fillStyle = '#666';
    ctx.font = '9px monospace';
    if (log.duration > 0) {
      const dur = log.duration;
      for (let i = 0; i <= 5; i++) {
        const sec = (i / 5) * dur;
        const x = (i / 5) * w;
        ctx.fillText(`${sec.toFixed(0)}s`, x + 2, h - 2);
      }
    }
  });

  function exportCsv() {
    if (!log) return;
    const types = [...selectedTypes];
    let csv = 'time,' + types.join(',') + '\n';
    const series = types.map(tp => {
      const fmt = log!.formats.get(tp);
      const col = fmt?.columns.filter(c => c !== 'TimeUS' && c !== 'TimeMS')[0] || '';
      return getTimeSeries(log!, tp, col);
    });
    const maxLen = Math.max(...series.map(s => s.t.length));
    for (let i = 0; i < Math.min(maxLen, 10000); i++) {
      const row = [series[0]?.t[i]?.toFixed(3) || ''];
      for (const s of series) row.push(s.v[i]?.toFixed(4) || '');
      csv += row.join(',') + '\n';
    }
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = fileName.replace(/\.\w+$/, '') + '_export.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center" onclick={onclose}>
  <div class="bg-card border border-border rounded-2xl overflow-hidden w-[800px] max-h-[85vh] shadow-2xl flex flex-col" onclick={(e) => e.stopPropagation()}>
    <div class="bg-gradient-to-r from-primary/20 to-primary/5 px-5 py-3 flex items-center justify-between shrink-0">
      <div class="flex items-center gap-2">
        <FileText size={16} class="text-primary" />
        <h3 class="text-base font-bold text-primary">{t('logview.title')}</h3>
        {#if fileName}<span class="text-xs text-muted-foreground">{fileName}</span>{/if}
      </div>
      <div class="flex items-center gap-2">
        <Button variant="default" size="sm" onclick={openFile} disabled={parsing}>
          {parsing ? t('logview.parsing') : t('logview.open')}
        </Button>
        {#if log}
          <Button variant="outline" size="sm" onclick={exportCsv}><Download size={13} class="mr-1" />{t('logview.export')}</Button>
        {/if}
        <Button variant="ghost" size="icon-xs" onclick={onclose}><X size={16} /></Button>
      </div>
    </div>

    <div class="flex-1 overflow-auto px-5 py-3">
      {#if !log}
        <div class="text-center py-16 text-muted-foreground text-sm">{t('logview.noFile')}</div>
      {:else}
        <div class="flex items-center gap-2 mb-3 text-xs text-muted-foreground">
          <span>{t('logview.messages').replace('{n}', String(log.messages.length))}</span>
          <span>·</span>
          <span>{t('logview.duration')}: {log.duration.toFixed(0)}s</span>
          <span>·</span>
          <span>{log.types.length} {t('logview.channels').toLowerCase()}</span>
        </div>

        <div class="flex flex-wrap gap-1 mb-3">
          {#each log.types as tp}
            <button class="px-2 py-0.5 text-[10px] rounded border cursor-pointer transition-all
              {selectedTypes.has(tp) ? 'bg-primary text-primary-foreground border-primary' : 'text-muted-foreground border-border hover:text-foreground'}"
              onclick={() => toggleType(tp)}>{tp}</button>
          {/each}
        </div>

        <div class="border border-border rounded-lg overflow-hidden">
          <canvas bind:this={canvasEl} height="300" class="w-full"></canvas>
        </div>
      {/if}
    </div>
  </div>
</div>
