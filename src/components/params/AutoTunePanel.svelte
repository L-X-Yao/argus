<script lang="ts">
  import { onDestroy } from 'svelte';
  import { app, addToast } from '../../lib/stores.svelte';
  import { specialModes } from '../../lib/vehicleModes';
  import { dispatch } from '../../lib/transport';
  import { paramState, getParam } from '../../lib/paramStore.svelte';
  import { t } from '../../lib/i18n.svelte';
  import type { DroneEvent } from '../../lib/types';
  import Button from '$lib/components/ui/button/button.svelte';
  import { X, Zap, AlertTriangle } from '@lucide/svelte';

  let { onclose }: { onclose: () => void } = $props();

  const connected = $derived(app.drone.connected);
  const armed = $derived(app.drone.armed);
  // AUTOTUNE_AXES is a bitmask (AC_AutoTune_Multi.cpp:100, 0:Roll 1:Pitch 2:Yaw) that the FC
  // keeps: All has to be written like the others, or it tunes whatever was picked last.
  const ALL_AXES = 7;
  let axes = $state(ALL_AXES);

  const AXES_OPTIONS = $derived([
    { value: ALL_AXES, label: t('autotune.all') },
    { value: 1, label: t('autotune.rollOnly') },
    { value: 2, label: t('autotune.pitchOnly') },
    { value: 4, label: t('autotune.yawOnly') },
  ]);

  let isAutotuning = $derived(
    app.drone.mode_id === specialModes().autotune
  );

  // ── The mode is real when the FC says so, never when the button is clicked ──
  // MAV_CMD_DO_SET_MODE is answered with COMMAND_ACK (GCS_Common.cpp:5077
  // handle_command_do_set_mode → _set_mode_common :2927; a refused change is
  // MAV_RESULT_FAILED :2931-2938), and the refusal says why in a STATUSTEXT
  // "Mode change to %s failed: %s" (ArduCopter/mode.cpp:175 mode_change_failed,
  // reached at :433 when AutoTune::init refuses on the ground,
  // mode_autotune.cpp:9-21: throttle at zero, landed or disarmed). Success
  // needs the ACK plus a HEARTBEAT that carries the mode. The AUTOTUNE_AXES
  // echo is deliberately not waited for — a silent echo must never stall the
  // mode change (same pending-ACK pattern as GimbalPanel).
  interface PendingMode {
    kind: 'start' | 'stop';
    mark: DroneEvent | undefined;
    expect: number;
  }
  let pending = $state<PendingMode | null>(null);
  // The last refusal: its ACK event, and when it happened. The FC's own
  // sentence for a refused mode ("Mode change to %s failed: %s",
  // ArduCopter/mode.cpp:175 mode_change_failed) often trails the COMMAND_ACK
  // through the queued statustext path, so the shown reason upgrades when it
  // lands — only for this refusal, only for a short while, and never over a
  // newer attempt: beginPending and the success branch clear it first, so a
  // fast retry that succeeds can never be relabelled by the old failure.
  let refused = $state<{ ack: DroneEvent; at: number } | null>(null);
  let modeError = $state('');
  let pendingTimer: ReturnType<typeof setTimeout> | undefined;

  function beginPending(kind: 'start' | 'stop', expect: number) {
    pending = { kind, mark: app.events[app.events.length - 1], expect };
    refused = null;
    modeError = '';
    // The links give up on a silent FC themselves after 3 tries (~3 s,
    // transport _trackCommand / backend _cmd_pending, both emitting a
    // cmd_ack_fail); this timer only catches an ACK that never matches the
    // readback, so the buttons cannot stay locked.
    clearTimeout(pendingTimer);
    pendingTimer = setTimeout(() => {
      const p = pending;
      pending = null;
      pendingTimer = undefined;
      if (p) addToast(`${p.kind === 'start' ? t('autotune.start') : t('autotune.stop')}: ${t('ack.result.noAnswer')}`, 'warn');
    }, 8000);
  }

  function start() {
    const mode = specialModes().autotune;
    if (mode === null) return; // Rover and Sub have no AutoTune mode
    if (pending) return;
    dispatch('param_set', undefined, { name: 'AUTOTUNE_AXES', value: axes });
    beginPending('start', mode);
    dispatch('mode', mode);
  }

  function stop() {
    if (pending) return;
    const hold = specialModes().hold;
    beginPending('stop', hold);
    dispatch('mode', hold);
  }

  $effect(() => {
    const p = pending;
    if (!p) return;
    const markIndex = p.mark ? app.events.lastIndexOf(p.mark) : -1;
    // If the marker was trimmed, every retained event is newer than it.
    const newer = app.events.slice(markIndex >= 0 ? markIndex + 1 : 0);
    const ack = newer.find(
      (ev) => ev.cmd === 176 && (ev.event_type === 'cmd_ack_ok' || ev.event_type === 'cmd_ack_fail'),
    );
    if (!ack) return;
    if (ack.event_type === 'cmd_ack_fail') {
      refused = { ack, at: Date.now() };
      const said = [...newer].reverse().find((ev) => ev.event_type === 'statustext');
      modeError = said?.text ?? ack.text;
      clearTimeout(pendingTimer);
      pending = null;
      pendingTimer = undefined;
      return;
    }
    if (app.drone.mode_id !== p.expect) return; // acked; the heartbeat has not caught up yet
    refused = null;
    clearTimeout(pendingTimer);
    pendingTimer = undefined;
    modeError = '';
    pending = null;
    addToast(p.kind === 'start' ? t('autotune.start') : t('autotune.stop'), 'success');
  });

  // The upgrade pass: only statustexts that arrive after this refusal's ACK,
  // within a few seconds of it. A trimmed ACK means the refusal is ancient
  // history; a newer attempt clears `refused` before this can run again.
  $effect(() => {
    const r = refused;
    if (!r) return;
    if (Date.now() - r.at > 3000) return;
    const idx = app.events.lastIndexOf(r.ack);
    if (idx < 0) return;
    const said = [...app.events.slice(idx + 1)].reverse().find((ev) => ev.event_type === 'statustext');
    if (said) modeError = said.text;
  });

  onDestroy(() => clearTimeout(pendingTimer));

  let currentAxes = $derived(getParam('AUTOTUNE_AXES', 0));
  let aggr = $derived(getParam('AUTOTUNE_AGGR', 0.1));
