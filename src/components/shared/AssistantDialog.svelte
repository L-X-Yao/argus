<script lang="ts">
  // A change the AI assistant asks for, waiting for the operator (src/lib/assistant.svelte.ts).
  // It sits beside the map rather than over it: a proposed route is drawn there while it waits.
  // No key approves it, so that a key meant for something else cannot. Everything the upload
  // does with a waypoint is shown: speed, hold and circling change the flight as much as a place.
  import { assistant, approve, decline, type Proposal } from '../../lib/assistant.svelte';
  import type { Waypoint } from '../../lib/types';
  import { totalDist } from '../../lib/missionIO';
  import { t } from '../../lib/i18n.svelte';
  import { app } from '../../lib/stores.svelte';
  import { vehicleKind } from '../../lib/vehicleModes';
  import Button from '$lib/components/ui/button/button.svelte';
  import { Bot } from '@lucide/svelte';

  let current: Proposal | undefined = $derived(assistant.queue[0]);

  // When another proposal takes the place of the one shown (withdrawn, timed out), a click
  // already on its way must not approve what nobody has read. Approve waits a moment.
  const READ_FIRST_MS = 1500;
  let readable = $state(false);
  $effect(() => {
    if (!current?.id) return;
    readable = false;
    const timer = setTimeout(() => (readable = true), READ_FIRST_MS);
    return () => clearTimeout(timer);
  });

  /** What the upload does at a waypoint besides flying to it. */
  function details(wp: Waypoint): string {
    const parts: string[] = [];
    const n = (key: string, value: number) => t(key).replace('{n}', String(value));
    if (wp.type === 'loiter_time') parts.push(n('assistant.loiterTime', wp.loiter_param));
    if (wp.type === 'loiter_turns') parts.push(n('assistant.loiterTurns', wp.loiter_param));
    if (wp.type === 'spline') parts.push(t('assistant.spline'));
    if (wp.delay > 0) parts.push(n('assistant.hold', wp.delay));
    if (wp.speed > 0) parts.push(n('assistant.speed', wp.speed));
    return parts.join(' · ');
  }

  function summary(p: Proposal): string {
    if (p.kind !== 'propose_mission') return '';
    const alts = p.waypoints.map((w) => w.alt);
    const sub = vehicleKind() === 'sub';
    return t(sub ? 'assistant.missionSummarySub' : 'assistant.missionSummary')
      .replace('{n}', String(p.waypoints.length))
      .replace('{dist}', totalDist(p.waypoints))
      .replace('{alt}', String(sub ? Math.min(...alts) : Math.max(...alts)))
      .replace('{takeoff}', String(p.takeoffAlt));
  }

  const coord = (v: number) => v.toFixed(6);
</script>

{#if current}
  <div
    class="fixed top-14 right-3 z-[1500] w-[400px] max-w-[calc(100vw-1.5rem)] max-h-[70vh] flex flex-col bg-card border-2 border-primary/60 rounded-xl shadow-2xl"
    role="dialog"
    aria-labelledby="assistant-title"
    data-testid="assistant-dialog"
  >
    <div class="flex items-center gap-2 px-4 pt-3 pb-2 border-b border-border">
      <Bot size={18} class="text-primary shrink-0" />
      <h2 id="assistant-title" class="text-sm font-bold text-foreground">{t('assistant.title')}</h2>
      {#if assistant.queue.length > 1}
        <span class="ml-auto text-[11px] text-muted-foreground"
          >{t('assistant.more').replace('{n}', String(assistant.queue.length - 1))}</span
        >
      {/if}
    </div>

    <div class="px-4 py-3 overflow-y-auto text-xs space-y-2">
      {#if current.kind === 'propose_mission'}
        <p class="font-semibold text-foreground">{t('assistant.missionTitle')}</p>
        <p class="text-muted-foreground">{summary(current)} {t('assistant.onMap')}</p>
        <table class="w-full font-mono text-[11px]">
          <thead class="text-muted-foreground">
            <tr
              ><th class="text-left">#</th><th class="text-left">lat</th><th class="text-left">lon</th><th
                class="text-right">m</th
              ><th class="text-left"></th></tr
            >
          </thead>
          <tbody>
            {#each current.waypoints as wp, i (i)}
              <tr>
                <td>{i + 1}</td>
                <td>{coord(wp.lat)}</td>
                <td>{coord(wp.lon)}</td>
                <td class="text-right">{wp.alt}</td>
                <td class="pl-2 text-warning">{details(wp)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="font-semibold text-foreground">{t('assistant.paramsTitle')}</p>
        <table class="w-full font-mono text-[11px]">
          <thead class="text-muted-foreground">
            <tr
              ><th class="text-left">{t('assistant.param')}</th><th class="text-right">{t('assistant.now')}</th><th
                class="text-right">{t('assistant.new')}</th
              ></tr
            >
          </thead>
          <tbody>
            {#each current.changes as change (change.name)}
              <tr>
                <td>{change.name}</td>
                <td class="text-right">{change.from}</td>
                <td class="text-right font-bold {change.from === change.to ? 'text-muted-foreground' : 'text-warning'}"
                  >{change.from === change.to ? t('assistant.unchanged') : change.to}</td
                >
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}

      {#if current.reason}
        <div class="border-l-2 border-border pl-2">
          <p class="text-[10px] uppercase tracking-wide text-muted-foreground">{t('assistant.reason')}</p>
          <p class="text-foreground whitespace-pre-line break-words">{current.reason}</p>
        </div>
      {/if}
    </div>

    <div class="flex gap-2 px-4 pb-3 pt-2 border-t border-border">
      <Button
        variant="outline"
        size="sm"
        class="flex-1"
        disabled={assistant.running}
        onclick={() => decline(current!.id)}
        data-testid="assistant-decline">{t('assistant.decline')}</Button
      >
      <Button
        size="sm"
        class="flex-1"
        disabled={!readable || assistant.running || !app.drone.connected || app.drone.armed}
        onclick={() => approve(current!.id)}
        data-testid="assistant-approve">{assistant.running ? t('assistant.running') : t('assistant.approve')}</Button
      >
    </div>
  </div>
{/if}
