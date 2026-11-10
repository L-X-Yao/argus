import { describe, it, expect } from 'vitest';
import { worst } from './worst';

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
