<script lang="ts">
  import { onMount } from 'svelte';
  import { apiUrl } from '../lib/backend';
  import { t } from '../lib/i18n.svelte';
  import { X, VideoOff, Camera } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let { onclose }: { onclose: () => void } = $props();

  let videoUrl = $state('');
  onMount(() => { try { videoUrl = localStorage.getItem('pllink_video_url') || ''; } catch {} });
  let streaming = $state(false);
  let size = $state<'sm' | 'md' | 'lg'>('md');
  let error = $state('');

  // --- dragging ---
  let dragging = $state(false);
  let posX = $state(16);  // offset from right
  let posY = $state(8);   // offset from top
  let dragStartX = 0;
  let dragStartY = 0;
  let origX = 0;
  let origY = 0;

  const sizeMap = {
    sm: { w: 320, h: 240, labelKey: 'video.sizeSmall' },
    md: { w: 480, h: 360, labelKey: 'video.sizeMedium' },
    lg: { w: 640, h: 480, labelKey: 'video.sizeLarge' },
  } as const;

  let imgSrc = $derived(
    streaming ? apiUrl(`/api/video?url=${encodeURIComponent(videoUrl)}`) : ''
  );

  function startStream() {
    if (!videoUrl.trim()) {
      error = t('video.urlRequired');
      return;
    }
    error = '';
    streaming = true;
    try { localStorage.setItem('pllink_video_url', videoUrl); } catch {}
  }

  async function stopStream() {
    streaming = false;
    try {
      await fetch(apiUrl('/api/video/stop'));
    } catch {}
  }

  function onDragStart(e: MouseEvent) {
    dragging = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    origX = posX;
    origY = posY;
    window.addEventListener('mousemove', onDragMove);
    window.addEventListener('mouseup', onDragEnd);
  }

  function onDragMove(e: MouseEvent) {
    if (!dragging) return;
    // posX is "right offset", so moving mouse right means decreasing posX
    posX = Math.max(0, origX - (e.clientX - dragStartX));
    posY = Math.max(0, origY + (e.clientY - dragStartY));
  }

  function onDragEnd() {
    dragging = false;
    window.removeEventListener('mousemove', onDragMove);
    window.removeEventListener('mouseup', onDragEnd);
  }

  let videoImg: HTMLImageElement | null = $state(null);

  function takeScreenshot() {
    if (!videoImg) return;
    const canvas = document.createElement('canvas');
    canvas.width = videoImg.naturalWidth || sizeMap[size].w;
    canvas.height = videoImg.naturalHeight || sizeMap[size].h;
    canvas.getContext('2d')!.drawImage(videoImg, 0, 0);
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = 'screenshot_' + new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19) + '.png';
    a.click();
  }

  function handleClose() {
    if (streaming) stopStream();
    onclose();
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="absolute z-[1003] flex flex-col bg-card/95 backdrop-blur border border-border
         rounded-xl shadow-2xl overflow-hidden select-none"
  style="right: {posX}px; top: {posY}px; width: {sizeMap[size].w}px;"
>
  <!-- Title bar (draggable) -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="flex items-center justify-between px-3 py-1.5 border-b border-border cursor-move bg-muted/50"
    onmousedown={onDragStart}
  >
    <span class="text-xs font-semibold text-foreground tracking-wide">{t('video.title')}</span>
    <div class="flex items-center gap-1">
      {#each (['sm', 'md', 'lg'] as const) as s}
        <button
          class="px-1.5 py-0.5 rounded text-[10px] font-semibold transition-all
            {size === s
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
          onclick={() => size = s}
        >
          {t(sizeMap[s].labelKey)}
        </button>
      {/each}
      <button class="ml-1 text-muted-foreground hover:text-foreground leading-none px-0.5"
              onclick={handleClose}>
        <X size={14} />
      </button>
    </div>
  </div>

  <!-- Video display -->
  <div
    class="relative bg-black flex items-center justify-center overflow-hidden"
    style="height: {sizeMap[size].h}px;"
  >
    {#if streaming && imgSrc}
      <img
        bind:this={videoImg}
        src={imgSrc}
        alt={t('video.alt')}
        class="w-full h-full object-contain"
        crossorigin="anonymous"
        onerror={() => { error = t('video.loadFail'); streaming = false; }}
      />
    {:else}
      <div class="flex flex-col items-center gap-2 text-muted-foreground">
        <VideoOff size={40} class="opacity-40" />
        <span class="text-xs">{t('video.noSource')}</span>
      </div>
    {/if}
  </div>

  <!-- Controls -->
  <div class="px-3 py-2 border-t border-border flex items-center gap-2">
    <input
      type="text"
      class="flex-1 h-7 px-2 text-xs rounded-md border border-border bg-background text-foreground
             placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
      placeholder={t('video.placeholder')}
      bind:value={videoUrl}
      disabled={streaming}
      onkeydown={(e) => { if (e.key === 'Enter') startStream(); }}
    />
    {#if streaming}
      <Button variant="ghost" size="icon-xs" onclick={takeScreenshot} title="Screenshot"><Camera size={14} /></Button>
      <Button variant="destructive" size="sm" onclick={stopStream}>{t('video.disconnect')}</Button>
    {:else}
      <Button size="sm" onclick={startStream}>{t('video.connect')}</Button>
    {/if}
  </div>

  {#if error}
    <div class="px-3 pb-2 text-[11px] text-destructive">{error}</div>
  {/if}
</div>
