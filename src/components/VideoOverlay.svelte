<script lang="ts">
  import { apiUrl } from '../lib/backend';
  import { X } from '@lucide/svelte';

  let { onclose }: { onclose: () => void } = $props();

  let videoUrl = $state('');
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
    sm: { w: 320, h: 240, label: '小' },
    md: { w: 480, h: 360, label: '中' },
    lg: { w: 640, h: 480, label: '大' },
  } as const;

  let imgSrc = $derived(
    streaming ? apiUrl(`/api/video?url=${encodeURIComponent(videoUrl)}`) : ''
  );

  function startStream() {
    if (!videoUrl.trim()) {
      error = '请输入视频流地址';
      return;
    }
    error = '';
    streaming = true;
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
    <span class="text-xs font-semibold text-foreground tracking-wide">视频监控</span>
    <div class="flex items-center gap-1">
      {#each (['sm', 'md', 'lg'] as const) as s}
        <button
          class="px-1.5 py-0.5 rounded text-[10px] font-semibold transition-all
            {size === s
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
          onclick={() => size = s}
        >
          {sizeMap[s].label}
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
        src={imgSrc}
        alt="视频流"
        class="w-full h-full object-contain"
        onerror={() => { error = '视频流加载失败'; streaming = false; }}
      />
    {:else}
      <div class="flex flex-col items-center gap-2 text-muted-foreground">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z" />
        </svg>
        <span class="text-xs">无视频源</span>
      </div>
    {/if}
  </div>

  <!-- Controls -->
  <div class="px-3 py-2 border-t border-border flex items-center gap-2">
    <input
      type="text"
      class="flex-1 h-7 px-2 text-xs rounded-md border border-border bg-background text-foreground
             placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
      placeholder="rtsp://地址"
      bind:value={videoUrl}
      disabled={streaming}
      onkeydown={(e) => { if (e.key === 'Enter') startStream(); }}
    />
    {#if streaming}
      <button
        class="h-7 px-3 rounded-md bg-destructive/80 text-destructive-foreground text-xs font-semibold
               hover:bg-destructive transition-all shrink-0"
        onclick={stopStream}
      >
        断开
      </button>
    {:else}
      <button
        class="h-7 px-3 rounded-md bg-primary text-primary-foreground text-xs font-semibold
               hover:bg-primary/80 transition-all shrink-0"
        onclick={startStream}
      >
        连接
      </button>
    {/if}
  </div>

  {#if error}
    <div class="px-3 pb-2 text-[11px] text-destructive">{error}</div>
  {/if}
</div>
