<script lang="ts">
  // A change the AI assistant asks for, waiting for the operator (src/lib/assistant.svelte.ts).
  // It sits beside the map rather than over it: a proposed route is drawn there while it waits.
  // No key approves it, so that a key meant for something else cannot.
  import { assistant, approve, decline, type Proposal } from '../../lib/assistant.svelte';
  import { totalDist } from '../../lib/missionIO';
  import { t } from '../../lib/i18n.svelte';
  import { app } from '../../lib/stores.svelte';
  import { vehicleKind } from '../../lib/vehicleModes';
  import Button from '$lib/components/ui/button/button.svelte';
  import { Bot } from '@lucide/svelte';

  let current: Proposal | undefined = $derived(assistant.queue[0]);

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
              ><th class="text-right"></th></tr
            >
          </thead>
          <tbody>
            {#each current.waypoints as wp, i (i)}
              <tr>
                <td>{i + 1}</td>
                <td>{coord(wp.lat)}</td>
                <td>{coord(wp.lon)}</td>
                <td class="text-right">{wp.alt}</td>
                <td class="text-right text-muted-foreground">{wp.type === 'wp' ? '' : wp.type}</td>
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
        disabled={assistant.running || !app.drone.connected || app.drone.armed}
        onclick={() => approve(current!.id)}
        data-testid="assistant-approve">{assistant.running ? t('assistant.running') : t('assistant.approve')}</Button
      >
    </div>
  </div>
{/if}
