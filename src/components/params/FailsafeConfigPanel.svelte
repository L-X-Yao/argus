<script lang="ts">
  import { addToast } from '../../lib/stores.svelte';
  import { sendCommand } from '../../lib/ws';
  import { paramState } from '../../lib/paramStore.svelte';
  import { t } from '../../lib/i18n.svelte';
  import { X, ShieldAlert, Battery, Radio, Wifi, Navigation } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let { onclose }: { onclose: () => void } = $props();

  /* ── Helpers ── */

  function getParam(name: string, fallback: number): number {
    const p = paramState.list.find(p => p.name === name);
    return p !== undefined ? p.value : fallback;
  }

  function saveParams(pairs: [string, number][]) {
    for (const [name, value] of pairs) {
      sendCommand('param_set', undefined, { name, value });
    }
    addToast(t('failsafe.saved').replace('{n}', String(pairs.length)), 'success');
  }

  let paramsAvailable = $derived(paramState.list.length > 0);

  /* ── Battery failsafe ── */
  let battEnable  = $state(0);
  let battAction  = $state(0);
  let battVoltage = $state(10.5);
  let battMah     = $state(0);

  /* ── RC Loss ── */
  let rcEnable    = $state(0);
  let rcAction    = $state(0);
  let rcPwm       = $state(975);

  /* ── GCS Loss ── */
  let gcsEnable   = $state(0);
  let gcsAction   = $state(0);

  /* ── EKF/GPS ── */
  let ekfAction   = $state(0);
  let ekfThresh   = $state(0.8);

  /* ── Load from params on mount ── */
  $effect(() => {
    if (!paramsAvailable) return;
    battEnable  = getParam('FS_BATT_ENABLE', 0);
    // Audit F-18: was reading FS_BATT_ENABLE for both — the action selector
    // displayed the same value as the enable toggle. Correct param is
    // BATT_FS_LOW_ACT (Copter) / BATT_FS_LOW_ACT (Plane, 4.x).
    battAction  = getParam('BATT_FS_LOW_ACT', 0);
    battVoltage = getParam('FS_BATT_VOLTAGE', 10.5);
    battMah     = getParam('FS_BATT_MAH', 0);

    rcEnable    = getParam('FS_THR_ENABLE', 0);
    // FS_THR_ENABLE is itself the action enum (0=disabled, 1=Always RTL,
    // 2=Continue with Mission, 3=Always Land, 4=SmartRTL or RTL, ...).
    // Use the same value for the action selector; the UI then maps it to
    // a label via rcActions.
    rcAction    = getParam('FS_THR_ENABLE', 0);
    rcPwm       = getParam('FS_THR_VALUE', 975);

    gcsEnable   = getParam('FS_GCS_ENABLE', 0);
    // FS_GCS_ENABLE is the action enum same as FS_THR_ENABLE.
    gcsAction   = getParam('FS_GCS_ENABLE', 0);

    ekfAction   = getParam('FS_EKF_ACTION', 0);
    ekfThresh   = getParam('FS_EKF_THRESH', 0.8);
  });

  /* ── Action option maps ── */
  const stdActions: [number, string][] = [
    [0, 'failsafe.actionNone'],
    [1, 'failsafe.actionRtl'],
    [2, 'failsafe.actionLand'],
    [3, 'failsafe.actionSmartRtl'],
  ];

  const rcActions: [number, string][] = [
    [0, 'failsafe.actionNone'],
    [1, 'failsafe.actionRtl'],
    [2, 'failsafe.actionContinue'],
    [3, 'failsafe.actionLand'],
    [4, 'failsafe.actionSmartRtl'],
  ];

  const ekfActions: [number, string][] = [
    [0, 'failsafe.actionNone'],
    [1, 'failsafe.actionLand'],
    [2, 'failsafe.actionAltHold'],
  ];

  /* ── Section save handlers ── */
  function saveBattery() {
    saveParams([
      ['FS_BATT_ENABLE', battEnable ? battAction || 1 : 0],
      ['FS_BATT_VOLTAGE', battVoltage],
      ['FS_BATT_MAH', battMah],
    ]);
  }

  function saveRc() {
    saveParams([
      ['FS_THR_ENABLE', rcEnable ? rcAction || 1 : 0],
      ['FS_THR_VALUE', rcPwm],
    ]);
  }

  function saveGcs() {
    saveParams([
      ['FS_GCS_ENABLE', gcsEnable ? gcsAction || 1 : 0],
    ]);
  }

  function saveEkf() {
    saveParams([
      ['FS_EKF_ACTION', ekfAction],
      ['FS_EKF_THRESH', ekfThresh],
    ]);
  }
