<script lang="ts">
  import { addToast } from '../../lib/stores.svelte';
  import { sendCommand } from '../../lib/ws';
  import { t } from '../../lib/i18n.svelte';
  import { X, Clock, Calendar, Play, Trash2 } from '@lucide/svelte';
  import Button from '$lib/components/ui/button/button.svelte';

  let { onclose }: { onclose: () => void } = $props();

  const STORAGE_KEY = 'argus_schedules';

  type Frequency = 'once' | 'daily' | 'weekly' | 'custom';
  type ScheduleStatus = 'pending' | 'active' | 'completed';

  interface Schedule {
    id: number;
    name: string;
    missionName: string;
    frequency: Frequency;
    customHours: number;
    startTime: string;
    autoArm: boolean;
    status: ScheduleStatus;
  }

  let schedules: Schedule[] = $state(loadSchedules());
  let showForm = $state(false);

  let formName = $state('');
  let formMission = $state('current');
  let formFrequency: Frequency = $state('once');
  let formCustomHours = $state(24);
  let formStartTime = $state('');
  let formAutoArm = $state(false);

  let savedMissions = $derived.by(() => {
    const names: string[] = ['current'];
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key?.startsWith('argus_mission_')) {
          names.push(key.replace('argus_mission_', ''));
        }
      }
    } catch {}
    return names;
  });

  function loadSchedules(): Schedule[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return parsed;
      }
    } catch {}
    return [];
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(schedules));
    } catch {}
  }

  function addSchedule() {
    if (!formName.trim()) {
      addToast(t('sched.nameRequired'), 'warn');
      return;
    }
    if (!formStartTime) {
      addToast(t('sched.timeRequired'), 'warn');
      return;
    }
    schedules.push({
      id: Date.now(),
      name: formName.trim(),
      missionName: formMission,
      frequency: formFrequency,
      customHours: formCustomHours,
      startTime: formStartTime,
      autoArm: formAutoArm,
      status: 'pending',
    });
    persist();
    formName = '';
    formMission = 'current';
    formFrequency = 'once';
    formCustomHours = 24;
    formStartTime = '';
    formAutoArm = false;
    showForm = false;
    addToast(t('sched.created'), 'success');
  }

  function deleteSchedule(id: number) {
    const idx = schedules.findIndex(s => s.id === id);
    if (idx >= 0) {
      schedules.splice(idx, 1);
      persist();
    }
  }

  function runNow(sched: Schedule) {
    sched.status = 'active';
    persist();
    sendCommand('mission_start');
    addToast(t('sched.started'), 'success');
  }

  function fmtFreq(s: Schedule): string {
    switch (s.frequency) {
      case 'once': return t('sched.once');
      case 'daily': return t('sched.daily');
      case 'weekly': return t('sched.weekly');
      case 'custom': return `${s.customHours}h`;
    }
  }

  function statusColor(s: ScheduleStatus): string {
    switch (s) {
      case 'active': return 'text-green-400';
      case 'completed': return 'text-muted-foreground';
      default: return 'text-yellow-400';
    }
  }
</script>