</script>

<div role="dialog" aria-modal="true" tabindex="-1" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999] flex items-center justify-center" onclick={onclose} onkeydown={(e) => { if (e.key === "Escape") onclose(); }}>
  <div class="bg-card border border-border rounded-2xl overflow-hidden w-[420px] shadow-2xl" role="presentation" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
    <div class="bg-gradient-to-r from-primary/20 to-primary/5 px-5 py-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Zap size={16} class="text-primary" />
        <h3 class="text-base font-bold text-primary">{t('autotune.title')}</h3>
      </div>
      <Button variant="ghost" size="icon-xs" onclick={onclose} aria-label={t('error.close')}><X size={16} /></Button>
    </div>

    <div class="px-5 py-4 space-y-4">
      {#if !connected}
        <div class="text-center py-8 text-sm text-muted-foreground">{t('console.notConnected')}</div>
      {:else}
        <div class="flex items-start gap-2 p-3 rounded-lg bg-warning/10 border border-warning/30">
          <AlertTriangle size={16} class="text-warning shrink-0 mt-0.5" />
          <p class="text-xs text-warning">{t('autotune.hint')}</p>
        </div>

        <div>
          <span class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('autotune.axes')}</span>
          <div class="flex gap-1.5 mt-1.5">
            {#each AXES_OPTIONS as opt}
              <button class="px-3 py-1.5 text-xs rounded-md border transition-all cursor-pointer
                {axes === opt.value
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-card text-muted-foreground border-border hover:text-foreground hover:bg-muted'}"
                onclick={() => axes = opt.value}>{opt.label}</button>
            {/each}
          </div>
        </div>

        {#if paramState.list.length > 0}
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div class="flex justify-between p-2 bg-muted rounded-lg">
              <span class="text-muted-foreground">AUTOTUNE_AXES</span>
              <span class="font-mono">{currentAxes}</span>
            </div>
            <div class="flex justify-between p-2 bg-muted rounded-lg">
              <span class="text-muted-foreground">AUTOTUNE_AGGR</span>
              <span class="font-mono">{aggr.toFixed(2)}</span>
            </div>
          </div>
        {/if}

        {#if isAutotuning}
          <div class="text-center py-3">
            <div class="inline-flex items-center gap-2 px-4 py-2 bg-primary/10 rounded-full">
              <span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
              <span class="text-sm font-bold text-primary">AutoTune {t('cal.active')}</span>
            </div>
          </div>
          <Button variant="destructive" class="w-full" onclick={stop} disabled={!!pending}>
            {t('autotune.stop')}
          </Button>
        {:else}
          <Button variant="default" class="w-full" onclick={start} disabled={!armed || !!pending}>
            <Zap size={14} class="mr-1" />{t('autotune.start')}
          </Button>
          {#if !armed}
            <p class="text-[10px] text-muted-foreground text-center">{t('check.notArmed')}</p>
          {/if}
        {/if}

        {#if modeError}
          <p class="text-xs text-destructive text-center" role="alert">{modeError}</p>
        {/if}
      {/if}
    </div>
  </div>
</div>
