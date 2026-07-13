// Scheduler service — advance/catch-up math plus the fire/tick paths.
// The tick loop and confirm-gated firing are the safety-relevant bits: a due
// schedule must NEVER start a mission without a confirmed dialog.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./stores.svelte', () => ({
  app: { drone: { connected: true, armed: false } },
  addToast: vi.fn(),
  showConfirm: vi.fn(async () => true),
}));
vi.mock('./transport', () => ({
  dispatch: vi.fn(),
}));
vi.mock('./i18n.svelte', () => ({
  t: (k: string) => k,
}));

import { app, addToast, showConfirm } from './stores.svelte';
import { dispatch } from './transport';
import {
  advanceSchedule,
  fireSchedule,
  schedulerState,
  startScheduler,
  stopScheduler,
  type Schedule,
} from './scheduler.svelte';

// Node test env has no localStorage — same stub pattern as migrate.test.ts.
function makeStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => store.clear(),
    get length() {
      return store.size;
    },
    key: (i: number) => [...store.keys()][i] ?? null,
  };
}
vi.stubGlobal('localStorage', makeStorage());

function sched(overrides: Partial<Schedule>): Schedule {
  return {
    id: 1,
    name: 't',
    frequency: 'once',
    customHours: 24,
    startTime: '2026-07-10T08:00',
    autoArm: false,
    status: 'pending',
    ...overrides,
  };
}

describe('advanceSchedule', () => {
  it('marks once schedules completed', () => {
    const s = sched({ frequency: 'once' });
    advanceSchedule(s, Date.parse('2026-07-10T08:01'));
    expect(s.status).toBe('completed');
    expect(s.startTime).toBe('2026-07-10T08:00'); // untouched
  });

  it('daily advances to the next future occurrence, same time of day', () => {
    const s = sched({ frequency: 'daily' });
    advanceSchedule(s, Date.parse('2026-07-10T08:01'));
    expect(s.startTime).toBe('2026-07-11T08:00');
    expect(s.status).toBe('pending');
  });

  it('catch-up skips all missed occurrences instead of replaying them', () => {
    const s = sched({ frequency: 'daily' });
    // GCS closed for 5 days — next due must be tomorrow relative to now,
    // not five stacked firings.
    advanceSchedule(s, Date.parse('2026-07-15T09:30'));
    expect(s.startTime).toBe('2026-07-16T08:00');
  });

  it('weekly steps in 7-day increments', () => {
    const s = sched({ frequency: 'weekly' });
    advanceSchedule(s, Date.parse('2026-07-10T08:01'));
    expect(s.startTime).toBe('2026-07-17T08:00');
  });

  it('custom uses customHours and clamps to >=1h', () => {
    const s = sched({ frequency: 'custom', customHours: 6 });
    advanceSchedule(s, Date.parse('2026-07-10T08:01'));
    expect(s.startTime).toBe('2026-07-10T14:00');

    const bad = sched({ frequency: 'custom', customHours: 0 });
    advanceSchedule(bad, Date.parse('2026-07-10T08:01'));
    expect(bad.startTime).toBe('2026-07-10T09:00');
  });

  it('due exactly at now still advances (no same-minute refire loop)', () => {
    const s = sched({ frequency: 'daily' });
    advanceSchedule(s, Date.parse('2026-07-10T08:00'));
    expect(s.startTime).toBe('2026-07-11T08:00');
  });
});

describe('fireSchedule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    app.drone.connected = true;
    app.drone.armed = false;
  });

  it('starts the mission only after a confirmed dialog', async () => {
    await fireSchedule(sched({}));
    expect(showConfirm).toHaveBeenCalledOnce();
    expect(dispatch).toHaveBeenCalledWith('mission_start');
  });

  it('declined confirm sends nothing', async () => {
    vi.mocked(showConfirm).mockResolvedValueOnce(false);
    await fireSchedule(sched({}));
    expect(dispatch).not.toHaveBeenCalled();
    expect(addToast).toHaveBeenCalledWith('sched.skippedDeclined', 'info');
  });

  it('autoArm arms first (2s settle) then starts', async () => {
    vi.useFakeTimers();
    const p = fireSchedule(sched({ autoArm: true }));
    await vi.advanceTimersByTimeAsync(2000);
    await p;
    vi.useRealTimers();
    expect(vi.mocked(dispatch).mock.calls.map((c) => c[0])).toEqual(['arm', 'mission_start']);
  });

  it('autoArm skips arming when already armed', async () => {
    app.drone.armed = true;
    await fireSchedule(sched({ autoArm: true }));
    expect(vi.mocked(dispatch).mock.calls.map((c) => c[0])).toEqual(['mission_start']);
  });
});

describe('scheduler tick', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    localStorage.clear();
    app.drone.connected = true;
    app.drone.armed = false;
  });

  afterEach(() => {
    stopScheduler();
    vi.useRealTimers();
    localStorage.clear();
  });

  function seed(s: Partial<Schedule>) {
    localStorage.setItem('argus_schedules', JSON.stringify([sched(s)]));
  }

  it('fires a due schedule through the confirm gate and completes it', async () => {
    seed({ startTime: '2020-01-01T00:00' }); // long overdue
    startScheduler();
    expect(schedulerState.schedules).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(15000);
    expect(showConfirm).toHaveBeenCalledOnce();
    expect(dispatch).toHaveBeenCalledWith('mission_start');
    expect(schedulerState.schedules[0].status).toBe('completed');
  });

  it('skips (and still advances) when no vehicle is connected', async () => {
    app.drone.connected = false;
    seed({ startTime: '2020-01-01T00:00' });
    startScheduler();
    await vi.advanceTimersByTimeAsync(15000);
    expect(dispatch).not.toHaveBeenCalled();
    expect(showConfirm).not.toHaveBeenCalled();
    expect(schedulerState.schedules[0].status).toBe('completed');
  });

  it('does not fire schedules that are not yet due', async () => {
    seed({ startTime: '2099-01-01T00:00' });
    startScheduler();
    await vi.advanceTimersByTimeAsync(15000);
    expect(showConfirm).not.toHaveBeenCalled();
    expect(schedulerState.schedules[0].status).toBe('pending');
  });

  it('load() drops the legacy missionName field and active status', () => {
    localStorage.setItem(
      'argus_schedules',
      JSON.stringify([{ id: 5, name: 'legacy', missionName: 'x', status: 'active', startTime: '2026-01-01T00:00' }]),
    );
    startScheduler();
    const s = schedulerState.schedules[0];
    expect(s.status).toBe('pending');
    expect('missionName' in s).toBe(false);
    expect(s.frequency).toBe('once');
  });
});
