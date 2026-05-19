<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import { API_BASE } from '../lib/backend';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';
  import { X } from '@lucide/svelte';

  let { onclose }: { onclose: () => void } = $props();

  type CalType = 'compass' | 'accel' | 'gyro' | 'level' | 'baro';

  const calTypes: { id: CalType; label: string; cmd: string }[] = [
    { id: 'compass', label: '罗盘', cmd: 'cal_compass' },
    { id: 'accel', label: '加速度计', cmd: 'cal_accel' },
    { id: 'gyro', label: '陀螺仪', cmd: 'cal_gyro' },
    { id: 'level', label: '水平', cmd: 'cal_level' },
    { id: 'baro', label: '气压计', cmd: 'cal_baro' },
  ];

  /* ── Accel orientation definitions ── */
  type AccelStep = 'level' | 'nose_up' | 'nose_down' | 'left' | 'right' | 'back';
  type StepStatus = 'pending' | 'active' | 'done';

  interface OrientDef {
    id: AccelStep;
    label: string;
    hint: string;
    img: string;
    keywords: string[];
  }

  const accelOrients: OrientDef[] = [
    { id: 'level',     label: '水平',     hint: '将飞机水平放置',       img: `${API_BASE}/images/cal/VehicleDown.png`,       keywords: ['level', 'Level', '水平'] },
    { id: 'nose_up',   label: '机头朝上', hint: '将飞机机头朝上竖立',   img: `${API_BASE}/images/cal/VehicleTailDown.png`,   keywords: ['nose up', 'Nose Up', 'UP', '机头朝上', 'nose-up'] },
    { id: 'nose_down', label: '机头朝下', hint: '将飞机机头朝下竖立',   img: `${API_BASE}/images/cal/VehicleNoseDown.png`,   keywords: ['nose down', 'Nose Down', 'DOWN', '机头朝下', 'nose-down'] },
    { id: 'left',      label: '左侧朝下', hint: '将飞机左侧朝下放置',   img: `${API_BASE}/images/cal/VehicleLeft.png`,       keywords: ['left', 'Left', '左侧'] },
    { id: 'right',     label: '右侧朝下', hint: '将飞机右侧朝下放置',   img: `${API_BASE}/images/cal/VehicleRight.png`,      keywords: ['right', 'Right', '右侧'] },
    { id: 'back',      label: '倒置',     hint: '将飞机翻转倒置放置',   img: `${API_BASE}/images/cal/VehicleUpsideDown.png`, keywords: ['back', 'Back', 'inverted', '倒置', '翻转'] },
  ];

  let selected = $state<CalType>('compass');
  let calibrating = $state(false);

  /* Accel step tracking */
  let accelSteps = $state<Record<AccelStep, StepStatus>>({
    level: 'pending', nose_up: 'pending', nose_down: 'pending',
    left: 'pending', right: 'pending', back: 'pending',
  });
  let accelActive = $state<AccelStep | null>(null);

  function resetAccelSteps() {
    accelSteps = {
      level: 'pending', nose_up: 'pending', nose_down: 'pending',
      left: 'pending', right: 'pending', back: 'pending',
    };
    accelActive = null;
  }

  /* Compass rotation tracking (0-100) */
  let compassProgress = $state(0);
  let compassMsgCount = $state(0);

  /* ── Event filtering ── */
  const calKeywords = ['校准', 'calibrat', 'Calibrat', 'cal ', 'Cal ', 'Gyro', 'Compass',
    'Accel', 'Baro', 'Level', 'Place vehicle', 'Place', 'Rotate', 'orientation',
    'complete', 'Complete', 'success', 'Success', '完成', '成功', '失败', 'FAILED',
    'progress', 'Progress'];

  let calEvents = $derived(
    app.events.filter(e => calKeywords.some(k => e.text.includes(k))).slice(-20)
  );

  /* Track last-seen event count to detect new events */
  let lastParsedCount = $state(0);

  /* Parse accel/compass progress from events */
  $effect(() => {
    if (!calibrating) return;
    const evts = calEvents;
    if (evts.length <= lastParsedCount) return;
    const newEvts = evts.slice(lastParsedCount);
    lastParsedCount = evts.length;

    for (const ev of newEvts) {
      const t = ev.text;

      if (selected === 'accel') {
        /* Detect "Place vehicle XXX" or orientation completion messages */
        const placeMatch = t.match(/Place\s+vehicle\s+(\w+)/i);
        if (placeMatch) {
          /* Mark previous active as done */
          if (accelActive && accelSteps[accelActive] === 'active') {
            accelSteps[accelActive] = 'done';
          }
          /* Find which orientation is requested */
          const word = placeMatch[1].toLowerCase();
          for (const o of accelOrients) {
            if (o.keywords.some(k => k.toLowerCase() === word || word.includes(k.toLowerCase()))) {
              accelSteps[o.id] = 'active';
              accelActive = o.id;
              break;
            }
          }
        }

        /* Detect Chinese orientation prompts */
        for (const o of accelOrients) {
          if (o.keywords.some(k => t.includes(k))) {
            if (t.includes('完成') || t.includes('complete') || t.includes('Complete') || t.includes('done') || t.includes('Done')) {
              accelSteps[o.id] = 'done';
              if (accelActive === o.id) accelActive = null;
            } else if (t.includes('Place') || t.includes('放置') || t.includes('请将')) {
              if (accelActive && accelActive !== o.id && accelSteps[accelActive] === 'active') {
                accelSteps[accelActive] = 'done';
              }
              accelSteps[o.id] = 'active';
              accelActive = o.id;
            }
          }
        }

        /* Detect overall calibration success/failure */
        if (t.includes('Accel') && (t.includes('success') || t.includes('成功') || t.includes('complete') || t.includes('done'))) {
          /* Mark all remaining as done */
          for (const o of accelOrients) {
            if (accelSteps[o.id] !== 'done') accelSteps[o.id] = 'done';
          }
          accelActive = null;
          calibrating = false;
        }
      }

      if (selected === 'compass') {
        if (t.includes('Compass') || t.includes('罗盘') || t.includes('Rotate') || t.includes('旋转') || t.includes('校准')) {
          compassMsgCount++;
          /* Estimate progress from message count; ArduPilot typically sends ~30+ messages during compass cal */
          compassProgress = Math.min(95, Math.round(compassMsgCount * 3));
        }
        if (t.includes('success') || t.includes('成功') || t.includes('complete') || t.includes('Complete')) {
          compassProgress = 100;
          calibrating = false;
        }
      }

      /* Gyro/Level/Baro: auto-detect completion */
      if ((selected === 'gyro' || selected === 'level' || selected === 'baro') &&
          (t.includes('success') || t.includes('成功') || t.includes('complete') || t.includes('Complete') || t.includes('done'))) {
        calibrating = false;
      }
      if (t.includes('FAILED') || t.includes('失败')) {
        calibrating = false;
      }
    }
  });

  function startCal() {
    const ct = calTypes.find(c => c.id === selected);
    if (!ct) return;
    calibrating = true;
    lastParsedCount = calEvents.length;
    if (selected === 'accel') resetAccelSteps();
    if (selected === 'compass') { compassProgress = 0; compassMsgCount = 0; }
    sendCommand(ct.cmd);
  }

  function cancelCal() {
    sendCommand('cal_cancel');
    calibrating = false;
    if (selected === 'accel') resetAccelSteps();
    if (selected === 'compass') { compassProgress = 0; compassMsgCount = 0; }
  }

  let accelDoneCount = $derived(
    accelOrients.filter(o => accelSteps[o.id] === 'done').length
  );
