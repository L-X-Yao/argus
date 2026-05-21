<script lang="ts">
  import { app, addToast } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import { t } from '../lib/i18n.svelte';
  import { paramState } from '../lib/paramStore.svelte';
  import { X, Sliders } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let { onclose }: { onclose: () => void } = $props();

  /* ── Helpers ── */

  function getParam(name: string, fallback: number): number {
    const p = paramState.list.find(p => p.name === name);
    return p !== undefined ? p.value : fallback;
  }

  let paramsAvailable = $derived(paramState.list.length > 0);

  /* ── Axis definitions ── */

  type Axis = 'roll' | 'pitch' | 'yaw';

  const axes: { id: Axis; labelKey: string }[] = [
    { id: 'roll',  labelKey: 'pid.roll' },
    { id: 'pitch', labelKey: 'pid.pitch' },
    { id: 'yaw',   labelKey: 'pid.yaw' },
  ];

  const paramPrefix: Record<Axis, string> = {
    roll:  'ATC_RAT_RLL',
    pitch: 'ATC_RAT_PIT',
    yaw:   'ATC_RAT_YAW',
  };

  interface PidSliderDef {
    suffix: string;
    labelKey: string;
    min: number;
    max: number;
    step: number;
  }

  const pidSliders: PidSliderDef[] = [
    { suffix: '_P', labelKey: 'pid.rateP', min: 0, max: 0.5,  step: 0.001 },
    { suffix: '_I', labelKey: 'pid.rateI', min: 0, max: 0.5,  step: 0.001 },
    { suffix: '_D', labelKey: 'pid.rateD', min: 0, max: 0.05, step: 0.0001 },
  ];

  /* ── State ── */

  let activeTab = $state<Axis>('roll');

  /* PID values keyed by full param name */
  let values = $state<Record<string, number>>({});

  /* ── Load from paramState on mount ── */

  $effect(() => {
    if (!paramsAvailable) return;
    const v: Record<string, number> = {};
    for (const axis of axes) {
      for (const s of pidSliders) {
        const name = paramPrefix[axis.id] + s.suffix;
        v[name] = getParam(name, 0);
      }
    }
    values = v;
  });

  /* ── Slider change handler — sends param_set immediately ── */

  function onSliderChange(paramName: string, newVal: number) {
    values[paramName] = newVal;
    sendCommand('param_set', undefined, { name: paramName, value: newVal });
  }

  /* ── Input field change handler (typed value) ── */

  function onInputChange(paramName: string, raw: string, slider: PidSliderDef) {
    const val = parseFloat(raw);
    if (isNaN(val)) return;
    const clamped = Math.max(slider.min, Math.min(slider.max, val));
    onSliderChange(paramName, clamped);
  }

  /* ── Save to flash ── */

  function saveToFlash() {
    sendCommand('param_save');
    addToast(t('pid.saved'), 'success');
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
     onclick={(e) => { if (e.target === e.currentTarget) onclose(); }}>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[500px] max-h-[85vh] flex flex-col overflow-hidden">

    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <div class="flex items-center gap-2">
        <Sliders size={16} class="text-primary" />
        <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('pid.title')}</h2>
      </div>
      <Button variant="ghost" size="icon-xs" onclick={onclose}><X size={16} /></Button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4">

      {#if !paramsAvailable}
        <!-- Hint: params not loaded -->
        <div class="p-4 rounded-lg bg-muted/50 border border-border/50 text-center">
          <p class="text-xs text-muted-foreground">{t('pid.hint')}</p>
        </div>
      {:else}

        <!-- Tab selector: Roll / Pitch / Yaw -->
        <div class="flex gap-1.5 mb-4">
          {#each axes as axis (axis.id)}
            <button
              class="flex-1 px-3 py-1.5 text-xs font-semibold rounded-md transition-all
                {activeTab === axis.id
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'bg-secondary text-secondary-foreground hover:bg-muted'}"
              onclick={() => { activeTab = axis.id; }}
            >
              {t(axis.labelKey)}
            </button>
          {/each}
        </div>

        <!-- ════════════════════════════════════════════ -->
        <!-- PID Sliders for active axis                   -->
        <!-- ════════════════════════════════════════════ -->
        <div class="space-y-4">
          {#each pidSliders as slider (slider.suffix)}
            {@const paramName = paramPrefix[activeTab] + slider.suffix}
            {@const val = values[paramName] ?? 0}
            <div class="rounded-lg border border-border bg-muted/20 p-3">
              <!-- Label row -->
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-semibold text-foreground">{t(slider.labelKey)}</span>
                  <span class="text-[10px] text-muted-foreground font-mono">{paramName}</span>
                </div>
                <input
                  type="number"
                  value={val}
                  min={slider.min}
                  max={slider.max}
                  step={slider.step}
                  class="w-20 h-6 px-1.5 text-right font-mono text-xs bg-input border border-border rounded-md text-foreground
                         focus:outline-none focus:ring-1 focus:ring-ring/50"
                  onchange={(e) => onInputChange(paramName, (e.target as HTMLInputElement).value, slider)}
                />
              </div>
              <!-- Range slider -->
              <div class="flex items-center gap-2">
                <span class="text-[9px] text-muted-foreground font-mono w-8 text-right shrink-0">{slider.min}</span>
                <input
                  type="range"
                  value={val}
                  min={slider.min}
                  max={slider.max}
                  step={slider.step}
                  class="flex-1 h-2 accent-primary cursor-pointer"
                  oninput={(e) => onSliderChange(paramName, parseFloat((e.target as HTMLInputElement).value))}
                />
                <span class="text-[9px] text-muted-foreground font-mono w-8 shrink-0">{slider.max}</span>
              </div>
            </div>
          {/each}
        </div>

        <!-- ════════════════════════════════════════════ -->
        <!-- Save to Flash button                          -->
        <!-- ════════════════════════════════════════════ -->
        <div class="flex justify-end pt-4">
          <Button variant="default" size="sm" class="h-8 text-xs px-6" onclick={saveToFlash}
                  disabled={!app.drone.connected}>
            {t('pid.save')}
          </Button>
        </div>

      {/if}
    </div>
  </div>
</div>
