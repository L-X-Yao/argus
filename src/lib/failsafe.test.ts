import { describe, it, expect } from 'vitest';
import { ekfActions, failsafeAction } from './failsafe';

describe('failsafeAction', () => {
  it('shows the RTL a Copter flies for a removed 2', () => {
    expect(failsafeAction(2, 'copter')).toBe(1);
  });

  it('leaves 2 alone on what still means something by it', () => {
    // Rover FS_THR_ENABLE 2 continues in Auto, and Sub FS_GCS_ENABLE 2 disarms.
    expect(failsafeAction(2, 'rover')).toBe(2);
    expect(failsafeAction(2, 'sub')).toBe(2);
  });

  it('passes the rest through', () => {
    expect(failsafeAction(0, 'copter')).toBe(0);
    expect(failsafeAction(5, 'copter')).toBe(5);
  });
});

describe('ekfActions', () => {
  const values = (version: string) => ekfActions(version).map(([value]) => value);

  it('offers report only from 4.7 on', () => {
    expect(values('v4.7.0')).toEqual([0, 1, 2, 3]);
    expect(values('v4.10.1')).toEqual([0, 1, 2, 3]);
    expect(values('v5.0.0')).toEqual([0, 1, 2, 3]);
  });

  it('keeps it off firmware that would land on it', () => {
    expect(values('v4.6.3')).toEqual([1, 2, 3]);
  });

  it('keeps it off until the version is known', () => {
    expect(values('')).toEqual([1, 2, 3]);
  });
});
