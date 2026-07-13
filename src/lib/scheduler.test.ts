// advanceSchedule catch-up logic — the piece of the scheduler most likely to
// misfire: a long-closed GCS must not replay every missed occurrence, and the
// next due time must stay on the original time-of-day grid.
import { describe, expect, it } from 'vitest';

import { advanceSchedule, type Schedule } from './scheduler.svelte';

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
