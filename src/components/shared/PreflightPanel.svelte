<script lang="ts">
  import { app, showConfirm } from '../../lib/stores.svelte';
  import { getParam } from '../../lib/paramStore.svelte';
  import { t } from '../../lib/i18n.svelte';
  import { preflightChecks, loadPreflightConfig, savePreflightConfig, isCheckEnabled } from '../../lib/preflight';
  import { Check, X as XIcon, Settings2 } from '@lucide/svelte';

  const d = app.drone;

  /* ── Customization state ── */
  let customConfig: Record<string, boolean> = $state(loadPreflightConfig());
  let showEditor = $state(false);

  function checkOn(key: string): boolean {
    return isCheckEnabled(customConfig, key);
  }

  /** Applies the toggle. A critical check asks first: hidden, it stops guarding the flight. */
  function toggleCheck(key: string) {
    if (checkOn(key) && allChecks.find((c) => c.key === key)?.critical) {
      void showConfirm(t('check.hideCritical')).then((ok) => {
        if (ok) applyToggle(key);
      });
      return;
    }
    applyToggle(key);
  }

  function applyToggle(key: string) {
    customConfig[key] = !checkOn(key);
    customConfig = { ...customConfig };
    savePreflightConfig(customConfig);
  }

  // BATT_ARM_VOLT is the voltage ArduPilot itself refuses to arm below.
  let battArmVolt = $derived(getParam('BATT_ARM_VOLT', -1));

  /* ── All available checks ── */
  let allChecks = $derived.by(() =>
    preflightChecks({
      drone: d,
      waypointCount: app.waypoints.length,
      battArmVolt,
      t,
    }),
  );

  /* ── Filtered checks based on user config ── */
  let checks = $derived(allChecks.filter((c) => checkOn(c.key)));

  let allCriticalOk = $derived(checks.filter((c) => c.critical).every((c) => c.ok));
  let passCount = $derived(checks.filter((c) => c.ok).length);
</script>

<div class="p-3">
  <div class="flex items-center justify-between mb-2">
    <h2 class="text-xs font-semibold text-primary uppercase tracking-wider">{t('preflight.title')}</h2>
    <div class="flex items-center gap-2">
      <span class="text-[11px] font-medium {allCriticalOk ? 'text-success' : 'text-muted-foreground'}">
        {passCount}/{checks.length}
        {allCriticalOk ? t('preflight.ready') : t('preflight.notReady')}
      </span>
      <button
        class="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors px-1.5 py-0.5 rounded hover:bg-muted/50"
        onclick={() => {
          showEditor = !showEditor;
        }}
      >
        <Settings2 size={12} />
        <span>{t('preflight.customize')}</span>
      </button>
    </div>
  </div>

  <!-- Customization editor -->
  {#if showEditor}
    <div class="mb-3 p-2.5 rounded-lg border border-border bg-muted/20">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider"
          >{t('preflight.customizeTitle')}</span
        >
      </div>
      <div class="grid grid-cols-2 gap-x-3 gap-y-1 max-sm:grid-cols-1">
        {#each allChecks as c}
          <label class="flex items-center gap-2 py-0.5 cursor-pointer group">
            <input
              type="checkbox"
              checked={checkOn(c.key)}
              onchange={() => toggleCheck(c.key)}
              class="w-3.5 h-3.5 rounded border-border accent-primary"
            />
            <span class="text-xs text-foreground group-hover:text-primary transition-colors">{c.name}</span>
            {#if c.critical}
              <span class="text-[9px] text-muted-foreground">*</span>
            {/if}
          </label>
        {/each}
      </div>
    </div>
  {/if}

  <div class="grid grid-cols-2 gap-x-3 gap-y-1 max-sm:grid-cols-1">
    {#each checks as c}
      <div class="flex items-center gap-1.5 py-0.5">
        <span
          class="w-4.5 h-4.5 rounded-full flex items-center justify-center shrink-0
          {c.ok
            ? 'bg-green-700 text-white'
            : c.critical
              ? 'bg-destructive text-white'
              : 'bg-muted text-muted-foreground'}"
        >
          {#if c.ok}<Check size={11} strokeWidth={3} />{:else}<XIcon size={11} strokeWidth={3} />{/if}
        </span>
        <span class="text-xs font-semibold whitespace-nowrap">{c.name}</span>
        <span class="text-[11px] text-muted-foreground truncate">{c.detail}</span>
      </div>
    {/each}
  </div>
  {#if allCriticalOk}
    <div
      class="mt-2 py-1.5 bg-green-900/40 text-success text-center rounded-lg text-xs font-bold border border-green-700/30"
    >
      {t('preflight.allPass')}
    </div>
  {/if}
  {#if d.prearm && d.prearm.length > 0}
    <div class="mt-2 pt-2 border-t border-border/50">
      <span class="text-[10px] font-semibold text-destructive uppercase tracking-wider">{t('prearm.title')}</span>
      <div class="mt-1 space-y-0.5">
        {#each d.prearm as msg}
          <div class="flex items-center gap-1.5 text-[11px] text-destructive/80">
            <XIcon size={10} class="shrink-0" />
            <span>{msg}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>
