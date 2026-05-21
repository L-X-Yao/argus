import { describe, it, expect } from 'vitest';
import { generateSurveyGrid, polygonArea } from './survey';

const SQUARE = [
  { lat: 34.258, lon: 108.942 },
  { lat: 34.259, lon: 108.942 },
  { lat: 34.259, lon: 108.943 },
  { lat: 34.258, lon: 108.943 },
];

describe('generateSurveyGrid', () => {
  it('generates waypoints for a valid polygon', () => {
    const wps = generateSurveyGrid(SQUARE, { angle: 0, spacing: 20, alt: 50, overshoot: 5 });
    expect(wps.length).toBeGreaterThan(0);
    for (const wp of wps) {
      expect(wp.alt).toBe(50);
      expect(wp.type).toBe('wp');
      expect(wp.drop).toBe(false);
    }
  });

  it('returns empty for less than 3 vertices', () => {
    expect(generateSurveyGrid([], { angle: 0, spacing: 20, alt: 50, overshoot: 0 })).toEqual([]);
    expect(generateSurveyGrid([SQUARE[0], SQUARE[1]], { angle: 0, spacing: 20, alt: 50, overshoot: 0 })).toEqual([]);
  });

  it('spacing affects waypoint count', () => {
    const dense = generateSurveyGrid(SQUARE, { angle: 0, spacing: 10, alt: 30, overshoot: 0 });
    const sparse = generateSurveyGrid(SQUARE, { angle: 0, spacing: 50, alt: 30, overshoot: 0 });
    expect(dense.length).toBeGreaterThan(sparse.length);
  });

  it('produces serpentine pattern', () => {
    const wps = generateSurveyGrid(SQUARE, { angle: 0, spacing: 30, alt: 40, overshoot: 0 });
    if (wps.length >= 4) {
      const first2 = wps[1].lon - wps[0].lon;
      const next2 = wps[3].lon - wps[2].lon;
      expect(Math.sign(first2)).toBe(-Math.sign(next2));
    }
  });

  it('angle rotates grid pattern', () => {
    const a0 = generateSurveyGrid(SQUARE, { angle: 0, spacing: 20, alt: 30, overshoot: 0 });
    const a45 = generateSurveyGrid(SQUARE, { angle: 45, spacing: 20, alt: 30, overshoot: 0 });
    expect(a0.length).not.toBe(a45.length);
  });
});

describe('polygonArea', () => {
  it('computes area for a ~100m square', () => {
    const side = 100;
    const sq = [
      { lat: 34.258, lon: 108.942 },
      { lat: 34.258 + side / 111320, lon: 108.942 },
      { lat: 34.258 + side / 111320, lon: 108.942 + side / (111320 * Math.cos(34.258 * Math.PI / 180)) },
      { lat: 34.258, lon: 108.942 + side / (111320 * Math.cos(34.258 * Math.PI / 180)) },
    ];
    const area = polygonArea(sq);
    expect(area).toBeGreaterThan(9000);
    expect(area).toBeLessThan(11000);
  });

  it('returns 0 for fewer than 3 points', () => {
    expect(polygonArea([])).toBe(0);
    expect(polygonArea([{ lat: 0, lon: 0 }])).toBe(0);
  });
});
