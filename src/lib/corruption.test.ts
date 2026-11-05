import { describe, it, expect, vi, beforeEach } from 'vitest';
import { loadSettings, app } from './stores.svelte';

function makeStorage(init?: Record<string, string>): Storage {
  const store = new Map<string, string>(init ? Object.entries(init) : []);
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

beforeEach(() => {
  vi.stubGlobal('localStorage', makeStorage());
  vi.stubGlobal('requestAnimationFrame', (cb: () => void) => cb());
  app.waypoints = [];
  app.undoStack = [];
});

// ---------------------------------------------------------------------------
// loadSettings — corrupted argus_settings
// ---------------------------------------------------------------------------

describe('loadSettings with corrupted argus_settings', () => {
  it('handles invalid JSON string', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: '{not valid json!!!',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
  });

  it('handles completely empty string', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: '',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
  });

  it('handles null string literal', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: 'null',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
  });

  it('handles number string instead of object', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: '42',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
  });

  it('handles array instead of object', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: '[1, 2, 3]',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
  });

  it('handles wrong types for known keys', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: '{"alt":"not-a-number","dark":"yes","region":999}',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
  });

  it('handles extremely long JSON string', () => {
    const huge = JSON.stringify({ alt: 50, junk: 'x'.repeat(100_000) });
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: huge,
      }),
    );
    expect(() => loadSettings()).not.toThrow();
    expect(app.defaultAlt).toBe(50);
  });

  it('preserves defaults when settings JSON is broken', () => {
    const altBefore = app.defaultAlt;
    const speedBefore = app.defaultSpeed;
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: '%%%CORRUPT%%%',
      }),
    );
    loadSettings();
    expect(app.defaultAlt).toBe(altBefore);
    expect(app.defaultSpeed).toBe(speedBefore);
  });
});

// ---------------------------------------------------------------------------
// loadSettings — corrupted argus_waypoints
// ---------------------------------------------------------------------------

describe('loadSettings with corrupted argus_waypoints', () => {
  it('handles invalid JSON for waypoints', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_waypoints: '{broken',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
    expect(app.waypoints).toEqual([]);
  });

  it('handles non-array JSON for waypoints', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_waypoints: '{"not":"an array"}',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
    expect(app.waypoints).toEqual([]);
  });

  it('handles null literal for waypoints', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_waypoints: 'null',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
    expect(app.waypoints).toEqual([]);
  });

  it('handles empty string for waypoints', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_waypoints: '',
      }),
    );
    expect(() => loadSettings()).not.toThrow();
    expect(app.waypoints).toEqual([]);
  });
});
