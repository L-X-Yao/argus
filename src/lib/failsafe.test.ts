import { describe, it, expect } from 'vitest';
import { ekfAction, ekfActions, ekfParams, failsafeAction } from './failsafe';
import type { VehicleType } from './modeStore';

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
  const values = (version: string, kind: VehicleType = 'copter') => ekfActions(version, kind).map(([value]) => value);

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

  it('leaves it on what means Disabled by it', () => {
    expect(values('v4.6.3', 'rover')).toEqual([0, 1, 2, 3]);
    expect(values('v4.6.3', 'sub')).toEqual([0, 1, 2, 3]);
  });
});

describe('ekfAction', () => {
  it('shows the Land a 0 means on 4.6', () => {
    expect(ekfAction(0, 'v4.6.3', 'copter')).toBe(1);
  });

  it('leaves what the firmware has', () => {
    expect(ekfAction(0, 'v4.7.0', 'copter')).toBe(0);
    expect(ekfAction(3, 'v4.6.3', 'copter')).toBe(3);
  });
});

describe('ekfParams', () => {
  it('turns the check off by its threshold, and leaves the action', () => {
    expect(ekfParams(false, 2, 0.7)).toEqual([
      ['FS_EKF_ACTION', 2],
      ['FS_EKF_THRESH', 0],
    ]);
  });

  it('writes what is shown when on', () => {
    expect(ekfParams(true, 2, 0.7)).toEqual([
      ['FS_EKF_ACTION', 2],
      ['FS_EKF_THRESH', 0.7],
    ]);
  });

  it('turns a check that was off back on at the default', () => {
    expect(ekfParams(true, 1, 0)).toEqual([
      ['FS_EKF_ACTION', 1],
      ['FS_EKF_THRESH', 0.8],
    ]);
  });
});
