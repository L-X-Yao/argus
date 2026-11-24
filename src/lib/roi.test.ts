import { describe, expect, it } from 'vitest';
import { normalizePickedPoint, validRoiInput } from './roi';

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
});
