import type { VehicleType } from './modeStore';

/**
 * What the selector shows for FS_THR_ENABLE and FS_GCS_ENABLE, and so what Save writes.
 * 2 is "removed in 4.0+" on Copter, where the FC flies an RTL for it (ArduCopter/events.cpp:24
 * and :189). Rover and Sub mean something else by 2, so theirs is left as it is.
 */
export function failsafeAction(value: number, kind: VehicleType): number {
  return value === 2 && kind === 'copter' ? 1 : value;
}

// ArduCopter/Parameters.cpp:270 FS_EKF_ACTION @Values.
const EKF_ACTIONS: [number, string][] = [
  [0, 'failsafe.actionNone'],
  [1, 'failsafe.actionLand'],
  [2, 'failsafe.actionAltHold'],
  [3, 'failsafe.actionLandAlways'],
];

/**
 * 0 is report only from 4.7 on. Before that it is not a value at all, and the FC falls to the
 * default of the action switch and lands (Copter-4.6.3 ArduCopter/ekf_check.cpp:199).
 */
export function ekfActions(fwVersion: string): [number, string][] {
  const [major, minor] = (fwVersion.match(/(\d+)\.(\d+)/) ?? []).slice(1).map(Number);
  return major > 4 || (major === 4 && minor >= 7) ? EKF_ACTIONS : EKF_ACTIONS.slice(1);
}
