import { describe, expect, it, vi } from 'vitest';
import { defaultState, type DroneState } from './types';
import { isCheckEnabled, preflightChecks, savePreflightConfig } from './preflight';

const t = (key: string) => key;

/** A vehicle that passes every check, and one field changed at a time. */
function good(overrides: Partial<DroneState> = {}): DroneState {
  return {
    ...defaultState,
    connected: true,
    link_age: 0.5,
    gps_fix: '3D',
    gps_fix_raw: 3,
    gps_sats: 12,
    voltage: 24,
    remaining: 80,
    home_lat: 34.25,
    home_lon: 108.9,
    ekf_vel: 0.1,
    ekf_pos_h: 0.1,
    ekf_pos_v: 0.1,
    ekf_compass: 0.1,
    vibe: [5, 5, 5],
    alt_msl: 400,
    alt_rel: 10,
    rc_rssi: 80,
    rc: [1500],
    vtype_raw: 2,
    armed: false,
    prearm: [],
    ...overrides,
  };
}

function check(checks: ReturnType<typeof preflightChecks>, key: string) {
  const found = checks.find((c) => c.key === key);
  if (!found) throw new Error(`no ${key} check`);
  return found;
}

describe('preflightChecks', () => {
  it('passes a healthy vehicle, and the mission check follows the page route', () => {
    const checks = preflightChecks({ drone: good(), waypointCount: 2, battArmVolt: -1, t });
    expect(checks.every((c) => c.ok)).toBe(true);
    expect(check(checks, 'mission').ok).toBe(true);
    expect(check(checks, 'mission').critical).toBe(false);
    expect(check(checks, 'mission').detail).toContain('2 WP');
  });

  it('fails GPS below a 3D fix and below ten satellites', () => {
    const checks = preflightChecks({
      drone: good({ gps_fix_raw: 2, gps_sats: 6 }),
      waypointCount: 0,
      battArmVolt: -1,
      t,
    });
    expect(check(checks, 'gps').ok).toBe(false);
    expect(check(checks, 'sats').ok).toBe(false);
  });

  it('uses BATT_ARM_VOLT when the page has read it, and 22 V otherwise', () => {
    const at23 = preflightChecks({ drone: good({ voltage: 23 }), waypointCount: 0, battArmVolt: -1, t });
    expect(check(at23, 'batV').ok).toBe(true);
    const withParam = preflightChecks({ drone: good({ voltage: 23 }), waypointCount: 0, battArmVolt: 24, t });
    expect(check(withParam, 'batV').ok).toBe(false);
    expect(check(withParam, 'batV').detail).toContain('>=24.0');
  });

  it('BATT_ARM_VOLT 0 disables the voltage check instead of falling back to 22 V', () => {
    const checks = preflightChecks({ drone: good({ voltage: 16 }), waypointCount: 0, battArmVolt: 0, t });
    expect(check(checks, 'batV').ok).toBe(true);
    expect(check(checks, 'batV').detail).toContain('no arming threshold');
  });

  it('a home on the equator is set, and a sea-level barometer is not a failure', () => {
    const equator = preflightChecks({
      drone: good({ home_lat: 0, home_lon: 108.9 }),
      waypointCount: 0,
      battArmVolt: -1,
      t,
    });
    expect(check(equator, 'home').ok).toBe(true);
    const seaLevel = preflightChecks({
      drone: good({ alt_msl: 0, alt_rel: 0 }),
      waypointCount: 0,
      battArmVolt: -1,
      t,
    });
    expect(check(seaLevel, 'baro').ok).toBe(true);
  });

  it('fails navigation, AHRS and compass on their EKF flags and a NaN variance', () => {
    const checks = preflightChecks({
      drone: good({ ekf_flags: 0x480 | 0x800, ekf_compass: NaN }),
      waypointCount: 0,
      battArmVolt: -1,
      t,
    });
    expect(check(checks, 'nav').ok).toBe(false);
    expect(check(checks, 'ahrs').ok).toBe(false);
    expect(check(checks, 'compass').ok).toBe(false);
  });

  it('a NaN variance fails rather than passes the comparison', () => {
    const checks = preflightChecks({
      drone: good({ vibe: [NaN, 1, 1] }),
      waypointCount: 0,
      battArmVolt: -1,
      t,
    });
    expect(check(checks, 'vibe').ok).toBe(false);
  });

  it.each([
    ['sats', { gps_sats: 9 }],
    ['batPct', { remaining: 29 }],
    ['link', { link_age: 2 }],
    ['nav', { ekf_vel: 1 }],
    ['ahrs', { ekf_pos_v: 1 }],
    ['compass', { ekf_compass: 0.8 }],
    ['baro', { connected: false }],
    ['rc', { rc_rssi: 0, rc: [0] }],
    ['vtype', { vtype_raw: 0 }],
    ['notArmed', { armed: true }],
  ])('fails %s at its threshold', (key, overrides) => {
    const checks = preflightChecks({
      drone: good(overrides),
      waypointCount: 1,
      battArmVolt: -1,
      t,
    });
    expect(check(checks, key).ok).toBe(false);
  });

  it('passes the other side of the thresholds', () => {
    const checks = preflightChecks({
      drone: good({ gps_sats: 10, remaining: 30, link_age: 1.9, ekf_vel: 0.99, ekf_pos_v: 0.99 }),
      waypointCount: 1,
      battArmVolt: -1,
      t,
    });
    for (const key of ['sats', 'batPct', 'link', 'nav', 'ahrs']) expect(check(checks, key).ok).toBe(true);
    const unknown = preflightChecks({ drone: good({ remaining: -1 }), waypointCount: 1, battArmVolt: -1, t });
    expect(check(unknown, 'batPct').ok).toBe(true);
  });

  it('a check the operator hid is off; every other key stays on', () => {
    expect(isCheckEnabled({ gps: false }, 'gps')).toBe(false);
    expect(isCheckEnabled({ gps: false }, 'sats')).toBe(true);
    expect(isCheckEnabled({}, 'gps')).toBe(true);
  });

  it('a failed save is reported so the panel keeps its old state', () => {
    vi.stubGlobal('localStorage', {
      setItem: () => {
        throw new Error('storage full');
      },
    });
    expect(savePreflightConfig({ gps: false })).toBe(false);
    vi.unstubAllGlobals();
  });
});
