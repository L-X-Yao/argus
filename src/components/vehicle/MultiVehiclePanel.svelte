<script lang="ts">
  import { app, addToast } from '../../lib/stores.svelte';
  import { t } from '../../lib/i18n.svelte';
  import { X, Plane, Radio } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';
  import Badge from '$lib/components/ui/badge/badge.svelte';

  let { onclose }: { onclose: () => void } = $props();

  /* ── Active vehicle (own sysid = 1 by convention) ── */
  let activeSysid = $state(1);

  let otherVehicles = $derived(
    app.drone.vehicles.filter(v => v.sysid !== activeSysid)
  );

  /* ── Mode name helper ── */
  function modeName(id: number | undefined): string {
    if (id === undefined) return '---';
    return `Mode ${id}`;
  }

  /* ── Heading format ── */
  function fmtHdg(hdg: number): string {
    return `${Math.round(hdg)}°`;
  }

  /* ── Switch control (placeholder) ── */
  function switchTo(sysid: number) {
    addToast(`${t('multi.switch')}: sysid=${sysid} (placeholder)`, 'info');
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
        <Radio size={16} class="text-primary" />
        <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('multi.title')}</h2>
        <Badge variant="secondary" class="text-[10px]">
          {app.drone.vehicles.length}
        </Badge>
      </div>
      <Button variant="ghost" size="icon-xs" onclick={onclose}><X size={16} /></Button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">

      <!-- Active vehicle info -->
      <div class="p-3 rounded-lg bg-primary/10 border border-primary/30 space-y-2">
        <div class="flex items-center gap-2">
          <Plane size={14} class="text-primary shrink-0" />
          <span class="text-xs font-semibold text-primary uppercase">{t('multi.active')}</span>
        </div>
        <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <div class="flex justify-between">
            <span class="text-muted-foreground">SysID</span>
            <span class="font-mono font-medium text-foreground">{activeSysid}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted-foreground">{t('ctrl.mode')}</span>
            <span class="font-medium text-foreground">{app.drone.mode}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted-foreground">{t('status.armed')}</span>
            <span class="font-medium {app.drone.armed ? 'text-destructive' : 'text-muted-foreground'}">
              {app.drone.armed ? 'Armed' : 'Disarmed'}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted-foreground">Alt</span>
            <span class="font-mono font-medium text-foreground">{app.drone.alt_rel.toFixed(1)} m</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted-foreground">Lat</span>
            <span class="font-mono text-[11px] text-foreground">{app.drone.lat.toFixed(6)}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-muted-foreground">Lon</span>
            <span class="font-mono text-[11px] text-foreground">{app.drone.lon.toFixed(6)}</span>
          </div>
        </div>
      </div>

      <!-- Vehicle list header -->
      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{t('multi.vehicles')}</span>
        <Badge variant="outline" class="text-[10px]">{otherVehicles.length}</Badge>
      </div>

      <!-- Vehicle cards -->
      {#if otherVehicles.length > 0}
        <div class="space-y-2">
          {#each otherVehicles as v (v.sysid)}
            <div class="p-3 rounded-lg border border-border bg-muted/30 hover:bg-muted/50 transition-colors">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <Plane size={14} class="text-muted-foreground" />
                  <span class="text-xs font-semibold text-foreground">SysID {v.sysid}</span>
                  {#if v.armed}
                    <Badge variant="destructive" class="text-[10px]">Armed</Badge>
                  {:else}
                    <Badge variant="outline" class="text-[10px]">Disarmed</Badge>
                  {/if}
                </div>
                <Button variant="outline" size="xs" onclick={() => switchTo(v.sysid)}>
                  {t('multi.switch')}
                </Button>
              </div>
              <div class="grid grid-cols-3 gap-x-3 gap-y-1 text-[11px]">
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Alt</span>
                  <span class="font-mono text-foreground">{v.alt.toFixed(1)} m</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Hdg</span>
                  <span class="font-mono text-foreground">{fmtHdg(v.hdg)}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-muted-foreground">{t('ctrl.mode')}</span>
                  <span class="font-mono text-foreground">{modeName(v.mode)}</span>
                </div>
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <div class="p-6 rounded-lg bg-muted/50 border border-border/50 text-center">
          <Radio size={24} class="mx-auto text-muted-foreground/50 mb-2" />
          <p class="text-xs text-muted-foreground">{t('multi.noVehicles')}</p>
        </div>
      {/if}

    </div>
  </div>
</div>
