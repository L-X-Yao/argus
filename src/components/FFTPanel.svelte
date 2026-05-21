<script lang="ts">
  import { addToast } from '../lib/stores.svelte';
  import { t } from '../lib/i18n.svelte';
  import { parseDFLog, getTimeSeries, computeFFT, type DFLog } from '../lib/dflog';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, BarChart3 } from '@lucide/svelte';

  let { onclose }: { onclose: () => void } = $props();

  let log = $state<DFLog | null>(null);
  let source = $state('IMU.GyrX');
  let canvasEl: HTMLCanvasElement = $state(null!);
  let peakHz = $state(0);

  const SOURCES = [
    { key: 'IMU.GyrX', label: 'fft.gyroX' },
    { key: 'IMU.GyrY', label: 'fft.gyroY' },
    { key: 'IMU.GyrZ', label: 'fft.gyroZ' },
    { key: 'IMU.AccX', label: 'fft.accelX' },
    { key: 'IMU.AccY', label: 'fft.accelY' },
    { key: 'IMU.AccZ', label: 'fft.accelZ' },
  ];

  function openFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.bin,.log';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev: any) => {
        try {
          log = parseDFLog(ev.target.result);
          addToast(`FFT: ${log.messages.length} messages`, 'success');
        } catch (err: any) {
          addToast('Parse error: ' + err.message, 'error');
        }
      };
      reader.readAsArrayBuffer(file);
    };
    input.click();
  }

  $effect(() => {
    if (!canvasEl || !log) return;
    const [msgType, field] = source.split('.');
    const series = getTimeSeries(log, msgType, field);
    if (series.t.length < 64) return;

    const dt = series.t.length > 1 ? (series.t[series.t.length - 1] - series.t[0]) / (series.t.length - 1) : 0.001;
    const sampleRate = 1 / dt;
    const { freq, mag } = computeFFT(series.v, sampleRate);
    if (freq.length === 0) return;

    let maxIdx = 0;
    for (let i = 1; i < mag.length; i++) {
      if (mag[i] > mag[maxIdx]) maxIdx = i;
    }
    peakHz = freq[maxIdx];

    const ctx = canvasEl.getContext('2d')!;
    const w = canvasEl.width = canvasEl.parentElement!.clientWidth;
    const h = canvasEl.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#0d1117';
    ctx.fillRect(0, 0, w, h);

    const maxFreqDisplay = Math.min(500, freq[freq.length - 1]);
    const maxMag = Math.max(...mag) || 1;

    ctx.strokeStyle = '#333';
    ctx.lineWidth = 0.5;
    for (let f = 50; f <= maxFreqDisplay; f += 50) {
      const x = (f / maxFreqDisplay) * w;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      ctx.fillStyle = '#555';
      ctx.font = '9px monospace';
      ctx.fillText(`${f}`, x + 2, h - 2);
    }

    ctx.strokeStyle = '#4fc3f7';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i < freq.length && freq[i] <= maxFreqDisplay; i++) {
      const x = (freq[i] / maxFreqDisplay) * w;
      const y = h - (mag[i] / maxMag) * (h - 20) - 10;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    const peakX = (peakHz / maxFreqDisplay) * w;
    ctx.strokeStyle = '#f44336';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(peakX, 0); ctx.lineTo(peakX, h); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#f44336';
    ctx.font = 'bold 11px monospace';
    ctx.fillText(`${peakHz.toFixed(1)}Hz`, peakX + 4, 14);
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center" onclick={onclose}>
  <div class="bg-card border border-border rounded-2xl overflow-hidden w-[700px] max-h-[85vh] shadow-2xl flex flex-col" onclick={(e) => e.stopPropagation()}>
    <div class="bg-gradient-to-r from-primary/20 to-primary/5 px-5 py-3 flex items-center justify-between shrink-0">
      <div class="flex items-center gap-2">
        <BarChart3 size={16} class="text-primary" />
        <h3 class="text-base font-bold text-primary">{t('fft.title')}</h3>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="default" size="sm" onclick={openFile}>{t('logview.open')}</Button>
        <Button variant="ghost" size="icon-xs" onclick={onclose}><X size={16} /></Button>
      </div>
    </div>

    <div class="px-5 py-3 flex-1 overflow-auto">
      {#if !log}
        <div class="text-center py-16 text-muted-foreground text-sm">{t('fft.noData')}</div>
      {:else}
        <div class="flex items-center gap-2 mb-3">
          <span class="text-xs font-semibold text-muted-foreground">{t('fft.source')}:</span>
          {#each SOURCES as src}
            <button class="px-2 py-0.5 text-[10px] rounded border cursor-pointer transition-all
              {source === src.key ? 'bg-primary text-primary-foreground border-primary' : 'text-muted-foreground border-border hover:text-foreground'}"
              onclick={() => source = src.key}>{t(src.label)}</button>
          {/each}
        </div>

        <div class="border border-border rounded-lg overflow-hidden">
          <canvas bind:this={canvasEl} height="280" class="w-full"></canvas>
        </div>

        {#if peakHz > 0}
          <div class="mt-3 p-3 bg-warning/10 border border-warning/30 rounded-lg">
            <p class="text-xs font-bold text-warning">{t('fft.peak')}: {peakHz.toFixed(1)} Hz</p>
            <p class="text-[10px] text-muted-foreground mt-1">{t('fft.notchHint').replace('{hz}', peakHz.toFixed(0))}</p>
          </div>
        {/if}
      {/if}
    </div>
  </div>
</div>
