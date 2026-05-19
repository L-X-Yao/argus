<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';

  let { onclose }: { onclose: () => void } = $props();

  type CalType = 'compass' | 'accel' | 'gyro' | 'level' | 'baro';

  const calTypes: { id: CalType; label: string; cmd: string; desc: string }[] = [
    { id: 'compass', label: '罗盘', cmd: 'cal_compass', desc: '缓慢旋转飞机，覆盖所有方向（约 60 秒）' },
    { id: 'accel', label: '加速计', cmd: 'cal_accel', desc: '按提示将飞机放置在 6 个方向（水平、左侧、右侧、机头朝下、机头朝上、倒置）' },
    { id: 'gyro', label: '陀螺仪', cmd: 'cal_gyro', desc: '将飞机放在平面上，保持完全静止' },
    { id: 'level', label: '水平', cmd: 'cal_level', desc: '将飞机放在水平面上，保持静止' },
    { id: 'baro', label: '气压计', cmd: 'cal_baro', desc: '保持飞机静止，等待完成' },
  ];

  let selected = $state<CalType>('compass');
  let calibrating = $state(false);

  const calKeywords = ['校准', 'calibrat', 'Calibrat', 'cal ', 'Cal ', 'Gyro', 'Compass', 'Accel', 'Baro', 'Level', 'Place vehicle', 'Rotate'];

  let calEvents = $derived(
    app.events.filter(e => calKeywords.some(k => e.text.includes(k))).slice(-20)
  );

  function startCal() {
    const ct = calTypes.find(c => c.id === selected);
    if (!ct) return;
    calibrating = true;
    sendCommand(ct.cmd);
  }

  function cancelCal() {
    sendCommand('cal_cancel');
    calibrating = false;
  }

  function selInfo(): typeof calTypes[0] {
    return calTypes.find(c => c.id === selected)!;
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
     onclick={(e) => { if (e.target === e.currentTarget) onclose(); }}>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[520px] max-h-[80vh] flex flex-col overflow-hidden">
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">传感器校准</h2>
      <button class="text-muted-foreground hover:text-foreground text-lg leading-none px-1"
              onclick={onclose}>&times;</button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4">
      <!-- Calibration type selector -->
      <div class="flex flex-wrap gap-1.5 mb-4">
        {#each calTypes as ct (ct.id)}
          <button
            class="px-3 py-1.5 text-xs font-semibold rounded-md transition-all
              {selected === ct.id
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'bg-secondary text-secondary-foreground hover:bg-muted'}"
            onclick={() => { selected = ct.id; }}
          >
            {ct.label}
          </button>
        {/each}
      </div>

      <!-- Description -->
      <div class="p-3 mb-4 rounded-lg bg-muted/50 border border-border/50">
        <p class="text-xs text-foreground font-medium mb-1">{selInfo().label}校准</p>
        <p class="text-xs text-muted-foreground">{selInfo().desc}</p>
      </div>

      <!-- Status messages -->
      <div class="mb-4">
        <p class="text-[11px] text-muted-foreground font-semibold uppercase tracking-wider mb-1.5">校准消息</p>
        <div class="rounded-lg border border-border bg-muted/30 min-h-[80px] max-h-[160px] overflow-y-auto p-2">
          {#if calEvents.length > 0}
            {#each calEvents as ev (ev.time + ev.text)}
              <div class="flex items-start gap-2 py-0.5">
                <span class="text-[10px] text-muted-foreground font-mono shrink-0">{ev.time}</span>
                <span class="text-xs text-foreground">{ev.text}</span>
              </div>
            {/each}
          {:else}
            <p class="text-xs text-muted-foreground text-center py-4">暂无校准消息</p>
          {/if}
        </div>
      </div>

      <!-- Calibrating indicator -->
      {#if calibrating}
        <div class="mb-4 flex items-center gap-2 p-2 rounded-lg bg-primary/10 border border-primary/20">
          <div class="w-3 h-3 rounded-full bg-primary animate-pulse shrink-0"></div>
          <span class="text-xs text-primary font-medium">校准进行中...</span>
        </div>
      {/if}

      <!-- Action buttons -->
      <div class="flex gap-2">
        <Button variant="default" class="flex-1"
                onclick={startCal}
                disabled={calibrating || !app.drone.connected}>
          开始校准
        </Button>
        <Button variant="secondary" class="flex-1"
                onclick={cancelCal}
                disabled={!calibrating}>
          取消
        </Button>
      </div>

      {#if !app.drone.connected}
        <p class="mt-2 text-center text-[11px] text-muted-foreground">请先连接飞控</p>
      {/if}
    </div>
  </div>
</div>
