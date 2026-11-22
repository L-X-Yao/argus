<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { app } from '../../lib/stores.svelte';
  import { apiUrl } from '../../lib/backend';
  import { t } from '../../lib/i18n.svelte';
  import { wrapPi } from '../../lib/worst';
  import { X, VideoOff, Camera, Crosshair, RotateCcw } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let { onclose }: { onclose: () => void } = $props();
  let arEnabled = $state(false);
  let arCanvas: HTMLCanvasElement = $state(null!);
  let arFov = $state(70);
  let arGimbalPitch = $state(0);

  let videoUrl = $state('');
  onMount(() => {
    try {
      videoUrl = localStorage.getItem('argus_video_url') || '';
    } catch {}
  });
  let streaming = $state(false);
  let starting = $state(false);
  let preflight: AbortController | null = null;
  let size = $state<'sm' | 'md' | 'lg'>('md');
  let error = $state('');
  let ffmpegMissing = $state(false);
  onMount(() => {
    fetch(apiUrl('/api/video/capabilities'))
      .then((r) => r.json())
      .then((d) => {
        ffmpegMissing = d?.mjpeg === false;
      })
      .catch(() => {});
  });

  // --- dragging ---
  let dragging = $state(false);
  let posX = $state(16); // offset from right
  let posY = $state(8); // offset from top
  let dragStartX = 0;
  let dragStartY = 0;
  let origX = 0;
  let origY = 0;

  const sizeMap = {
    sm: { w: 320, h: 240, labelKey: 'video.sizeSmall' },
    md: { w: 480, h: 360, labelKey: 'video.sizeMedium' },
    lg: { w: 640, h: 480, labelKey: 'video.sizeLarge' },
  } as const;

  let imgSrc = $derived(streaming ? apiUrl(`/api/video?url=${encodeURIComponent(videoUrl)}`) : '');

  async function startStream() {
    if (starting) return;
    if (ffmpegMissing) {
      error = t('video.ffmpegMissing');
      return;
    }
    if (!videoUrl.trim()) {
      error = t('video.urlRequired');
      return;
    }
    error = '';
    starting = true;
    const url = videoUrl;
    const controller = new AbortController();
    preflight = controller;
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 10000);
    try {
      // Validate without opening a stream: a camera with one RTSP session must
      // see exactly one request, the <img> below.
      const response = await fetch(apiUrl(`/api/video/validate?url=${encodeURIComponent(url)}`), {
        signal: controller.signal,
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || data?.ok !== true) {
        const detail = typeof data?.error === 'string' ? data.error : `HTTP ${response.status}`;
        if (detail.startsWith('Invalid video URL:') || detail === 'No video URL provided') {
          error = `${t('video.invalidUrl')}: ${detail.replace(/^Invalid video URL:\s*/, '')}`;
        } else if (detail === 'ffmpeg not installed on server') {
          ffmpegMissing = true;
          error = t('video.ffmpegMissing');
        } else {
          error = `${t('video.loadFail')}: ${detail}`;
        }
        return;
      }
      streaming = true;
      try {
        localStorage.setItem('argus_video_url', url);
      } catch {}
    } catch (e) {
      if (timedOut) error = `${t('video.networkFail')}: timeout`;
      else if (!controller.signal.aborted) {
        error = `${t('video.networkFail')}: ${e instanceof Error ? e.message : String(e)}`;
      }
    } finally {
      clearTimeout(timeout);
      controller.abort();
      if (preflight === controller) preflight = null;
      starting = false;
    }
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

  function clampPosition() {
    posX = Math.min(Math.max(0, posX), Math.max(0, window.innerWidth - sizeMap[size].w));
    // Keep the title bar reachable even when the video itself is taller than the viewport.
    posY = Math.min(Math.max(0, posY), Math.max(0, window.innerHeight - 40));
  }

  function onDragMove(e: MouseEvent) {
    if (!dragging) return;
    // posX is "right offset", so moving mouse right means decreasing posX
    posX = origX - (e.clientX - dragStartX);
    posY = origY + (e.clientY - dragStartY);
    clampPosition();
  }

  function resetPosition() {
    posX = 16;
    posY = 8;
    clampPosition();
  }

  function onDragEnd() {
    dragging = false;
    window.removeEventListener('mousemove', onDragMove);
    window.removeEventListener('mouseup', onDragEnd);
  }

  $effect(() => {
    return () => {
      window.removeEventListener('mousemove', onDragMove);
      window.removeEventListener('mouseup', onDragEnd);
    };
  });

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
    preflight?.abort();
    if (streaming) stopStream();
    onclose();
  }

  onDestroy(() => preflight?.abort());

  $effect(() => {
    if (!arEnabled || !arCanvas || !streaming) return;
    const ctx = arCanvas.getContext('2d')!;
    const w = (arCanvas.width = sizeMap[size].w);
    const h = (arCanvas.height = sizeMap[size].h);
    // Clear before the prerequisites: a lost link or an empty route must not
    // leave the previous overlay drawn over the live picture.
    ctx.clearRect(0, 0, w, h);
    const d = app.drone;
    const wps = app.waypoints;
    if (!d.connected || d.lat === 0 || wps.length === 0) return;
    const hfov = (arFov * Math.PI) / 180;
    const vfov = hfov * (h / w);
    const yawRad = (d.yaw * Math.PI) / 180;
    const gimbalP = d.gimbal_pitch ?? arGimbalPitch;
    const pitchRad = ((d.pitch + gimbalP) * Math.PI) / 180;
    for (let i = 0; i < wps.length; i++) {
      const dlat = (wps[i].lat - d.lat) * 111320;
      const dlon = (wps[i].lon - d.lon) * 111320 * Math.cos((d.lat * Math.PI) / 180);
      const dist = Math.sqrt(dlat * dlat + dlon * dlon);
      if (dist < 1 || dist > 5000) continue;
      const bearing = Math.atan2(dlon, dlat);
      const relBearing = wrapPi(bearing - yawRad);
      if (!(Math.abs(relBearing) <= hfov / 2)) continue; // out of view, or no heading to tell
      const dalt = wps[i].alt - d.alt_rel;
      const elevAngle = Math.atan2(dalt, dist) - pitchRad;
      if (Math.abs(elevAngle) > vfov / 2) continue;
      const sx = w / 2 + (relBearing / (hfov / 2)) * (w / 2);
      const sy = h / 2 - (elevAngle / (vfov / 2)) * (h / 2);
      ctx.strokeStyle = '#4fc3f7';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(sx - 8, sy);
      ctx.lineTo(sx + 8, sy);
      ctx.moveTo(sx, sy - 8);
      ctx.lineTo(sx, sy + 8);
      ctx.stroke();
      ctx.fillStyle = '#4fc3f7';
      ctx.font = 'bold 10px monospace';
      ctx.fillText(`WP${i + 1}`, sx + 10, sy - 4);
      ctx.fillText(`${dist.toFixed(0)}m`, sx + 10, sy + 8);
    }
    if (d.home_lat !== 0) {
      const dlat = (d.home_lat - d.lat) * 111320;
      const dlon = (d.home_lon - d.lon) * 111320 * Math.cos((d.lat * Math.PI) / 180);
      const dist = Math.sqrt(dlat * dlat + dlon * dlon);
      const bearing = Math.atan2(dlon, dlat);
      const relBearing = wrapPi(bearing - yawRad);
      if (Math.abs(relBearing) <= hfov / 2) {
        const sx = w / 2 + (relBearing / (hfov / 2)) * (w / 2);
        ctx.fillStyle = '#f44336';
        ctx.beginPath();
        ctx.arc(sx, h - 20, 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.font = 'bold 9px monospace';
        ctx.fillText(`H ${dist.toFixed(0)}m`, sx + 8, h - 16);
      }
    }
  });
</script>

<div
  class="absolute z-[1003] flex flex-col bg-card/95 backdrop-blur border border-border
         rounded-xl shadow-2xl overflow-hidden select-none"
  style="right: {posX}px; top: {posY}px; width: {sizeMap[size].w}px;"
  role="region"
  aria-label={t('ui.video')}
>
  <!-- Title bar (draggable) -->
  <div
    class="flex items-center justify-between px-3 py-1.5 border-b border-border cursor-move bg-muted/50"
    role="toolbar"
    aria-label={t('ui.videoControls')}
    tabindex="0"
    onmousedown={onDragStart}
  >
    <span class="text-xs font-semibold text-foreground tracking-wide">{t('video.title')}</span>
    <div class="flex items-center gap-1">
      {#each ['sm', 'md', 'lg'] as const as s}
        <button
          class="px-1.5 py-0.5 rounded text-[10px] font-semibold transition-all
            {size === s
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted'}"
          onclick={() => (size = s)}
        >
          {t(sizeMap[s].labelKey)}
        </button>
      {/each}
      <button
        class="ml-1 text-muted-foreground hover:text-foreground leading-none px-0.5"
        onclick={resetPosition}
        title={t('video.resetPosition')}
        aria-label={t('video.resetPosition')}
      >
        <RotateCcw size={13} />
      </button>
      <button class="ml-1 text-muted-foreground hover:text-foreground leading-none px-0.5" onclick={handleClose}>
        <X size={14} />
      </button>
    </div>
  </div>

  <!-- Video display -->
  <div class="relative bg-black flex items-center justify-center overflow-hidden" style="height: {sizeMap[size].h}px;">
    {#if streaming && imgSrc}
      <img
        bind:this={videoImg}
        src={imgSrc}
        alt={t('video.alt')}
        class="w-full h-full object-contain"
        crossorigin="anonymous"
        onerror={() => {
          error = t('video.loadFail');
          streaming = false;
        }}
      />
      {#if arEnabled}
        <canvas bind:this={arCanvas} class="absolute inset-0 w-full h-full pointer-events-none"></canvas>
      {/if}
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
      disabled={streaming || starting}
      onkeydown={(e) => {
        if (e.key === 'Enter') startStream();
      }}
    />
    {#if streaming}
      <Button
        variant="ghost"
        size="icon-xs"
        onclick={takeScreenshot}
        title={t('tip.screenshot')}
        aria-label={t('tip.screenshot')}><Camera size={14} /></Button
      >
      <Button
        variant={arEnabled ? 'default' : 'ghost'}
        size="icon-xs"
        onclick={() => (arEnabled = !arEnabled)}
        title={t('ar.overlay')}
        aria-label={t('ar.overlay')}><Crosshair size={14} /></Button
      >
      {#if arEnabled}
        <input
          type="number"
          bind:value={arFov}
          min="30"
          max="120"
          step="5"
          title={t('label.fov')}
          class="w-10 h-5 px-1 text-[9px] text-center bg-input border border-border rounded font-mono"
        />
      {/if}
      <Button variant="destructive" size="sm" onclick={stopStream}>{t('video.disconnect')}</Button>
    {:else}
      <Button size="sm" onclick={startStream} disabled={starting}
        >{starting ? t('conn.connecting') : t('video.connect')}</Button
      >
    {/if}
  </div>

  {#if error}
    <div class="px-3 pb-2 text-[11px] text-destructive">{error}</div>
  {/if}
</div>
