import type { VehicleType } from './modeStore';

/**
 * What the selector shows for FS_THR_ENABLE and FS_GCS_ENABLE, and so what Save writes.
 * 2 is "removed in 4.0+" on Copter, where the FC flies an RTL for it (ArduCopter/events.cpp
 * failsafe_radio_on_event, failsafe_gcs_on_event). Rover and Sub mean something else by 2, so
 * theirs is left as it is.
 */
export function failsafeAction(value: number, kind: VehicleType): number {
  return value === 2 && kind === 'copter' ? 1 : value;
}

const FS_EKF_THRESH_DEFAULT = 0.8; // ArduCopter/config.h

// ArduCopter/Parameters.cpp:270 FS_EKF_ACTION @Values.
const EKF_ACTIONS: [number, string][] = [
  [0, 'failsafe.actionNone'],
  [1, 'failsafe.actionLand'],
  [2, 'failsafe.actionAltHold'],
  [3, 'failsafe.actionLandAlways'],
];

/**
 * 0 is report only from 4.7 on. Before that Copter has no such value: it falls to the default
 * of the action switch and lands (Copter-4.6.3 ArduCopter/ekf_check.cpp:199). Rover and Sub
 * mean Disabled by it.
 */
export function ekfActions(fwVersion: string, kind: VehicleType): [number, string][] {
  const [major, minor] = (fwVersion.match(/(\d+)\.(\d+)/) ?? []).slice(1).map(Number);
  return kind !== 'copter' || major > 4 || (major === 4 && minor >= 7) ? EKF_ACTIONS : EKF_ACTIONS.slice(1);
}

/** What the selector shows for FS_EKF_ACTION: a 0 the firmware lands on reads as the Land it is. */
export function ekfAction(value: number, fwVersion: string, kind: VehicleType): number {
  return ekfActions(fwVersion, kind).some(([offered]) => offered === value) ? value : 1;
}

/**
 * What the section saves. Off is a threshold of 0, which stops the check itself on every
 * version (ArduCopter/ekf_check.cpp:42). An action of 0 is no off: see ekfActions.
 */
export function ekfParams(enabled: boolean, action: number, threshold: number): [string, number][] {
  return [
    ['FS_EKF_ACTION', action],
    ['FS_EKF_THRESH', enabled ? threshold || FS_EKF_THRESH_DEFAULT : 0],
  ];
}
