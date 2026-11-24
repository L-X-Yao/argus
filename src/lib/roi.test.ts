import { describe, expect, it } from 'vitest';
import { normalizePickedPoint, inverseMapPoint, validRoiInput } from './roi';
import { toWgs } from './gcj02';

describe('ROI input', () => {
  it('rejects invalid coordinates and non-finite altitude before any pending ACK is recorded', () => {
    expect(validRoiInput(999, 108.9, 30)).toBe(false);
    expect(validRoiInput(34.2, 190, 30)).toBe(false);
    expect(validRoiInput(34.2, 108.9, Number.NaN)).toBe(false);
    expect(validRoiInput(null, 108.9, 30)).toBe(false);
    expect(validRoiInput(34.2, 108.9, 30)).toBe(true);
  });

  it('normalizes a repeated-world pick before it reaches ROI state', () => {
    const picked = normalizePickedPoint(34.2, 190);
    expect(picked).toEqual({ lat: 34.2, lon: -170 });
    expect(validRoiInput(picked.lat, picked.lon, 30)).toBe(true);
    expect(validRoiInput(34.2, 190, 30)).toBe(false);
  });

  it('normalizes the raw map longitude before a nonlinear inverse transform', () => {
    let seenLon = 0;
    inverseMapPoint(34.258, 468.942, (lat, lon) => {
      seenLon = lon;
      return [lat, lon];
    });
    expect(seenLon).toBeCloseTo(108.942, 12);

    const direct = inverseMapPoint(34.258, 108.942, toWgs);
    const repeated = inverseMapPoint(34.258, 108.942 + 360, toWgs);
    expect(repeated[0]).toBeCloseTo(direct[0], 12);
    expect(repeated[1]).toBeCloseTo(direct[1], 12);
  });
});
