/**
 * The checks the preflight panel makes before flight, in one place: the panel shows them and
 * the AI assistant reads the same list through backend/mcp_server.py, so a threshold changed
 * here changes both. Nothing in this file touches a link or a vehicle.
 */
import type { DroneState } from './types';
import { worst } from './worst';

export interface PreflightCheck {
  key: string;
  name: string;
  ok: boolean;
  detail: string;
  critical: boolean;
}

export interface PreflightInputs {
  drone: DroneState;
  waypointCount: number;
  /** BATT_ARM_VOLT when the page has read it, otherwise a value <= 0. */
  battArmVolt: number;
  /** The page's translator: names are shown to the operator and sent to the model. */
  t: (key: string) => string;
}

export function preflightChecks({ drone: d, waypointCount, battArmVolt, t }: PreflightInputs): PreflightCheck[] {
  // BATT_ARM_VOLT 0 means no voltage threshold: 0 disables the check
  // (AP_BattMonitor_Params.cpp:167-173) and only a positive value is enforced
  // (AP_BattMonitor_Backend.cpp:215-216). A negative value means the page has not read it,
  // and the fixed 22 V fallback applies (the old check read every vehicle as a 6S one).
  const minBatV = battArmVolt === 0 ? 0 : battArmVolt > 0 ? battArmVolt : 22;
  const gpsOk = d.gps_fix_raw >= 3;
  return [
    { key: 'gps', name: t('check.gps'), ok: gpsOk, detail: `${d.gps_fix}`, critical: true },
    { key: 'sats', name: t('check.sats'), ok: d.gps_sats >= 10, detail: `${d.gps_sats} (>=10)`, critical: true },
    {
      key: 'batV',
      name: t('check.batV'),
      ok: minBatV === 0 || d.voltage >= minBatV,
      detail:
        minBatV === 0
          ? `${d.voltage.toFixed(1)}V (no arming threshold)`
          : `${d.voltage.toFixed(1)}V (>=${minBatV.toFixed(1)})`,
      critical: true,
    },
    {
      key: 'batPct',
      name: t('check.batPct'),
      ok: d.remaining >= 30 || d.remaining < 0,
      detail: d.remaining >= 0 ? `${d.remaining}%` : '---',
      critical: true,
    },
    {
      key: 'home',
      name: t('check.home'),
      // (0, 0) is the "no home" sentinel; a home on the equator is still a home.
      ok: d.home_lat !== 0 || d.home_lon !== 0,
      detail: d.home_lat !== 0 || d.home_lon !== 0 ? `${d.home_lat.toFixed(5)}, ${d.home_lon.toFixed(5)}` : '---',
      critical: true,
    },
    {
      key: 'link',
      name: t('check.link'),
      ok: d.connected && d.link_age >= 0 && d.link_age < 2,
      detail: d.connected ? `${d.link_age.toFixed(1)}s` : '---',
      critical: true,
    },
    {
      key: 'nav',
      name: t('check.nav'),
      ok: !(d.ekf_flags & 0x480) && worst(d.ekf_vel, d.ekf_pos_h, d.ekf_pos_v, d.ekf_compass) < 1.0,
      detail:
        d.ekf_flags & 0x480 ? 'ERR' : worst(d.ekf_vel, d.ekf_pos_h, d.ekf_pos_v, d.ekf_compass) < 0.5 ? 'OK' : 'WARN',
      critical: true,
    },
    {
      key: 'vibe',
      name: t('check.vibe'),
      ok: worst(d.vibe[0], d.vibe[1], d.vibe[2]) < 30,
      detail: `${Math.max(d.vibe[0], d.vibe[1], d.vibe[2]).toFixed(0)} m/s2`,
      critical: true,
    },
    {
      key: 'compass',
      name: t('check.compass'),
      ok: worst(d.ekf_compass) < 0.8,
      detail: worst(d.ekf_compass) < 0.5 ? 'OK' : worst(d.ekf_compass) < 0.8 ? 'WARN' : `${d.ekf_compass.toFixed(2)}`,
      critical: true,
    },
    {
      key: 'baro',
      name: t('check.baro'),
      // A connected vehicle at sea level legitimately reports 0 m; what matters is that the
      // barometer's numbers are present and finite, not that they are non-zero.
      ok: d.connected && Number.isFinite(d.alt_msl) && Number.isFinite(d.alt_rel),
      detail: d.connected ? `MSL ${d.alt_msl.toFixed(1)}m` : '---',
      critical: true,
    },
    {
      key: 'ahrs',
      name: t('check.ahrs'),
      ok: !(d.ekf_flags & 0x800) && worst(d.ekf_vel, d.ekf_pos_v) < 1.0,
      detail: d.ekf_flags & 0x800 ? 'ERR' : worst(d.ekf_vel, d.ekf_pos_v) < 0.5 ? 'OK' : 'WARN',
      critical: true,
    },
    {
      key: 'rc',
      name: t('check.rc'),
      ok: d.rc_rssi > 0 || d.rc[0] > 0,
      detail: d.rc_rssi > 0 ? `RSSI ${d.rc_rssi}` : d.rc[0] > 0 ? 'OK' : '---',
      critical: false,
    },
    {
      key: 'mission',
      name: t('check.mission'),
      ok: waypointCount > 0,
      // The route kept in this page, not the vehicle's: nothing tells the vehicle's count
      // without a download. The detail says which one it is, so the green tick is not read
      // as "the vehicle has this mission" when it never was uploaded.
      detail: waypointCount > 0 ? `${waypointCount} WP · ${t('check.local')}` : '---',
      critical: false,
    },
    {
      key: 'vtype',
      name: t('check.vtype'),
      ok: d.vtype_raw > 0,
      detail:
        d.vtype_raw > 0
          ? t(
              [1, 19, 20, 21, 22, 23, 24, 25].includes(d.vtype_raw)
                ? 'vtype.plane'
                : [10, 11].includes(d.vtype_raw)
                  ? 'vtype.rover'
                  : d.vtype_raw === 12
                    ? 'vtype.sub'
                    : 'vtype.copter',
            )
          : '---',
      critical: false,
    },
    {
      key: 'notArmed',
      name: t('check.notArmed'),
      ok: !d.armed,
      detail: d.armed ? t('status.armed') : 'OK',
      critical: false,
    },
  ];
}

export const PREFLIGHT_CONFIG_KEY = 'argus_preflight_config';

export function loadPreflightConfig(): Record<string, boolean> {
  try {
    const cfg = JSON.parse(localStorage.getItem(PREFLIGHT_CONFIG_KEY) || '{}');
    if (cfg && typeof cfg === 'object' && !Array.isArray(cfg)) return cfg;
  } catch {
    // No storage in this context, or a value that is not an object: every check stays on.
  }
  return {};
}

export function savePreflightConfig(config: Record<string, boolean>): boolean {
  try {
    localStorage.setItem(PREFLIGHT_CONFIG_KEY, JSON.stringify(config));
    return true;
  } catch {
    // A full or forbidden storage must not leave the panel and the assistant reading
    // different configurations: the caller keeps the old state when this returns false.
    return false;
  }
}

export function isCheckEnabled(config: Record<string, boolean>, key: string): boolean {
  return config[key] !== false;
}
