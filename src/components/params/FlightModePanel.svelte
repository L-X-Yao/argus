<script lang="ts">
  import { app, addToast } from '../../lib/stores.svelte';
  import { vehicleKind } from '../../lib/vehicleModes';
  import { dispatch } from '../../lib/transport';
  import { paramState, getParam } from '../../lib/paramStore.svelte';
  import { getModeName, getModeEntries } from '../../lib/modeStore';
  import { t } from '../../lib/i18n.svelte';
  import { X, Plane } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let { onclose }: { onclose: () => void } = $props();

  const PWM_RANGES = [
    '1-1230', '1231-1360', '1361-1490',
    '1491-1620', '1621-1749', '1750+',
  ];

  /* ── Helpers ── */

  let vtype = $derived(vehicleKind());
  let modeEntries = $derived(getModeEntries(vtype));
  // Rover names these MODE1-6 (Rover/Parameters.cpp:159); Sub has FLTMODE1-6 like the
  // rest (ArduSub/Parameters.cpp:121), so ask the parameter list, not the vehicle type.
  let prefix = $derived(vtype === 'rover' ? 'MODE' : 'FLTMODE');

  // Only a finished read can say a name is missing.
  let paramsRead = $derived(
    app.drone.connected && !paramState.fetching && paramState.total > 0 && paramState.received >= paramState.total,
  );
  // All six, or Save would write 0 over a slot that has not arrived.
  let hasSlots = $derived([1, 2, 3, 4, 5, 6].every((i) => getParam(`${prefix}${i}`, -1) >= 0));

  /* ── Slot state ── */
  let slot1 = $state(0);
  let slot2 = $state(0);
  let slot3 = $state(0);
  let slot4 = $state(0);
  let slot5 = $state(0);
  let slot6 = $state(0);

  let slots = $derived([slot1, slot2, slot3, slot4, slot5, slot6]);

  /* ── Load from params ── */
  // Audit F-17: load once, don't clobber operator edits mid-stream.
  let _loaded = $state(false);
  $effect(() => {
    if (!hasSlots) { _loaded = false; return; }
    if (_loaded) return;
    _loaded = true;
    slot1 = getParam(`${prefix}1`, 0);
    slot2 = getParam(`${prefix}2`, 0);
    slot3 = getParam(`${prefix}3`, 0);
    slot4 = getParam(`${prefix}4`, 0);
    slot5 = getParam(`${prefix}5`, 0);
    slot6 = getParam(`${prefix}6`, 0);
  });

  /* ── Determine active slot from mode_id ── */
  let activeSlotIndex = $derived.by(() => {
    const current = app.drone.mode_id;
    for (let i = 0; i < 6; i++) {
      if (slots[i] === current) return i;
    }
    return -1;
  });

  /* ── Setters ── */
  function setSlot(index: number, value: number) {
    switch (index) {
      case 0: slot1 = value; break;
      case 1: slot2 = value; break;
      case 2: slot3 = value; break;
      case 3: slot4 = value; break;
      case 4: slot5 = value; break;
      case 5: slot6 = value; break;
    }
  }

  /* ── Save ── */
  function saveAll() {
    const pairs: [string, number][] = [
      [`${prefix}1`, slot1], [`${prefix}2`, slot2], [`${prefix}3`, slot3],
      [`${prefix}4`, slot4], [`${prefix}5`, slot5], [`${prefix}6`, slot6],
    ];
    for (const [name, value] of pairs) {
      dispatch('param_set', undefined, { name, value });
    }
    addToast(t('fltmode.saved'), 'success');
  }
</script>

<div role="dialog" aria-modal="true" tabindex="-1" class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
     onclick={(e) => { if (e.target === e.currentTarget) onclose(); }} onkeydown={(e) => { if (e.key === "Escape") onclose(); }}>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[550px] max-h-[85vh] flex flex-col overflow-hidden">

    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <div class="flex items-center gap-2">
        <Plane size={16} class="text-primary" />
        <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('fltmode.title')}</h2>
      </div>
      <Button variant="ghost" size="icon-xs" onclick={onclose} aria-label={t('error.close')}><X size={16} /></Button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">

      {#if !hasSlots && !paramsRead}
        <div class="p-4 rounded-lg bg-muted/50 border border-border/50 text-center">
          <p class="text-xs text-muted-foreground">{t('param.connectHint')}</p>
        </div>
      {:else if !hasSlots}
        <div class="p-4 rounded-lg bg-muted/50 border border-border/50 text-center">
          <p class="text-xs text-muted-foreground">{t('fltmode.noSwitch')}</p>
        </div>
      {:else}

        <!-- Current active mode -->
        <div class="flex items-center gap-2 p-3 rounded-lg bg-primary/10 border border-primary/30">
          <Plane size={14} class="text-primary shrink-0" />
          <span class="text-xs font-medium text-foreground">{t('fltmode.current')}:</span>
          <span class="text-xs font-bold text-primary">
            {getModeName(vtype, app.drone.mode_id)}
          </span>
        </div>

        <!-- 6 mode slots -->
        <div class="rounded-lg border border-border overflow-hidden">
          {#each Array(6) as _, i}
            {@const isActive = activeSlotIndex === i}
            <div class="flex items-center gap-3 px-4 py-2.5 border-b border-border/50 last:border-b-0 transition-colors
              {isActive ? 'bg-primary/5 border-l-[3px] border-l-primary' : 'hover:bg-muted/30'}">

              <!-- Slot label -->
              <div class="w-14 shrink-0">
                <span class="text-[11px] font-semibold text-foreground">{t('fltmode.slot')} {i + 1}</span>
              </div>

              <!-- PWM range -->
              <div class="w-20 shrink-0">
                <span class="text-[10px] font-mono text-muted-foreground">{t('fltmode.pwm')}: {PWM_RANGES[i]}</span>
              </div>

              <!-- Mode dropdown -->
              <select
                value={slots[i]}
                onchange={(e) => setSlot(i, Number((e.target as HTMLSelectElement).value))}
                class="flex-1 h-7 px-2 bg-input border border-border rounded-md text-xs text-foreground
                       focus:outline-none focus:ring-1 focus:ring-ring/50
                       {isActive ? 'ring-1 ring-primary/50' : ''}">
                {#each modeEntries as [val, name]}
                  <option value={val}>{name}</option>
                {/each}
              </select>

              <!-- Active indicator -->
              {#if isActive}
                <div class="w-2 h-2 rounded-full bg-primary shrink-0 animate-pulse"></div>
              {/if}
            </div>
          {/each}
        </div>

        <!-- Save button -->
        <div class="flex justify-end pt-1">
          <Button variant="default" size="sm" class="h-7 text-xs px-6" onclick={saveAll}>
            {t('fltmode.save')}
          </Button>
        </div>

      {/if}
    </div>
  </div>
</div>
