import { describe, it, expect, beforeEach, vi } from 'vitest';
import { saveFlightRecord, loadFlightRecords, deleteFlightRecord } from './flightDb';
import type { FlightRecord } from './flightDb';

/* ── localStorage mock ── */
function makeStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v); },
    removeItem: (k: string) => { store.delete(k); },
    clear: () => store.clear(),
    get length() { return store.size; },
    key: (i: number) => [...store.keys()][i] ?? null,
  };
}

beforeEach(() => {
  vi.stubGlobal('localStorage', makeStorage());
});

const SAMPLE: Omit<FlightRecord, 'id'> = {
  date: '2026-05-21',
  duration: 300,
  maxAlt: 100,
  maxSpeed: 15,
  totalDist: 5000,
  batUsed: 2400,
  vtype: 'copter',
  fw: '4.5.7',
  eventCount: 3,
};

describe('flightDb', () => {
  it('starts with an empty record list', () => {
    expect(loadFlightRecords()).toEqual([]);
  });

  it('saves and loads a flight record with auto-incrementing id', () => {
    saveFlightRecord(SAMPLE);
    const records = loadFlightRecords();
    expect(records.length).toBe(1);
    expect(records[0].id).toBe(1);
    expect(records[0].date).toBe('2026-05-21');
    expect(records[0].duration).toBe(300);
  });

  it('assigns incrementing ids across multiple saves', () => {
    saveFlightRecord(SAMPLE);
    saveFlightRecord({ ...SAMPLE, date: '2026-05-22' });
    const records = loadFlightRecords();
    expect(records.length).toBe(2);
    expect(records[0].id).toBe(1);
    expect(records[1].id).toBe(2);
  });

  it('deletes a record by id', () => {
    saveFlightRecord(SAMPLE);
    saveFlightRecord({ ...SAMPLE, date: '2026-05-22' });
    const before = loadFlightRecords();
    deleteFlightRecord(before[0].id);
    const after = loadFlightRecords();
    expect(after.length).toBe(1);
    expect(after[0].date).toBe('2026-05-22');
  });

  it('caps records at 200 entries, dropping oldest', () => {
    for (let i = 0; i < 205; i++) {
      saveFlightRecord({ ...SAMPLE, date: `2026-01-${String(i + 1).padStart(3, '0')}` });
    }
    const records = loadFlightRecords();
    expect(records.length).toBe(200);
    // The first 5 should have been pruned — earliest remaining should be day 006
    expect(records[0].date).toBe('2026-01-006');
  });
});
