<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import Button from '$lib/components/ui/button/button.svelte';

  function rtl() { if (confirm('切换到返航模式？')) sendCommand('rtl'); }
  function forceDisarm() { if (confirm('强制锁定 — 电机立即停转！\n仅在已着陆时使用。继续？')) sendCommand('force_disarm'); }
  function pause() { sendCommand('mode', app.drone.vtype === '固定翼' ? 19 : 5); }
</script>

<div class="bg-card border border-border rounded-xl p-4 w-48 shrink-0 flex flex-col gap-2">
  <Button variant="destructive" size="lg" class="w-full text-lg font-bold bg-red-600 hover:bg-red-700" onclick={rtl}>
    !! 返航 !!
  </Button>
  <Button size="lg" class="w-full font-bold bg-amber-600 hover:bg-amber-700 text-white" onclick={pause}>
    悬停
  </Button>

  <div class="flex gap-1.5 mt-1">
    <Button size="sm" class="flex-1 bg-orange-700 hover:bg-orange-800 text-white" onclick={() => sendCommand('arm')}>解锁</Button>
    <Button size="sm" class="flex-1 bg-green-700 hover:bg-green-800 text-white" onclick={() => sendCommand('disarm')}>锁定</Button>
  </div>
  <Button variant="destructive" size="xs" class="w-full" onclick={forceDisarm}>强制锁定</Button>

  <div class="text-[11px] text-muted-foreground font-semibold mt-2 tracking-wide uppercase">模式</div>
  <div class="flex flex-col gap-1">
    {#each app.drone.mode_btns as [id, name]}
      <Button variant={app.drone.mode_id === id ? 'default' : 'secondary'} size="sm" class="w-full justify-start"
              onclick={() => sendCommand('mode', id)}>
        {name}
      </Button>
    {/each}
  </div>

  <div class="text-[11px] text-muted-foreground font-semibold mt-2 tracking-wide uppercase">载荷</div>
  <div class="flex gap-1.5">
    <Button size="sm" class="flex-1 bg-orange-700 hover:bg-orange-800 text-white font-bold" onclick={() => sendCommand('drop')}>投放</Button>
    <Button size="sm" variant="secondary" class="flex-1" onclick={() => sendCommand('drop_stop')}>停止</Button>
  </div>

  <div class="text-[11px] text-muted-foreground font-semibold mt-2 tracking-wide uppercase">任务</div>
  <div class="flex flex-col gap-1">
    <Button variant="outline" size="sm" class="w-full" onclick={() => sendCommand('mission_start')}>开始任务</Button>
    <Button variant="outline" size="sm" class="w-full" onclick={() => sendCommand('mission_download')}>下载任务</Button>
    <Button variant="outline" size="sm" class="w-full" onclick={() => sendCommand('mission_clear')}>清除任务</Button>
  </div>

  <div class="text-[11px] text-muted-foreground font-semibold mt-2 tracking-wide uppercase">起飞</div>
  <Button variant="outline" size="sm" class="w-full border-teal-600 text-teal-400 hover:bg-teal-900/30"
          onclick={() => sendCommand('takeoff', undefined, { alt: app.defaultAlt })}>
    起飞 {app.defaultAlt}m
  </Button>
</div>
