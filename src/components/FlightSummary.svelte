<script lang="ts">
  import type { FlightSummary } from '../lib/types';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X } from '@lucide/svelte';

  let { summary, onclose }: { summary: FlightSummary; onclose: () => void } = $props();

  function fmtTime(s: number): string {
    const m = Math.floor(s / 60), sec = s % 60;
    return `${m}:${sec < 10 ? '0' : ''}${sec}`;
  }
  function fmtDist(d: number): string {
    return d < 1000 ? d + 'm' : (d / 1000).toFixed(1) + 'km';
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 bg-black/70 backdrop-blur-sm z-[9999] flex items-center justify-center" onclick={onclose}>
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="bg-card border-2 border-primary rounded-xl p-6 min-w-[320px] shadow-2xl" onclick={(e) => e.stopPropagation()}>
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-bold text-primary">飞行摘要</h3>
      <Button variant="ghost" size="icon-xs" onclick={onclose}><X size={16} /></Button>
    </div>
    <div class="flex justify-between py-2 border-b border-border">
      <span class="text-muted-foreground">飞行时间</span>
      <span class="font-bold text-base">{fmtTime(summary.duration)}</span>
    </div>
    <div class="flex justify-between py-2 border-b border-border">
      <span class="text-muted-foreground">最大高度</span>
      <span class="font-bold text-base">{summary.max_alt} m</span>
    </div>
    <div class="flex justify-between py-2 border-b border-border">
      <span class="text-muted-foreground">最大速度</span>
      <span class="font-bold text-base">{summary.max_speed} m/s</span>
    </div>
    <div class="flex justify-between py-2 border-b border-border">
      <span class="text-muted-foreground">飞行距离</span>
      <span class="font-bold text-base">{fmtDist(summary.total_dist)}</span>
    </div>
    {#if summary.bat_used >= 0}
      <div class="flex justify-between py-2 border-b border-border">
        <span class="text-muted-foreground">电量消耗</span>
        <span class="font-bold text-base">{summary.bat_used}%</span>
      </div>
    {/if}
    <Button variant="secondary" class="w-full mt-4" onclick={onclose}>关闭</Button>
  </div>
</div>
