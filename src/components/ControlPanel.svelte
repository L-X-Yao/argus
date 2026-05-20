<script lang="ts">
  import { app, showConfirm, showSlide, addToast, saveSettings, isPlane } from '../lib/stores.svelte';
  import { sendCommand } from '../lib/ws';
  import { t } from '../lib/i18n.svelte';
  import Button from '$lib/components/ui/button/button.svelte';
  import { Plane, ShieldCheck, CircleStop, ArrowDown, CornerDownLeft, Play, Pause, Package, ChevronUp, ChevronDown } from '@lucide/svelte';

  type Phase = 'disarmed' | 'ground' | 'flying' | 'mission' | 'returning';

  const RTL_MODES = ['返航', '旋翼返航', '智能返航'];
  const LAND_MODES = ['降落', '旋翼降落'];
  const AUTO_MODES = ['自动'];

  let phase = $derived.by((): Phase => {
    const d = app.drone;
    if (!d.armed) return 'disarmed';
    if (RTL_MODES.includes(d.mode) || LAND_MODES.includes(d.mode)) return 'returning';
    if (AUTO_MODES.includes(d.mode)) return 'mission';
    if (d.alt_rel < 2 && d.gs < 1) return 'ground';
    return 'flying';
  });

  let phaseLabel = $derived(
    phase === 'disarmed' ? t('phase.disarmed') :
    phase === 'ground' ? t('phase.ground') :
    phase === 'mission' ? t('phase.mission') :
    phase === 'returning' ? t('phase.returning') : t('phase.flying')
  );

  let phaseColor = $derived(
    phase === 'disarmed' ? 'text-muted-foreground' :
    phase === 'ground' ? 'text-teal-400' :
    phase === 'mission' ? 'text-blue-400' :
    phase === 'returning' ? 'text-orange-400' : 'text-green-400'
  );

  function arm() { showSlide(t('slide.arm'), 'orange', () => sendCommand('arm')); }
  function disarm() { sendCommand('disarm'); }
  function rtl() { showSlide(t('slide.rtl'), 'red', () => sendCommand('rtl')); }
  function forceDisarm() { showSlide(t('slide.forceDisarm'), 'red', () => sendCommand('force_disarm')); }
  function pauseMode() { sendCommand('mode', isPlane() ? 19 : 5); }
  function takeoff() { showSlide(`${t('slide.takeoff')} ${app.defaultAlt}m`, 'teal', () => sendCommand('takeoff', undefined, { alt: app.defaultAlt })); }
  function startMission() { showSlide(t('slide.mission'), 'blue', () => sendCommand('mission_start')); }
  async function drop() { if (await showConfirm(t('ctrl.drop') + '?', true)) sendCommand('drop'); }
  function adjustAlt(delta: number) {
    const d = app.drone;
    if (!d.connected || !d.armed || d.lat === 0) return;
    const newAlt = Math.max(5, Math.round(d.alt_rel + delta));
    sendCommand('guided_goto', undefined, { lat: d.lat, lon: d.lon, alt: newAlt });
    addToast(`${t('ctrl.altitude')} → ${newAlt}m`, 'info', 2000);
  }
</script>

