import { describe, it, expect } from 'vitest';
import { worst, wrapPi } from './worst';

describe('worst', () => {
  it('is the largest of healthy values', () => {
    expect(worst(0.1, 0.7, 0.3)).toBe(0.7);
  });

  it('is beyond every limit when one value is NaN', () => {
    // What Math.max gives is NaN, and NaN > 0.8 is false: no alarm.
    expect(Math.max(0.1, NaN) > 0.8).toBe(false);
    expect(worst(0.1, NaN) > 0.8).toBe(true);
    expect(worst(NaN, NaN, NaN) >= 1.0).toBe(true);
  });

  it('is beyond every limit for an infinity of either sign', () => {
    expect(worst(0.1, Infinity)).toBe(Infinity);
    expect(worst(0.1, -Infinity)).toBe(Infinity);
  });
});

describe('wrapPi', () => {
  it('leaves an angle already in range alone', () => {
    expect(wrapPi(1)).toBe(1);
    expect(wrapPi(-3)).toBe(-3);
  });

  it('brings any angle into -π..π', () => {
    expect(wrapPi(Math.PI + 0.5)).toBeCloseTo(-Math.PI + 0.5);
    expect(wrapPi(-Math.PI - 0.5)).toBeCloseTo(Math.PI - 0.5);
    expect(wrapPi(7 * 2 * Math.PI + 0.25)).toBeCloseTo(0.25);
    expect(Math.abs(wrapPi(1e12))).toBeLessThanOrEqual(Math.PI);
  });

  it('gives NaN for a heading that is no number, where a loop never ended', () => {
    expect(wrapPi(Infinity)).toBeNaN();
    expect(wrapPi(-Infinity)).toBeNaN();
    expect(wrapPi(NaN)).toBeNaN();
  });
});
