import { describe, it, expect, vi } from 'vitest';

// backend.ts accesses `window` at module scope — stub before import
vi.stubGlobal('window', { location: { protocol: 'http:', host: 'localhost' } });

const { interpolateRoute } = await import('./terrain');

describe('interpolateRoute', () => {
  it('returns single point for a single waypoint', () => {
    const result = interpolateRoute([{ lat: 34.258, lon: 108.942 }]);
    expect(result.length).toBe(1);
    expect(result[0].wpIndex).toBe(0);
    expect(result[0].lat).toBe(34.258);
    expect(result[0].lon).toBe(108.942);
  });

  it('returns empty array for empty input', () => {
    expect(interpolateRoute([])).toEqual([]);
  });

  it('creates intermediate points between two waypoints', () => {
    // Two waypoints ~1.1 km apart (0.01 deg lat at 34 N ~ 1113m)
    const wps = [
      { lat: 34.258, lon: 108.942 },
      { lat: 34.268, lon: 108.942 },
    ];
    const result = interpolateRoute(wps, 50);
    // ~1113m / 50m step = ~23 steps, plus the final waypoint
    expect(result.length).toBeGreaterThan(10);
    // First point matches first waypoint
    expect(result[0].lat).toBe(wps[0].lat);
    expect(result[0].lon).toBe(wps[0].lon);
    expect(result[0].wpIndex).toBe(0);
    // Last point matches last waypoint
    const last = result[result.length - 1];
    expect(last.lat).toBe(wps[1].lat);
    expect(last.lon).toBe(wps[1].lon);
    expect(last.wpIndex).toBe(1);
  });

  it('intermediate points have wpIndex -1', () => {
    const wps = [
      { lat: 34.258, lon: 108.942 },
      { lat: 34.268, lon: 108.942 },
    ];
    const result = interpolateRoute(wps, 50);
    const intermediates = result.filter(p => p.wpIndex === -1);
    expect(intermediates.length).toBeGreaterThan(0);
  });

  it('larger step size produces fewer points', () => {
    const wps = [
      { lat: 34.258, lon: 108.942 },
      { lat: 34.268, lon: 108.942 },
    ];
    const fine = interpolateRoute(wps, 25);
    const coarse = interpolateRoute(wps, 200);
    expect(fine.length).toBeGreaterThan(coarse.length);
  });

  it('handles three-waypoint route correctly', () => {
    const wps = [
      { lat: 34.258, lon: 108.942 },
      { lat: 34.260, lon: 108.942 },
      { lat: 34.260, lon: 108.944 },
    ];
    const result = interpolateRoute(wps, 100);
    // Should have waypoint indices 0, 1, 2 somewhere in the result
    const wpIndices = result.filter(p => p.wpIndex >= 0).map(p => p.wpIndex);
    expect(wpIndices).toContain(0);
    expect(wpIndices).toContain(1);
    expect(wpIndices).toContain(2);
  });
});
