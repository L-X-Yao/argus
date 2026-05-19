<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import Button from '$lib/components/ui/button/button.svelte';

  function arm() { if (confirm('确认解锁电机？\n请确保周围无人员。')) sendCommand('arm'); }
  function disarm() { sendCommand('disarm'); }
  function rtl() { if (confirm('切换到返航模式？')) sendCommand('rtl'); }
  function forceDisarm() { if (confirm('强制锁定 — 电机立即停转！\n仅在已着陆时使用。继续？')) sendCommand('force_disarm'); }
  function pause() { sendCommand('mode', app.drone.vtype === '固定翼' ? 19 : 5); }
</script>

<div class="bg-card border-r border-border p-3 w-44 shrink-0 flex flex-col gap-2">
  {#if app.drone.armed}
    <div class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-orange-900/30 border border-orange-700/40">
      <span class="w-2 h-2 rounded-full bg-orange-500 animate-pulse"></span>
      <span class="text-[11px] font-bold text-orange-400">已解锁</span>
    </div>
    <Button size="sm" class="w-full bg-green-700 hover:bg-green-800 text-white font-bold" onclick={disarm}>锁定电机</Button>
  {:else}
    <Button size="sm" class="w-full bg-orange-700 hover:bg-orange-800 text-white font-bold" onclick={arm}>解锁电机</Button>
  {/if}
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
          onclick={() => { if (confirm(`确认起飞到 ${app.defaultAlt}m？`)) sendCommand('takeoff', undefined, { alt: app.defaultAlt }); }}>
    起飞 {app.defaultAlt}m
  </Button>
</div>
