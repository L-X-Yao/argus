import { describe, it, expect } from 'vitest';
import { exportWaypoints, importWaypoints, exportQgcPlan, importQgcPlan, exportGpx, autoImport } from './missionIO';
import type { Waypoint } from './types';

const sampleWps: Waypoint[] = [
  { lat: 34.258, lon: 108.942, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 },
  { lat: 34.259, lon: 108.943, alt: 60, drop: false, delay: 5, speed: 0, type: 'wp', loiter_param: 0 },
  { lat: 34.260, lon: 108.944, alt: 50, drop: false, delay: 0, speed: 0, type: 'loiter_turns', loiter_param: 3 },
];

describe('Mission Planner .waypoints', () => {
  it('roundtrip export → import preserves waypoints', () => {
    const text = exportWaypoints(sampleWps);
    const imported = importWaypoints(text);
    expect(imported.length).toBe(3);
    expect(imported[0].lat).toBeCloseTo(34.258, 5);
    expect(imported[1].delay).toBe(5);
    expect(imported[2].type).toBe('loiter_turns');
    expect(imported[2].loiter_param).toBe(3);
  });

  it('export starts with QGC WPL 110 header', () => {
    const text = exportWaypoints(sampleWps);
    expect(text.startsWith('QGC WPL 110')).toBe(true);
  });
});

describe('QGC .plan JSON', () => {
  it('roundtrip export → import preserves waypoints', () => {
    const json = exportQgcPlan(sampleWps);
    const imported = importQgcPlan(json);
    expect(imported.length).toBe(3);
    expect(imported[0].lat).toBeCloseTo(34.258, 5);
    expect(imported[1].alt).toBe(60);
  });

  it('export has correct structure', () => {
    const plan = JSON.parse(exportQgcPlan(sampleWps));
    expect(plan.fileType).toBe('Plan');
    expect(plan.groundStation).toBe('PL-Link GCS');
    expect(plan.mission.items.length).toBe(3);
  });
});

describe('GPX format', () => {
  it('export produces valid XML', () => {
    const gpx = exportGpx(sampleWps);
    expect(gpx).toContain('<gpx');
    expect(gpx).toContain('rtept');
    expect(gpx).toContain('34.258');
  });
});

describe('autoImport', () => {
  it('detects .waypoints format', () => {
    const text = exportWaypoints(sampleWps);
    const wps = autoImport(text, 'mission.waypoints');
    expect(wps.length).toBe(3);
  });

  it('detects .plan format', () => {
    const text = exportQgcPlan(sampleWps);
    const wps = autoImport(text, 'mission.plan');
    expect(wps.length).toBe(3);
  });
});