</script>

<div role="dialog" aria-modal="true" tabindex="-1" class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
     onclick={(e) => { if (e.target === e.currentTarget) onclose(); }} onkeydown={(e) => { if (e.key === "Escape") onclose(); }}>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[550px] max-h-[85vh] flex flex-col overflow-hidden">

    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <div class="flex items-center gap-2">
        <ShieldAlert size={16} class="text-primary" />
        <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('failsafe.title')}</h2>
      </div>
      <Button variant="ghost" size="icon-xs" onclick={onclose} aria-label="Close"><X size={16} /></Button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">

      {#if !paramsAvailable}
        <!-- Hint: params not loaded -->
        <div class="p-4 rounded-lg bg-muted/50 border border-border/50 text-center">
          <p class="text-xs text-muted-foreground">{t('failsafe.hint')}</p>
        </div>
      {:else}

        <!-- ════════════════════════════════════════════ -->
        <!-- 1. Battery Failsafe                          -->
        <!-- ════════════════════════════════════════════ -->
        <div class="rounded-lg border border-border bg-card overflow-hidden border-l-[3px] border-l-red-500">
          <div class="px-4 py-2.5 flex items-center justify-between bg-muted/30">
            <div class="flex items-center gap-2">
              <Battery size={14} class="text-red-500" />
              <span class="text-xs font-semibold text-foreground uppercase tracking-wider">{t('failsafe.battery')}</span>
            </div>
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={battEnable > 0}
                     onchange={() => { battEnable = battEnable > 0 ? 0 : 1; }} />
              <div class="w-9 h-5 bg-muted-foreground/30 peer-checked:bg-red-500 rounded-full
                          after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                          after:bg-white after:rounded-full after:h-4 after:w-4
                          after:transition-all peer-checked:after:translate-x-full transition-colors"></div>
              <span class="ml-2 text-[11px] text-muted-foreground">
                {battEnable > 0 ? t('failsafe.enable') : t('failsafe.disable')}
              </span>
            </label>
          </div>
          <div class="px-4 py-3 space-y-2.5">
            <div class="flex justify-between items-center">
              <label for="fs-batt-action" class="text-xs text-muted-foreground">{t('failsafe.action')}</label>
              <select id="fs-batt-action" bind:value={battAction}
                      class="w-36 h-7 px-2 bg-input border border-border rounded-md text-xs text-foreground
                             focus:outline-none focus:ring-1 focus:ring-ring/50">
                {#each stdActions as [val, key]}
                  <option value={val}>{t(key)}</option>
                {/each}
              </select>
            </div>
            <div class="flex justify-between items-center">
              <label for="fs-batt-volt" class="text-xs text-muted-foreground">{t('failsafe.voltage')}</label>
              <div class="flex items-center gap-1">
                <input id="fs-batt-volt" type="number" bind:value={battVoltage}
                       min="0" max="60" step="0.1"
                       class="w-20 h-7 px-2 text-right bg-input border border-border rounded-md text-xs text-foreground
                              focus:outline-none focus:ring-1 focus:ring-ring/50" />
                <span class="text-[11px] text-muted-foreground w-4">V</span>
              </div>
            </div>
            <div class="flex justify-between items-center">
              <label for="fs-batt-mah" class="text-xs text-muted-foreground">{t('failsafe.mah')}</label>
              <div class="flex items-center gap-1">
                <input id="fs-batt-mah" type="number" bind:value={battMah}
                       min="0" max="99999" step="100"
                       class="w-20 h-7 px-2 text-right bg-input border border-border rounded-md text-xs text-foreground
                              focus:outline-none focus:ring-1 focus:ring-ring/50" />
                <span class="text-[11px] text-muted-foreground w-8">mAh</span>
              </div>
            </div>
            <div class="flex justify-end pt-1">
              <Button variant="default" size="sm" class="h-7 text-xs px-4" onclick={saveBattery}>
                {t('fence.save') ?? 'Save'}
              </Button>
            </div>
          </div>
        </div>

        <!-- ════════════════════════════════════════════ -->
        <!-- 2. RC Loss                                    -->
        <!-- ════════════════════════════════════════════ -->
        <div class="rounded-lg border border-border bg-card overflow-hidden border-l-[3px] border-l-orange-500">
          <div class="px-4 py-2.5 flex items-center justify-between bg-muted/30">
            <div class="flex items-center gap-2">
              <Radio size={14} class="text-orange-500" />
              <span class="text-xs font-semibold text-foreground uppercase tracking-wider">{t('failsafe.rcLoss')}</span>
            </div>
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={rcEnable > 0}
                     onchange={() => { rcEnable = rcEnable > 0 ? 0 : 1; }} />
              <div class="w-9 h-5 bg-muted-foreground/30 peer-checked:bg-orange-500 rounded-full
                          after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                          after:bg-white after:rounded-full after:h-4 after:w-4
                          after:transition-all peer-checked:after:translate-x-full transition-colors"></div>
              <span class="ml-2 text-[11px] text-muted-foreground">
                {rcEnable > 0 ? t('failsafe.enable') : t('failsafe.disable')}
              </span>
            </label>
          </div>
          <div class="px-4 py-3 space-y-2.5">
            <div class="flex justify-between items-center">
              <label for="fs-rc-action" class="text-xs text-muted-foreground">{t('failsafe.action')}</label>
              <select id="fs-rc-action" bind:value={rcAction}
                      class="w-36 h-7 px-2 bg-input border border-border rounded-md text-xs text-foreground
                             focus:outline-none focus:ring-1 focus:ring-ring/50">
                {#each rcActions as [val, key]}
                  <option value={val}>{t(key)}</option>
                {/each}
              </select>
            </div>
            <div class="flex justify-between items-center">
              <label for="fs-rc-pwm" class="text-xs text-muted-foreground">{t('failsafe.rcPwm')}</label>
              <div class="flex items-center gap-1">
                <input id="fs-rc-pwm" type="number" bind:value={rcPwm}
                       min="800" max="1200" step="1"
                       class="w-20 h-7 px-2 text-right bg-input border border-border rounded-md text-xs text-foreground
                              focus:outline-none focus:ring-1 focus:ring-ring/50" />
                <span class="text-[11px] text-muted-foreground w-8">PWM</span>
              </div>
            </div>
            <div class="flex justify-end pt-1">
              <Button variant="default" size="sm" class="h-7 text-xs px-4" onclick={saveRc}>
                {t('fence.save') ?? 'Save'}
              </Button>
            </div>
          </div>
        </div>

        <!-- ════════════════════════════════════════════ -->
        <!-- 3. GCS Loss                                   -->
        <!-- ════════════════════════════════════════════ -->
        <div class="rounded-lg border border-border bg-card overflow-hidden border-l-[3px] border-l-yellow-500">
          <div class="px-4 py-2.5 flex items-center justify-between bg-muted/30">
            <div class="flex items-center gap-2">
              <Wifi size={14} class="text-yellow-500" />
              <span class="text-xs font-semibold text-foreground uppercase tracking-wider">{t('failsafe.gcsLoss')}</span>
            </div>
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={gcsEnable > 0}
                     onchange={() => { gcsEnable = gcsEnable > 0 ? 0 : 1; }} />
              <div class="w-9 h-5 bg-muted-foreground/30 peer-checked:bg-yellow-500 rounded-full
                          after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                          after:bg-white after:rounded-full after:h-4 after:w-4
                          after:transition-all peer-checked:after:translate-x-full transition-colors"></div>
              <span class="ml-2 text-[11px] text-muted-foreground">
                {gcsEnable > 0 ? t('failsafe.enable') : t('failsafe.disable')}
              </span>
            </label>
          </div>
          <div class="px-4 py-3 space-y-2.5">
            <div class="flex justify-between items-center">
              <label for="fs-gcs-action" class="text-xs text-muted-foreground">{t('failsafe.action')}</label>
              <select id="fs-gcs-action" bind:value={gcsAction}
                      class="w-36 h-7 px-2 bg-input border border-border rounded-md text-xs text-foreground
                             focus:outline-none focus:ring-1 focus:ring-ring/50">
                {#each stdActions as [val, key]}
                  <option value={val}>{t(key)}</option>
                {/each}
              </select>
            </div>
            <div class="flex justify-end pt-1">
              <Button variant="default" size="sm" class="h-7 text-xs px-4" onclick={saveGcs}>
                {t('fence.save') ?? 'Save'}
              </Button>
            </div>
          </div>
        </div>

        <!-- ════════════════════════════════════════════ -->
        <!-- 4. EKF / GPS                                  -->
        <!-- ════════════════════════════════════════════ -->
        <div class="rounded-lg border border-border bg-card overflow-hidden border-l-[3px] border-l-blue-500">
          <div class="px-4 py-2.5 flex items-center justify-between bg-muted/30">
            <div class="flex items-center gap-2">
              <Navigation size={14} class="text-blue-500" />
              <span class="text-xs font-semibold text-foreground uppercase tracking-wider">{t('failsafe.ekf')}</span>
            </div>
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" class="sr-only peer" checked={ekfAction > 0}
                     onchange={() => { ekfAction = ekfAction > 0 ? 0 : 1; }} />
              <div class="w-9 h-5 bg-muted-foreground/30 peer-checked:bg-blue-500 rounded-full
                          after:content-[''] after:absolute after:top-[2px] after:left-[2px]
                          after:bg-white after:rounded-full after:h-4 after:w-4
                          after:transition-all peer-checked:after:translate-x-full transition-colors"></div>
              <span class="ml-2 text-[11px] text-muted-foreground">
                {ekfAction > 0 ? t('failsafe.enable') : t('failsafe.disable')}
              </span>
            </label>
          </div>
          <div class="px-4 py-3 space-y-2.5">
            <div class="flex justify-between items-center">
              <label for="fs-ekf-action" class="text-xs text-muted-foreground">{t('failsafe.action')}</label>
              <select id="fs-ekf-action" bind:value={ekfAction}
                      class="w-36 h-7 px-2 bg-input border border-border rounded-md text-xs text-foreground
                             focus:outline-none focus:ring-1 focus:ring-ring/50">
                {#each ekfActions as [val, key]}
                  <option value={val}>{t(key)}</option>
                {/each}
              </select>
            </div>
            <div class="flex justify-between items-center">
              <label for="fs-ekf-thresh" class="text-xs text-muted-foreground">{t('failsafe.threshold')}</label>
              <div class="flex items-center gap-1">
                <input id="fs-ekf-thresh" type="number" bind:value={ekfThresh}
                       min="0.1" max="1.0" step="0.05"
                       class="w-20 h-7 px-2 text-right bg-input border border-border rounded-md text-xs text-foreground
                              focus:outline-none focus:ring-1 focus:ring-ring/50" />
              </div>
            </div>
            <div class="flex justify-end pt-1">
              <Button variant="default" size="sm" class="h-7 text-xs px-4" onclick={saveEkf}>
                {t('fence.save') ?? 'Save'}
              </Button>
            </div>
          </div>
        </div>

      {/if}
    </div>
  </div>
</div>
