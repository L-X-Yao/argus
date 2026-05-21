import { describe, it, expect, beforeEach } from 'vitest';
import { fmtAlt, fmtSpeed, fmtDist, fmtVs, setUnitSystem, altUnit, speedUnit, distUnit } from './units';

describe('units — metric', () => {
  beforeEach(() => setUnitSystem('metric'));

  it('fmtAlt returns meters with one decimal', () => {
    expect(fmtAlt(100)).toBe('100.0');
    expect(fmtAlt(0)).toBe('0.0');
    expect(fmtAlt(12.345)).toBe('12.3');
  });

  it('fmtSpeed returns m/s with one decimal', () => {
    expect(fmtSpeed(15)).toBe('15.0');
    expect(fmtSpeed(0)).toBe('0.0');
  });

  it('fmtDist returns meters for short distances', () => {
    expect(fmtDist(500)).toBe('500 m');
    expect(fmtDist(999)).toBe('999 m');
  });

  it('fmtDist returns km for long distances', () => {
    expect(fmtDist(1500)).toBe('1.5 km');
    expect(fmtDist(10000)).toBe('10.0 km');
  });

  it('fmtVs returns m/s with one decimal', () => {
    expect(fmtVs(2.5)).toBe('2.5');
    expect(fmtVs(-1.2)).toBe('-1.2');
  });

  it('unit labels are metric', () => {
    expect(altUnit()).toBe('m');
    expect(speedUnit()).toBe('m/s');
    expect(distUnit()).toBe('km');
  });
});

describe('units — imperial', () => {
  beforeEach(() => setUnitSystem('imperial'));

  it('fmtAlt converts to feet', () => {
    // 100m * 3.28084 = 328 ft
    expect(fmtAlt(100)).toBe('328');
    expect(fmtAlt(0)).toBe('0');
  });

  it('fmtSpeed converts to mph', () => {
    // 10 m/s * 2.23694 = 22.4 mph
    expect(fmtSpeed(10)).toBe('22.4');
  });

  it('fmtDist returns feet for short distances', () => {
    // 100m = 328 ft, mi = 0.062 < 0.1 → feet
    expect(fmtDist(100)).toContain('ft');
  });

  it('fmtDist returns miles for long distances', () => {
    // 5000m = 3.1 mi
    expect(fmtDist(5000)).toContain('mi');
  });

  it('fmtVs converts to ft/min', () => {
    // 1 m/s * 196.85 = 197 ft/min
    expect(fmtVs(1)).toBe('197');
  });

  it('unit labels are imperial', () => {
    expect(altUnit()).toBe('ft');
    expect(speedUnit()).toBe('mph');
    expect(distUnit()).toBe('mi');
  });
});
