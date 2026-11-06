<script lang="ts">
  import { app } from '../../lib/stores.svelte';
  import { vehicleKind } from '../../lib/vehicleModes';
  import { dispatch } from '../../lib/transport';
  import { getParam } from '../../lib/paramStore.svelte';
  import { t } from '../../lib/i18n.svelte';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, AlertTriangle } from '@lucide/svelte';

  let { onclose }: { onclose: () => void } = $props();

  // ESC_CALIBRATION is a Copter parameter: written elsewhere, nothing happens.
  let copter = $derived(vehicleKind() === 'copter');

  // ArduPilot calibrates ESCs by itself, during boot: with ESC_CALIBRATION at 3 it drives
  // every motor output to full for 5 s and then to minimum, and stays there until the next
  // restart (ArduCopter/esc_calibration.cpp:60, esc_calibration_auto). Nothing a GCS sends
  // reaches a disarmed motor output, so all there is to do from here is to set it up.
  // A soft reboot will not do: the FC refuses one while this is set
  // (GCS_MAVLink_Copter.cpp:448), since the ESCs have to lose power too.
  const ESCCAL_AUTO = 3;
  const ESCCAL_NONE = 0;

  const connected = $derived(app.drone.connected);
  const armedForBoot = $derived(getParam('ESC_CALIBRATION', ESCCAL_NONE) === ESCCAL_AUTO);

  const setCal = (value: number) => dispatch('param_set', undefined, { name: 'ESC_CALIBRATION', value });

  const STEPS = $derived([t('esccal.step1'), t('esccal.step2'), t('esccal.step3'), t('esccal.step4')]);
</script>

<div
  role="dialog"
  aria-modal="true"
  tabindex="-1"
  class="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center"
  onclick={onclose}
  onkeydown={(e) => {
    if (e.key === 'Escape') onclose();
  }}
>
  <div
    class="bg-card border border-border rounded-2xl overflow-hidden w-[420px] shadow-2xl"
    role="presentation"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <div class="bg-gradient-to-r from-warning/20 to-warning/5 px-5 py-3 flex items-center justify-between">
      <h3 class="text-base font-bold text-warning">{t('esccal.title')}</h3>
      <Button variant="ghost" size="icon-xs" onclick={onclose} aria-label={t('error.close')}><X size={16} /></Button>
    </div>

    <div class="px-5 py-4 space-y-4">
      <div class="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/30">
        <AlertTriangle size={18} class="text-destructive shrink-0" />
        <span class="text-xs font-bold text-destructive">{t('esccal.warn')}</span>
      </div>

      {#if !copter}
        <p class="text-xs text-warning" data-testid="copter-only">{t('setup.copterOnly')}</p>
      {:else if !connected}
        <div class="text-center py-8 text-sm text-muted-foreground">{t('console.notConnected')}</div>
      {:else}
        <ol class="space-y-2">
          {#each STEPS as label}
            <li class="py-2 px-3 rounded-lg bg-muted/50 text-sm">{label}</li>
          {/each}
        </ol>

        {#if armedForBoot}
          <p class="text-sm font-bold text-warning">{t('esccal.armed')}</p>
          <Button variant="outline" class="w-full" onclick={() => setCal(ESCCAL_NONE)}>{t('esccal.disarm')}</Button>
        {:else}
          <Button variant="destructive" class="w-full" onclick={() => setCal(ESCCAL_AUTO)} disabled={app.drone.armed}
            >{t('esccal.arm')}</Button
          >
        {/if}
      {/if}
    </div>
  </div>
</div>
