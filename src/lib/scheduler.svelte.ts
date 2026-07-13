/**
 * App-level mission scheduler — ticks for the whole GCS session, not just
 * while SchedulerPanel is open (the panel is only a UI over this store).
 *
 * Safety model: a due schedule NEVER auto-starts the mission. Every firing
 * pops the standard confirm dialog (repo convention: every call path to
 * mission_start guards on confirm) — the scheduler is a reminder + one-click
 * runner, not an unattended autostart.
 */

import { app, addToast, showConfirm } from './stores.svelte';
import { dispatch } from './transport';
import { t } from './i18n.svelte';

export type Frequency = 'once' | 'daily' | 'weekly' | 'custom';
export type ScheduleStatus = 'pending' | 'completed';

export interface Schedule {
  id: number;
  name: string;
  frequency: Frequency;
  customHours: number;
  /** datetime-local string, e.g. "2026-07-13T18:30" */
  startTime: string;
  autoArm: boolean;
  status: ScheduleStatus;
}

const STORAGE_KEY = 'argus_schedules';
const TICK_MS = 15000;

export const schedulerState = $state({ schedules: [] as Schedule[] });

function load(): Schedule[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      // Drop the legacy missionName field (saved-mission slots never existed)
      // and the legacy 'active' status.
      if (Array.isArray(parsed)) {
        return parsed.map((s) => ({
          id: s.id,
          name: s.name,
          frequency: s.frequency ?? 'once',
          customHours: s.customHours ?? 24,
          startTime: s.startTime ?? '',
          autoArm: !!s.autoArm,
          status: s.status === 'completed' ? 'completed' : 'pending',
        }));
      }
    }
  } catch {
    /* corrupted storage — start empty */
  }
  return [];
}

export function persistSchedules(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(schedulerState.schedules));
  } catch {
    /* quota/private mode — schedule stays in memory */
  }
}

export function addSchedule(s: Omit<Schedule, 'id' | 'status'>): void {
  schedulerState.schedules.push({ ...s, id: Date.now(), status: 'pending' });
  persistSchedules();
}

export function deleteSchedule(id: number): void {
  const idx = schedulerState.schedules.findIndex((s) => s.id === id);
  if (idx >= 0) {
    schedulerState.schedules.splice(idx, 1);
    persistSchedules();
  }
}

function fmtLocal(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Advance a repeating schedule past `now` (catch-up so a long-closed GCS
 * doesn't replay every missed occurrence); mark 'once' completed. */
export function advanceSchedule(s: Schedule, now: number): void {
  if (s.frequency === 'once') {
    s.status = 'completed';
    return;
  }
  const stepMs =
    s.frequency === 'daily'
      ? 24 * 3600_000
      : s.frequency === 'weekly'
        ? 7 * 24 * 3600_000
        : Math.max(1, s.customHours) * 3600_000;
  let due = Date.parse(s.startTime);
  while (due <= now) due += stepMs;
  s.startTime = fmtLocal(due);
}

/** Confirm-gated firing shared by the timer and the panel's run-now button. */
export async function fireSchedule(s: Schedule): Promise<void> {
  const note = s.autoArm ? t('sched.withAutoArm') : '';
  const ok = await showConfirm(`${s.name}: ${t('sched.confirmRun')}${note}`, true);
  if (!ok) {
    addToast(t('sched.skippedDeclined'), 'info');
    return;
  }
  if (s.autoArm && !app.drone.armed) {
    dispatch('arm');
    // Give the FC a moment to arm before AUTO — same fire-and-observe model
    // as the manual flow (any failure surfaces via cmd_ack/statustext events).
    await new Promise((r) => setTimeout(r, 2000));
  }
  dispatch('mission_start');
  addToast(t('sched.started'), 'success');
}

let timer: ReturnType<typeof setInterval> | null = null;
let firing = false;

async function tick(): Promise<void> {
  if (firing) return; // a confirm dialog is already up — don't stack
  const now = Date.now();
  for (const s of schedulerState.schedules) {
    if (s.status !== 'pending') continue;
    const due = Date.parse(s.startTime);
    if (Number.isNaN(due) || now < due) continue;
    if (!app.drone.connected) {
      addToast(`${s.name}: ${t('sched.skippedOffline')}`, 'warn', 6000);
      advanceSchedule(s, now);
      persistSchedules();
      continue;
    }
    firing = true;
    try {
      await fireSchedule(s);
    } finally {
      firing = false;
    }
    advanceSchedule(s, now);
    persistSchedules();
  }
}

export function startScheduler(): void {
  if (timer) return;
  schedulerState.schedules = load();
  timer = setInterval(() => void tick(), TICK_MS);
}

export function stopScheduler(): void {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}
