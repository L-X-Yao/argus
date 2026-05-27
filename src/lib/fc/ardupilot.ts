import type { FcAdapter, FcType, FlightMode } from './interface';

const COPTER_MODES: Record<number, string> = {
  0: 'Stabilize',
  1: 'Acro',
  2: 'AltHold',
  3: 'Auto',
  4: 'Guided',
  5: 'Loiter',
  6: 'RTL',
  7: 'Circle',
  9: 'Land',
  11: 'Drift',
  13: 'Sport',
  14: 'Flip',
  15: 'AutoTune',
  16: 'PosHold',
  17: 'Brake',
  18: 'Throw',
  19: 'Avoid_ADSB',
  20: 'Guided_NoGPS',
  21: 'SmartRTL',
  22: 'FlowHold',
  23: 'Follow',
  24: 'ZigZag',
  25: 'SystemID',
  26: 'Heli_Autorotate',
  27: 'Auto RTL',
  28: 'Turtle',
};

const PLANE_MODES: Record<number, string> = {
  0: 'Manual',
  1: 'Circle',
  2: 'Stabilize',
  3: 'Training',
  4: 'Acro',
  5: 'FBW-A',
  6: 'FBW-B',
  7: 'Cruise',
  8: 'AutoTune',
  10: 'Auto',
  11: 'RTL',
  12: 'Loiter',
  13: 'Takeoff',
  14: 'Avoid_ADSB',
  15: 'Guided',
  16: 'Initialising',
  17: 'QStabilize',
  18: 'QHover',
  19: 'QLoiter',
  20: 'QLand',
  21: 'QRTL',
  22: 'QAutotune',
  23: 'QAcro',
  24: 'Thermal',
  25: 'Loiter to QLand',
  26: 'Autoland',
};

const COPTER_BTNS: [number, string][] = [
  [2, 'AltHold'],
  [5, 'Loiter'],
  [3, 'Auto'],
  [6, 'RTL'],
  [0, 'Stabilize'],
  [16, 'PosHold'],
  [4, 'Guided'],
  [9, 'Land'],
];

const PLANE_BTNS: [number, string][] = [
  [19, 'QLoiter'],
  [10, 'Auto'],
  [11, 'RTL'],
  [12, 'Loiter'],
  [5, 'FBW-A'],
  [0, 'Manual'],
  [15, 'Guided'],
  [20, 'QLand'],
];

export const ardupilotAdapter: FcAdapter = {
  type: 'ardupilot' as FcType,

  matches(autopilot: number): boolean {
    return autopilot === 3; // MAV_AUTOPILOT_ARDUPILOTMEGA
  },

  modeName(customMode: number, isPlane: boolean): string {
    const map = isPlane ? PLANE_MODES : COPTER_MODES;
    return map[customMode] || `MODE${customMode}`;
  },

  modeButtons(isPlane: boolean): [number, string][] {
    return isPlane ? PLANE_BTNS : COPTER_BTNS;
  },

  allModes(isPlane: boolean): FlightMode[] {
    const map = isPlane ? PLANE_MODES : COPTER_MODES;
    const emergencyIds = isPlane
      ? new Set([11, 20, 21, 25, 26]) // RTL, QLand, QRTL, Loiter2QLand, Autoland
      : new Set([6, 9, 17, 19, 21, 26, 27]); // RTL, Land, Brake, AvoidADSB, SmartRTL, Autorotate, AutoRTL
    const manualIds = isPlane
      ? new Set([0, 2, 3, 4, 17, 23]) // Manual, Stabilize, Training, Acro, QStabilize, QAcro
      : new Set([0, 1, 13, 14]); // Stabilize, Acro, Sport, Flip
    const autoIds = isPlane ? new Set([10, 13, 15]) : new Set([3, 4]); // Auto+Takeoff+Guided / Auto+Guided
    return Object.entries(map).map(([id, name]) => {
      const n = parseInt(id);
      let category: FlightMode['category'] = 'assisted';
      if (emergencyIds.has(n)) category = 'emergency';
      else if (manualIds.has(n)) category = 'manual';
      else if (autoIds.has(n)) category = 'auto';
      return { id: n, name, category };
    });
  },

  armBaseMode(): number {
    return 209;
  },
  rtlModeId(isPlane: boolean): number {
    return isPlane ? 11 : 6;
  },
  holdModeId(isPlane: boolean): number {
    return isPlane ? 19 : 5;
  },
  autoModeId(): number {
    return 3;
  },

  vehicleTypeName(mavType: number): string {
    const map: Record<number, string> = {
      1: 'Fixed Wing',
      2: 'Quadrotor',
      3: 'Coaxial',
      4: 'Helicopter',
      10: 'Rover',
      12: 'Submarine',
      13: 'Hexarotor',
      14: 'Octorotor',
      19: 'VTOL Duo',
      20: 'VTOL Quad',
      21: 'VTOL Tilt',
      22: 'VTOL Fixedrotor',
      23: 'VTOL Tailsitter',
      24: 'VTOL Tilt (2)',
      25: 'VTOL Tilt (4)',
    };
    return map[mavType] || `Type ${mavType}`;
  },
};
