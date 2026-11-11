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

  it('keeps its own value where a known key has the wrong type', () => {
    const before = {
      alt: app.defaultAlt,
      speed: app.defaultSpeed,
      radius: app.geoRadius,
      dark: app.darkTheme,
      muted: app.audioMuted,
      region: app.mapRegion,
      tileSource: app.tileSource,
    };
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_settings: JSON.stringify({
          alt: '<img src=x onerror=alert(1)>',
          speed: 'fast',
          radius: 0,
          dark: 'yes',
          muted: 1,
          region: 999,
          tileSource: { toString: 'x' },
        }),
      }),
    );
    expect(() => loadSettings()).not.toThrow();
    expect({
      alt: app.defaultAlt,
      speed: app.defaultSpeed,
      radius: app.geoRadius,
      dark: app.darkTheme,
      muted: app.audioMuted,
      region: app.mapRegion,
      tileSource: app.tileSource,
    }).toEqual(before);
  });

  it('keeps an altitude below zero: a submarine has one', () => {
    vi.stubGlobal('localStorage', makeStorage({ argus_settings: '{"alt":-5}' }));
    loadSettings();
    expect(app.defaultAlt).toBe(-5);
    app.defaultAlt = 30;
  });

  it('reads a number that was stored as text', () => {
    vi.stubGlobal('localStorage', makeStorage({ argus_settings: '{"alt":"80","speed":"12"}' }));
    loadSettings();
    expect(app.defaultAlt).toBe(80);
    expect(app.defaultSpeed).toBe(12);
    app.defaultAlt = 30;
    app.defaultSpeed = 5;
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

// ---------------------------------------------------------------------------
// loadSettings — stored routes that are not routes
// ---------------------------------------------------------------------------

// The map writes these fields into HTML, and the panels call number methods on them: a stored
// list that is restored as it stands breaks the page again at every start.
describe('loadSettings with stored points of the wrong type', () => {
  const MARKUP = '<img src=x onerror="window.__argus_xss=1">';
  const point = { lat: 34.25, lon: 108.94, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 };

  beforeEach(() => {
    app.fencePolygon = [];
    app.rallyPoints = [];
  });

  it('restores a list that Argus saved', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({
        argus_waypoints: JSON.stringify([point, { ...point, lat: 34.26 }]),
        argus_fence: JSON.stringify([
          { lat: 1, lon: 2 },
          { lat: 3, lon: 4 },
          { lat: 5, lon: 6 },
        ]),
        argus_rally: JSON.stringify([{ lat: 7, lon: 8, alt: 90 }]),
      }),
    );
    loadSettings();
    expect(app.waypoints).toEqual([point, { ...point, lat: 34.26 }]);
    expect(app.fencePolygon).toHaveLength(3);
    expect(app.rallyPoints).toEqual([{ lat: 7, lon: 8, alt: 90 }]);
  });

  it.each(['lat', 'alt', 'delay', 'speed', 'loiter_param'])('restores no waypoints when %s holds markup', (field) => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({ argus_waypoints: JSON.stringify([point, { ...point, [field]: MARKUP }]) }),
    );
    app.toasts = [];
    expect(() => loadSettings()).not.toThrow();
    expect(app.waypoints).toEqual([]);
    // And says so: a route that is just gone at the next start is the worse surprise.
    expect(app.toasts.map((toast) => [toast.level, toast.text.includes('argus_waypoints')])).toEqual([['error', true]]);
  });

  it('says nothing when there is nothing wrong', () => {
    vi.stubGlobal('localStorage', makeStorage({ argus_waypoints: JSON.stringify([point]) }));
    app.toasts = [];
    loadSettings();
    expect(app.toasts).toEqual([]);
  });

  // What v3.7.10 stored for a point set on a repeated copy of the world.
  it('restores a route with a longitude past the date line, on the same meridian', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({ argus_waypoints: JSON.stringify([point, { ...point, lon: -251.06 }]) }),
    );
    loadSettings();
    expect(app.waypoints).toHaveLength(2);
    expect(app.waypoints[1].lon).toBeCloseTo(108.94, 9);
  });

  it('restores numbers for waypoint fields stored as text', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({ argus_waypoints: JSON.stringify([{ ...point, lat: '34.25', alt: '50' }]) }),
    );
    loadSettings();
    expect(app.waypoints).toEqual([point]);
  });

  it('restores no fence when a corner is not a point', () => {
    vi.stubGlobal(
      'localStorage',
      makeStorage({ argus_fence: JSON.stringify([{ lat: 1, lon: 2 }, { lat: MARKUP, lon: 4 }, 'x']) }),
    );
    expect(() => loadSettings()).not.toThrow();
    expect(app.fencePolygon).toEqual([]);
  });

  it('restores no rally points when an altitude holds markup', () => {
    vi.stubGlobal('localStorage', makeStorage({ argus_rally: JSON.stringify([{ lat: 7, lon: 8, alt: MARKUP }]) }));
    expect(() => loadSettings()).not.toThrow();
    expect(app.rallyPoints).toEqual([]);
  });
});
