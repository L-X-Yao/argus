/** Mode numbers for the UI, which differ per vehicle. See SPECIAL_MODES. */
import { app, isPlane } from './stores.svelte';
import { SPECIAL_MODES, VTOL_MODES, vehicleType, type SpecialModes, type VehicleType } from './modeStore';

export const vehicleKind = (): VehicleType => (isPlane() ? 'plane' : vehicleType(app.drone.vtype_raw));

// A default QuadPlane heartbeats as MAV_TYPE 1 like a plain plane, so the type alone
// misses it: see backend handle_extended_sys_state.
const isVtol = (): boolean => isPlane() && (app.drone.vtol_state !== 0 || app.drone.vtype_raw !== 1);

export function specialModes(): SpecialModes {
  const modes = SPECIAL_MODES[vehicleKind()];
  return isVtol() ? { ...modes, ...VTOL_MODES } : modes;
}