<div class="bg-card border-r border-border p-3 w-44 shrink-0 flex flex-col gap-2">
  <div class="flex items-center gap-2 px-1">
    <span class="w-2 h-2 rounded-full {phase === 'disarmed' ? 'bg-gray-500' : 'bg-current animate-pulse'} {phaseColor}"></span>
    <span class="text-[11px] font-bold uppercase tracking-wider {phaseColor}">{phaseLabel}</span>
  </div>

  {#if phase === 'disarmed'}
    <Button size="sm" class="w-full bg-orange-700 hover:bg-orange-800 text-white font-bold gap-1.5" onclick={arm}>
      <ShieldCheck size={14} />{t('ctrl.arm')}
    </Button>
    <div class="text-[11px] text-muted-foreground font-semibold mt-1 tracking-wide uppercase">{t('ctrl.mode')}</div>
    <div class="flex flex-col gap-1">
      {#each app.drone.mode_btns as [id, name]}
        <Button variant={app.drone.mode_id === id ? 'default' : 'secondary'} size="sm" class="w-full justify-start"
                onclick={() => sendCommand('mode', id)}>{name}</Button>
      {/each}
    </div>
    <div class="text-[11px] text-muted-foreground font-semibold mt-1 tracking-wide uppercase">{t('ctrl.mission')}</div>
    <Button variant="outline" size="sm" class="w-full" onclick={() => sendCommand('mission_download')}>{t('ctrl.downloadMission')}</Button>
    <Button variant="outline" size="sm" class="w-full" onclick={async () => { if (await showConfirm(t('ctrl.clearMission') + '?')) sendCommand('mission_clear'); }}>{t('ctrl.clearMission')}</Button>

  {:else if phase === 'ground'}
    <div class="flex gap-1">
      <Button size="sm" class="flex-1 bg-teal-700 hover:bg-teal-800 text-white font-bold gap-1" onclick={takeoff}>
        <Plane size={14} />{t('ctrl.takeoff')}
      </Button>
      <div class="flex items-center gap-0.5 bg-muted rounded-md px-1">
        <input type="number" bind:value={app.defaultAlt} min="5" max="200" step="5"
               onchange={() => saveSettings()}
               class="w-9 h-7 px-0.5 text-center text-xs font-bold bg-transparent border-none text-foreground focus:outline-none" />
        <span class="text-[10px] text-muted-foreground">m</span>
      </div>
    </div>
    {#if app.waypoints.length > 0}
      <Button size="sm" class="w-full bg-blue-700 hover:bg-blue-800 text-white font-bold gap-1.5" onclick={startMission}>
        <Play size={14} />{t('ctrl.startMission')}
      </Button>
    {/if}
    <Button size="sm" class="w-full bg-green-700 hover:bg-green-800 text-white" onclick={disarm}>{t('ctrl.disarm')}</Button>
    <div class="text-[11px] text-muted-foreground font-semibold mt-1 tracking-wide uppercase">{t('ctrl.mode')}</div>
    <div class="flex flex-col gap-1">
      {#each app.drone.mode_btns.slice(0, 4) as [id, name]}
        <Button variant={app.drone.mode_id === id ? 'default' : 'secondary'} size="sm" class="w-full justify-start"
                onclick={() => sendCommand('mode', id)}>{name}</Button>
      {/each}
    </div>

  {:else if phase === 'flying'}
    <Button variant="destructive" size="sm" class="w-full font-bold gap-1.5" onclick={rtl}>
      <CornerDownLeft size={14} />{t('ctrl.rtl')}
    </Button>
    <Button size="sm" class="w-full bg-amber-600 hover:bg-amber-700 text-white font-bold gap-1.5" onclick={pauseMode}>
      <Pause size={14} />{t('ctrl.pause')}
    </Button>
    {#if app.waypoints.length > 0}
      <Button size="sm" class="w-full bg-blue-700 hover:bg-blue-800 text-white gap-1.5" onclick={startMission}>
        <Play size={14} />{t('ctrl.startMission')}
      </Button>
    {/if}
    <div class="text-[11px] text-muted-foreground font-semibold mt-1 tracking-wide uppercase">{t('ctrl.altitude')}</div>
    <div class="flex items-center gap-1">
      <Button variant="outline" size="xs" class="px-1.5" onclick={() => adjustAlt(-5)}><ChevronDown size={12} /></Button>
      <span class="flex-1 text-center text-xs font-bold tabular-nums">{app.drone.alt_rel.toFixed(0)}m</span>
      <Button variant="outline" size="xs" class="px-1.5" onclick={() => adjustAlt(5)}><ChevronUp size={12} /></Button>
    </div>
    <div class="text-[11px] text-muted-foreground font-semibold mt-1 tracking-wide uppercase">{t('ctrl.payload')}</div>
    <div class="flex gap-1.5">
      <Button size="sm" class="flex-1 bg-orange-700 hover:bg-orange-800 text-white font-bold" onclick={drop}>
        <Package size={12} />{t('ctrl.drop')}
      </Button>
      <Button size="sm" variant="secondary" class="flex-1" onclick={() => sendCommand('drop_stop')}>{t('ctrl.dropStop')}</Button>
    </div>
    <div class="text-[11px] text-muted-foreground font-semibold mt-1 tracking-wide uppercase">{t('ctrl.mode')}</div>
    <div class="flex flex-col gap-1">
      {#each app.drone.mode_btns as [id, name]}
        <Button variant={app.drone.mode_id === id ? 'default' : 'secondary'} size="sm" class="w-full justify-start"
                onclick={() => sendCommand('mode', id)}>{name}</Button>
      {/each}
    </div>
    <Button variant="ghost" size="xs" class="w-full text-destructive mt-1" onclick={forceDisarm}>{t('ctrl.forceDisarm')}</Button>

  {:else if phase === 'mission'}
    <Button size="sm" class="w-full bg-amber-600 hover:bg-amber-700 text-white font-bold gap-1.5" onclick={pauseMode}>
      <Pause size={14} />{t('ctrl.pauseMission')}
    </Button>
    <Button variant="destructive" size="sm" class="w-full font-bold gap-1.5" onclick={rtl}>
      <CornerDownLeft size={14} />{t('ctrl.abortRtl')}
    </Button>
    <div class="text-[11px] text-muted-foreground font-semibold mt-1 tracking-wide uppercase">{t('ctrl.payload')}</div>
    <div class="flex gap-1.5">
      <Button size="sm" class="flex-1 bg-orange-700 hover:bg-orange-800 text-white font-bold" onclick={drop}>{t('ctrl.drop')}</Button>
      <Button size="sm" variant="secondary" class="flex-1" onclick={() => sendCommand('drop_stop')}>{t('ctrl.dropStop')}</Button>
    </div>
    <div class="text-[11px] text-muted-foreground font-semibold mt-1 tracking-wide uppercase">{t('ctrl.mode')}</div>
    <div class="flex flex-col gap-1">
      {#each app.drone.mode_btns.slice(0, 4) as [id, name]}
        <Button variant={app.drone.mode_id === id ? 'default' : 'secondary'} size="sm" class="w-full justify-start"
                onclick={() => sendCommand('mode', id)}>{name}</Button>
      {/each}
    </div>
    <Button variant="ghost" size="xs" class="w-full text-destructive mt-1" onclick={forceDisarm}>{t('ctrl.forceDisarm')}</Button>

  {:else if phase === 'returning'}
    <Button size="sm" class="w-full bg-amber-600 hover:bg-amber-700 text-white font-bold gap-1.5" onclick={pauseMode}>
      <CircleStop size={14} />{t('ctrl.cancelRtl')}
    </Button>
    <Button size="sm" class="w-full bg-teal-700 hover:bg-teal-800 text-white gap-1.5"
            onclick={() => sendCommand('mode', isPlane() ? 20 : 9)}>
      <ArrowDown size={14} />{t('ctrl.land')}
    </Button>
    <Button variant="ghost" size="xs" class="w-full text-destructive mt-2" onclick={forceDisarm}>{t('ctrl.forceDisarm')}</Button>
  {/if}
</div>