<div role="dialog" aria-modal="true" tabindex="-1" class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
     onclick={(e) => { if (e.target === e.currentTarget) onclose(); }} onkeydown={(e) => { if (e.key === "Escape") onclose(); }}>
  <div class="bg-card border border-border rounded-xl shadow-2xl w-[500px] max-h-[85vh] flex flex-col overflow-hidden">

    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-border">
      <div class="flex items-center gap-2">
        <Calendar size={16} class="text-primary" />
        <h2 class="text-sm font-semibold text-primary uppercase tracking-wider">{t('sched.title')}</h2>
      </div>
      <Button variant="ghost" size="icon-xs" onclick={onclose} aria-label="Close"><X size={16} /></Button>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">

      <!-- New schedule toggle -->
      {#if !showForm}
        <Button variant="outline" class="w-full" onclick={() => showForm = true}>
          + {t('sched.new')}
        </Button>
      {:else}
        <div class="bg-muted/30 rounded-lg p-3 space-y-2">
          <!-- Name -->
          <div class="flex items-center gap-2">
            <label for="sched-name" class="text-xs text-muted-foreground w-16 shrink-0">{t('sched.name')}</label>
            <input id="sched-name" type="text" bind:value={formName} placeholder="..."
                   class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground focus:outline-none focus:ring-1 focus:ring-ring/50" />
          </div>

          <!-- Mission -->
          <div class="flex items-center gap-2">
            <label for="sched-mission" class="text-xs text-muted-foreground w-16 shrink-0">{t('sched.mission')}</label>
            <select id="sched-mission" bind:value={formMission}
                    class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground focus:outline-none focus:ring-1 focus:ring-ring/50">
              {#each savedMissions as m}
                <option value={m}>{m === 'current' ? t('sched.currentWp') : m}</option>
              {/each}
            </select>
          </div>

          <!-- Frequency -->
          <div class="flex items-center gap-2">
            <label for="sched-freq" class="text-xs text-muted-foreground w-16 shrink-0">{t('sched.frequency')}</label>
            <select id="sched-freq" bind:value={formFrequency}
                    class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground focus:outline-none focus:ring-1 focus:ring-ring/50">
              <option value="once">{t('sched.once')}</option>
              <option value="daily">{t('sched.daily')}</option>
              <option value="weekly">{t('sched.weekly')}</option>
              <option value="custom">{t('sched.custom')}</option>
            </select>
          </div>

          {#if formFrequency === 'custom'}
            <div class="flex items-center gap-2">
              <label for="sched-hours" class="text-xs text-muted-foreground w-16 shrink-0">{t('sched.interval')}</label>
              <input id="sched-hours" type="number" min="1" max="720" bind:value={formCustomHours}
                     class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground focus:outline-none focus:ring-1 focus:ring-ring/50" />
              <span class="text-xs text-muted-foreground">h</span>
            </div>
          {/if}

          <!-- Start time -->
          <div class="flex items-center gap-2">
            <label for="sched-time" class="text-xs text-muted-foreground w-16 shrink-0">{t('sched.startTime')}</label>
            <input id="sched-time" type="datetime-local" bind:value={formStartTime}
                   class="flex-1 h-7 px-2 text-xs bg-input border border-border rounded-md text-foreground focus:outline-none focus:ring-1 focus:ring-ring/50" />
          </div>

          <!-- Auto-arm -->
          <div class="flex items-center gap-2">
            <label for="sched-arm" class="text-xs text-muted-foreground w-16 shrink-0">{t('sched.autoArm')}</label>
            <input id="sched-arm" type="checkbox" bind:checked={formAutoArm}
                   class="w-4 h-4 rounded border-border text-primary focus:ring-primary" />
          </div>

          <!-- Form actions -->
          <div class="flex gap-2">
            <Button variant="default" size="sm" class="flex-1" onclick={addSchedule}>
              {t('sched.create')}
            </Button>
            <Button variant="ghost" size="sm" onclick={() => showForm = false}>
              {t('map.cancel')}
            </Button>
          </div>
        </div>
      {/if}

      <!-- Schedule list -->
      {#if schedules.length > 0}
        <div class="space-y-1">
          {#each schedules as sched (sched.id)}
            <div class="flex items-start gap-2 bg-muted/20 rounded-lg p-2 group">
              <Clock size={14} class="text-primary mt-0.5 shrink-0" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-foreground truncate">{sched.name}</span>
                  <span class="text-[10px] font-medium {statusColor(sched.status)} bg-muted/50 px-1.5 py-0.5 rounded">
                    {t(`sched.status.${sched.status}`)}
                  </span>
                </div>
                <div class="text-[11px] text-muted-foreground">
                  {sched.missionName === 'current' ? t('sched.currentWp') : sched.missionName}
                  &middot; {fmtFreq(sched)}
                  &middot; {sched.startTime.replace('T', ' ')}
                  {#if sched.autoArm}&middot; {t('sched.autoArm')}{/if}
                </div>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <button class="p-1 text-primary hover:bg-primary/10 rounded" onclick={() => runNow(sched)} title={t('sched.runNow')}>
                  <Play size={13} />
                </button>
                <button class="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-destructive hover:bg-destructive/10 rounded"
                        onclick={() => deleteSchedule(sched.id)}>
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <div class="text-xs text-muted-foreground text-center py-4 italic">
          {t('sched.empty')}
        </div>
      {/if}

      <!-- Hint -->
      <div class="p-3 rounded-lg bg-primary/5 border border-primary/20">
        <p class="text-xs text-muted-foreground leading-relaxed">
          {t('sched.hint')}
        </p>
      </div>

    </div>
  </div>
</div>