</script>

<style>
  @keyframes pulse-border {
    0%, 100% { border-color: hsl(211 100% 50% / 0.5); box-shadow: 0 0 0 0 hsl(211 100% 50% / 0.3); }
    50% { border-color: hsl(211 100% 50% / 1); box-shadow: 0 0 8px 2px hsl(211 100% 50% / 0.25); }
  }
  .cal-active-border {
    animation: pulse-border 1.5s ease-in-out infinite;
  }
  @keyframes spin-slow {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  .spin-slow {
    animation: spin-slow 3s linear infinite;
  }
  @keyframes gentle-pulse {
    0%, 100% { opacity: 0.6; }
    50% { opacity: 1; }
  }
  .gentle-pulse {
    animation: gentle-pulse 2s ease-in-out infinite;
  }
</style>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
     onclick={(e) => { if (e.target === e.currentTarget) onclose(); }}>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[560px] max-h-[85vh] flex flex-col overflow-hidden">

    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">传感器校准</h2>
      <Button variant="ghost" size="icon-xs" onclick={onclose}><X size={16} /></Button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4">

      <!-- Tab selector -->
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

      <!-- ════════════════════════════════════════════ -->
      <!-- ACCEL calibration panel                      -->
      <!-- ════════════════════════════════════════════ -->
      {#if selected === 'accel'}
        <div class="mb-4">
          <div class="flex items-center justify-between mb-2">
            <p class="text-xs font-semibold text-foreground">加速度计校准</p>
            {#if calibrating}
              <Badge variant="secondary" class="text-[10px]">进度 {accelDoneCount}/6</Badge>
            {/if}
          </div>
          <p class="text-[11px] text-muted-foreground mb-3">
            按提示依次将飞机放置在 6 个方向，每个方向保持静止直到提示完成。
          </p>

          <!-- 6-orientation grid -->
          <div class="grid grid-cols-3 gap-2 mb-3">
            {#each accelOrients as orient (orient.id)}
              {@const st = accelSteps[orient.id]}
              <div class="flex flex-col items-center p-2 rounded-lg border-2 transition-all
                {st === 'done'   ? 'border-green-500/60 bg-green-500/5' :
                 st === 'active' ? 'border-primary/60 bg-primary/5 cal-active-border' :
                                   'border-border/50 bg-muted/20'}">
                <div class="w-20 h-16 flex items-center justify-center mb-1 rounded-md overflow-hidden
                  {st === 'done' ? 'bg-green-900/30 ring-1 ring-green-500/40' : st === 'active' ? 'bg-primary/10 ring-1 ring-primary/40' : 'bg-muted/20'}">
                  <img src={orient.img} alt={orient.label}
                       class="w-full h-full object-contain transition-all
                         {st === 'done' ? '' : st === 'active' ? '' : 'opacity-40 grayscale'}" />
                </div>

                <!-- Label + status icon -->
                <span class="text-[11px] font-medium {st === 'done' ? 'text-green-400' : st === 'active' ? 'text-primary' : 'text-muted-foreground'}">
                  {orient.label}
                </span>
                <span class="text-[10px] mt-0.5
                  {st === 'done' ? 'text-green-500' : st === 'active' ? 'text-primary' : 'text-muted-foreground/50'}">
                  {st === 'done' ? '已完成' : st === 'active' ? '校准中...' : '待校准'}
                </span>
              </div>
            {/each}
          </div>

          <!-- Current step hint -->
          {#if calibrating && accelActive}
            {@const ao = accelOrients.find(o => o.id === accelActive)}
            {#if ao}
              <div class="p-2.5 rounded-lg bg-primary/10 border border-primary/20 mb-3">
                <p class="text-xs text-primary font-medium">{ao.hint}，保持静止</p>
              </div>
            {/if}
          {:else if !calibrating}
            <div class="p-2.5 rounded-lg bg-muted/50 border border-border/50 mb-3">
              <p class="text-[11px] text-muted-foreground">点击"开始校准"后，按飞控提示依次完成 6 个方向的放置。</p>
            </div>
          {/if}
        </div>

      <!-- ════════════════════════════════════════════ -->
      <!-- COMPASS calibration panel                    -->
      <!-- ════════════════════════════════════════════ -->
      {:else if selected === 'compass'}
        <div class="mb-4">
          <p class="text-xs font-semibold text-foreground mb-1">罗盘校准</p>
          <p class="text-[11px] text-muted-foreground mb-4">
            缓慢旋转飞机，尽量覆盖所有方向（约 60 秒）。
          </p>

          <!-- Circular progress indicator -->
          <div class="flex flex-col items-center mb-4">
            <div class="relative w-[120px] h-[120px]">
              <svg viewBox="0 0 120 120" class="w-full h-full">
                <!-- Background circle -->
                <circle cx="60" cy="60" r="50" fill="none" stroke="hsl(var(--border))" stroke-width="6" opacity="0.4"/>
                <!-- Progress arc -->
                {#if calibrating || compassProgress > 0}
                  <circle cx="60" cy="60" r="50" fill="none"
                          stroke="{compassProgress >= 100 ? '#22c55e' : 'hsl(211,100%,50%)'}"
                          stroke-width="6" stroke-linecap="round"
                          stroke-dasharray="{Math.PI * 100}"
                          stroke-dashoffset="{Math.PI * 100 * (1 - compassProgress / 100)}"
                          transform="rotate(-90, 60, 60)"
                          class="transition-all duration-500"/>
                {/if}
                <!-- Center drone icon -->
                <g transform="translate(60,60)">
                  <rect x="-6" y="-6" width="12" height="12" rx="1.5"
                        fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.7"/>
                  <line x1="-6" y1="-6" x2="-14" y2="-14" stroke="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" stroke-width="1.5" stroke-linecap="round"/>
                  <line x1="6" y1="-6" x2="14" y2="-14" stroke="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" stroke-width="1.5" stroke-linecap="round"/>
                  <line x1="-6" y1="6" x2="-14" y2="14" stroke="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" stroke-width="1.5" stroke-linecap="round"/>
                  <line x1="6" y1="6" x2="14" y2="14" stroke="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" stroke-width="1.5" stroke-linecap="round"/>
                  <circle cx="-14" cy="-14" r="3" fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.5"/>
                  <circle cx="14" cy="-14" r="3" fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.5"/>
                  <circle cx="-14" cy="14" r="3" fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.5"/>
                  <circle cx="14" cy="14" r="3" fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.5"/>
                </g>
                <!-- Rotation arrow (animated when calibrating) -->
                {#if calibrating}
                  <g class="spin-slow" style="transform-origin: 60px 60px;">
                    <path d="M60,6 A54,54 0 0,1 108,40" fill="none" stroke="hsl(211,100%,50%)" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
                    <polygon points="108,40 104,32 112,34" fill="hsl(211,100%,50%)" opacity="0.6"/>
                  </g>
                {/if}
              </svg>
              <!-- Percentage in center -->
              {#if calibrating || compassProgress > 0}
                <div class="absolute inset-0 flex items-center justify-center pt-8">
                  <span class="text-sm font-bold {compassProgress >= 100 ? 'text-green-400' : 'text-primary'}">
                    {compassProgress}%
                  </span>
                </div>
              {/if}
            </div>
            <p class="mt-2 text-[11px] text-muted-foreground">
              {#if !calibrating && compassProgress === 0}
                点击"开始校准"后缓慢旋转飞机
              {:else if calibrating}
                正在校准，请持续旋转飞机...
              {:else if compassProgress >= 100}
                罗盘校准完成
              {/if}
            </p>
          </div>
        </div>

      <!-- ════════════════════════════════════════════ -->
      <!-- GYRO / LEVEL / BARO - simple "keep still"   -->
      <!-- ════════════════════════════════════════════ -->
      {:else}
        {@const labels = {
          gyro:  { title: '陀螺仪校准', desc: '将飞机放在水平面上，保持完全静止。', icon: '陀' },
          level: { title: '水平校准',   desc: '将飞机放在水平面上，保持静止。',     icon: '平' },
          baro:  { title: '气压计校准', desc: '保持飞机静止，等待完成。',           icon: '气' },
        }}
        {@const info = labels[selected]}
        <div class="mb-4">
          <p class="text-xs font-semibold text-foreground mb-1">{info.title}</p>
          <p class="text-[11px] text-muted-foreground mb-4">{info.desc}</p>

          <div class="flex flex-col items-center mb-4">
            <!-- Pulsing keep-still indicator -->
            <div class="relative w-[100px] h-[100px] flex items-center justify-center">
              {#if calibrating}
                <div class="absolute inset-0 rounded-full border-2 border-primary/40 gentle-pulse"></div>
                <div class="absolute inset-2 rounded-full border-2 border-primary/25 gentle-pulse" style="animation-delay: 0.5s;"></div>
              {/if}
              <svg viewBox="0 0 60 60" class="w-[56px] h-[56px]">
                <!-- Simple flat drone -->
                <rect x="22" y="22" width="16" height="16" rx="2"
                      fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.8"/>
                <line x1="22" y1="22" x2="10" y2="10" stroke="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" stroke-width="2" stroke-linecap="round"/>
                <line x1="38" y1="22" x2="50" y2="10" stroke="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" stroke-width="2" stroke-linecap="round"/>
                <line x1="22" y1="38" x2="10" y2="50" stroke="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" stroke-width="2" stroke-linecap="round"/>
                <line x1="38" y1="38" x2="50" y2="50" stroke="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" stroke-width="2" stroke-linecap="round"/>
                <circle cx="10" cy="10" r="5" fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.6"/>
                <circle cx="50" cy="10" r="5" fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.6"/>
                <circle cx="10" cy="50" r="5" fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.6"/>
                <circle cx="50" cy="50" r="5" fill="{calibrating ? 'hsl(211,100%,50%)' : '#6b7280'}" opacity="0.6"/>
              </svg>
            </div>
            <p class="mt-3 text-[11px] {calibrating ? 'text-primary' : 'text-muted-foreground'}">
              {calibrating ? '校准中，请保持飞机静止...' : '点击"开始校准"，校准过程中请勿移动飞机'}
            </p>
          </div>
        </div>
      {/if}

      <!-- ════════════════════════════════════════════ -->
      <!-- Status messages (shared)                     -->
      <!-- ════════════════════════════════════════════ -->
      <div class="mb-4">
        <p class="text-[11px] text-muted-foreground font-semibold uppercase tracking-wider mb-1.5">校准消息</p>
        <div class="rounded-lg border border-border bg-muted/30 min-h-[60px] max-h-[120px] overflow-y-auto p-2">
          {#if calEvents.length > 0}
            {#each calEvents as ev (ev.time + ev.text)}
              <div class="flex items-start gap-2 py-0.5">
                <span class="text-[10px] text-muted-foreground font-mono shrink-0">{ev.time}</span>
                <span class="text-xs text-foreground">{ev.text}</span>
              </div>
            {/each}
          {:else}
            <p class="text-xs text-muted-foreground text-center py-3">暂无校准消息</p>
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
