/**
 * MAVLink message decoders and encoders for the most common messages.
 *
 * Each decoder takes a DataView (the payload) and returns a typed object.
 * Encoders return a Uint8Array payload ready for encodeFrame().
 */

import type { MavFrame } from './codec';

/* ── Decoded message types ── */

export interface Heartbeat {
  customMode: number;
  type: number;
  autopilot: number;
  baseMode: number;
  systemStatus: number;
  mavlinkVersion: number;
}

export interface SysStatus {
  voltage: number;
  current: number;
  remaining: number;
}

export interface GpsRawInt {
  fixType: number;
  lat: number;
  lon: number;
  alt: number;
  sats: number;
}

export interface Attitude {
  roll: number;
  pitch: number;
  yaw: number;
}

export interface GlobalPositionInt {
  lat: number;
  lon: number;
  altMsl: number;
  altRel: number;
  vx: number;
  vy: number;
  vz: number;
  hdg: number;
}

export interface VfrHud {
  airspeed: number;
  groundspeed: number;
  heading: number;
  throttle: number;
  alt: number;
  climb: number;
}

export interface RcChannels {
  chancount: number;
  channels: number[];
  rssi: number;
}

export interface ServoOutput {
  outputs: number[];
}

export interface StatusText {
  severity: number;
  text: string;
}

export interface ParamValue {
  paramId: string;
  paramValue: number;
  paramType: number;
  paramCount: number;
  paramIndex: number;
}

export interface CommandAck {
  command: number;
  result: number;
}

export interface MissionCurrent {
  seq: number;
}

export interface MissionAck {
  type: number;
}

export interface MissionCount {
  count: number;
}

export interface MissionItemInt {
  seq: number;
  frame: number;
  command: number;
  current: number;
  autocontinue: number;
  param1: number;
  param2: number;
  param3: number;
  param4: number;
  x: number;  // lat * 1e7
  y: number;  // lon * 1e7
  z: number;  // alt
}

export interface HomePosition {
  lat: number;
  lon: number;
  alt: number;
}

export interface Vibration {
  x: number; y: number; z: number;
  clip0: number; clip1: number; clip2: number;
}

export interface Wind {
  direction: number;
  speed: number;
}

export interface AutopilotVersion {
  flightSwVersion: number;
  boardVersion: number;
  uid: bigint;
}

/* ── Decoders ── */

export function decodeHeartbeat(p: DataView): Heartbeat {
  return {
    customMode: p.getUint32(0, true),
    type: p.getUint8(4),
    autopilot: p.getUint8(5),
    baseMode: p.getUint8(6),
    systemStatus: p.getUint8(7),
    mavlinkVersion: p.getUint8(8),
  };
}

export function decodeSysStatus(p: DataView): SysStatus {
  return {
    voltage: p.getUint16(14, true) / 1000,
    current: p.getInt16(16, true) / 100,
    remaining: p.getInt8(30),
  };
}

export function decodeGpsRawInt(p: DataView): GpsRawInt {
  return {
    fixType: p.getUint8(28),
    lat: p.getInt32(8, true) / 1e7,
    lon: p.getInt32(12, true) / 1e7,
    alt: p.getInt32(16, true) / 1000,
    sats: p.byteLength > 29 ? p.getUint8(29) : 0,
  };
}

export function decodeAttitude(p: DataView): Attitude {
  return {
    roll: p.getFloat32(4, true) * 180 / Math.PI,
    pitch: p.getFloat32(8, true) * 180 / Math.PI,
    yaw: p.getFloat32(12, true) * 180 / Math.PI,
  };
}

export function decodeGlobalPositionInt(p: DataView): GlobalPositionInt {
  return {
    lat: p.getInt32(4, true) / 1e7,
    lon: p.getInt32(8, true) / 1e7,
    altMsl: p.getInt32(12, true) / 1000,
    altRel: p.getInt32(16, true) / 1000,
    vx: p.getInt16(20, true) / 100,
    vy: p.getInt16(22, true) / 100,
    vz: p.getInt16(24, true) / 100,
    hdg: p.getUint16(26, true) / 100,
  };
}

export function decodeVfrHud(p: DataView): VfrHud {
  return {
    airspeed: p.getFloat32(0, true),
    groundspeed: p.getFloat32(4, true),
    alt: p.getFloat32(8, true),
    climb: p.getFloat32(12, true),
    heading: p.getInt16(16, true),
    throttle: p.getUint16(18, true),
  };
}

export function decodeRcChannels(p: DataView): RcChannels {
  const channels: number[] = [];
  for (let i = 0; i < 18 && (4 + i * 2 + 1) < p.byteLength; i++) {
    channels.push(p.getUint16(4 + i * 2, true));
  }
  const chancount = p.byteLength > 40 ? p.getUint8(40) : 0;
  return { chancount, channels, rssi: p.byteLength > 41 ? p.getUint8(41) : 0 };
}

export function decodeServoOutput(p: DataView): ServoOutput {
  const outputs: number[] = [];
  for (let i = 0; i < 16 && (4 + i * 2 + 1) < p.byteLength; i++) {
    outputs.push(p.getUint16(4 + i * 2, true));
  }
  return { outputs };
}

export function decodeStatusText(p: DataView): StatusText {
  const severity = p.getUint8(0);
  const bytes = new Uint8Array(p.buffer, p.byteOffset + 1, Math.min(p.byteLength - 1, 50));
  let end = bytes.indexOf(0);
  if (end < 0) end = bytes.length;
  const text = new TextDecoder().decode(bytes.slice(0, end));
  return { severity, text };
}

export function decodeParamValue(p: DataView): ParamValue {
  const bytes = new Uint8Array(p.buffer, p.byteOffset + 8, 16);
  let end = bytes.indexOf(0);
  if (end < 0) end = 16;
  const paramId = new TextDecoder().decode(bytes.slice(0, end));
  return {
    paramValue: p.getFloat32(0, true),
    paramId,
    paramType: p.getUint8(24),
    paramCount: p.getUint16(4, true),
    paramIndex: p.getUint16(6, true),
  };
}

export function decodeCommandAck(p: DataView): CommandAck {
  return { command: p.getUint16(0, true), result: p.getUint8(2) };
}

export function decodeMissionCurrent(p: DataView): MissionCurrent {
  return { seq: p.getUint16(0, true) };
}

export function decodeMissionAck(p: DataView): MissionAck {
  return { type: p.getUint8(2) };
}

export function decodeMissionCount(p: DataView): MissionCount {
  return { count: p.getUint16(0, true) };
}

export function decodeMissionItemInt(p: DataView): MissionItemInt {
  return {
    param1: p.getFloat32(0, true),
    param2: p.getFloat32(4, true),
    param3: p.getFloat32(8, true),
    param4: p.getFloat32(12, true),
    x: p.getInt32(16, true),
    y: p.getInt32(20, true),
    z: p.getFloat32(24, true),
    seq: p.getUint16(28, true),
    command: p.getUint16(30, true),
    frame: p.getUint8(34),
    current: p.getUint8(35),
    autocontinue: p.getUint8(36),
  };
}

export function decodeHomePosition(p: DataView): HomePosition {
  return {
    lat: p.getInt32(0, true) / 1e7,
    lon: p.getInt32(4, true) / 1e7,
    alt: p.getInt32(8, true) / 1000,
  };
}

export function decodeVibration(p: DataView): Vibration {
  return {
    x: p.getFloat32(8, true),
    y: p.getFloat32(12, true),
    z: p.getFloat32(16, true),
    clip0: p.getUint32(20, true),
    clip1: p.getUint32(24, true),
    clip2: p.getUint32(28, true),
  };
}

export function decodeWind(p: DataView): Wind {
  return {
    direction: p.getFloat32(0, true),
    speed: p.getFloat32(4, true),
  };
}

/* ── Encoders ── */

export function encodeHeartbeat(sysType: number = 6, autopilot: number = 8): Uint8Array {
  const buf = new Uint8Array(9);
  const dv = new DataView(buf.buffer);
  dv.setUint32(0, 0, true);    // custom_mode
  dv.setUint8(4, sysType);     // MAV_TYPE_GCS = 6
  dv.setUint8(5, autopilot);   // MAV_AUTOPILOT_INVALID = 8
  dv.setUint8(6, 0);           // base_mode
  dv.setUint8(7, 0);           // system_status
  dv.setUint8(8, 3);           // mavlink_version
  return buf;
}

export function encodeCommandLong(
  targetSys: number, targetComp: number,
  command: number, confirmation: number,
  p1: number, p2: number, p3: number, p4: number,
  p5: number, p6: number, p7: number,
): Uint8Array {
  const buf = new Uint8Array(33);
  const dv = new DataView(buf.buffer);
  dv.setFloat32(0, p1, true);
  dv.setFloat32(4, p2, true);
  dv.setFloat32(8, p3, true);
  dv.setFloat32(12, p4, true);
  dv.setFloat32(16, p5, true);
  dv.setFloat32(20, p6, true);
  dv.setFloat32(24, p7, true);
  dv.setUint16(28, command, true);
  dv.setUint8(30, targetSys);
  dv.setUint8(31, targetComp);
  dv.setUint8(32, confirmation);
  return buf;
}

export function encodeSetMode(targetSys: number, baseMode: number, customMode: number): Uint8Array {
  const buf = new Uint8Array(6);
  const dv = new DataView(buf.buffer);
  dv.setUint32(0, customMode, true);
  dv.setUint8(4, targetSys);
  dv.setUint8(5, baseMode);
  return buf;
}

export function encodeParamRequestList(targetSys: number, targetComp: number): Uint8Array {
  const buf = new Uint8Array(2);
  buf[0] = targetSys;
  buf[1] = targetComp;
  return buf;
}

export function encodeParamSet(
  targetSys: number, targetComp: number,
  paramId: string, value: number, paramType: number,
): Uint8Array {
  const buf = new Uint8Array(23);
  const dv = new DataView(buf.buffer);
  dv.setFloat32(0, value, true);
  dv.setUint8(4, targetSys);
  dv.setUint8(5, targetComp);
  const enc = new TextEncoder();
  const nameBytes = enc.encode(paramId);
  buf.set(nameBytes.slice(0, 16), 6);
  dv.setUint8(22, paramType);
  return buf;
}

export function encodeRequestDataStream(
  targetSys: number, targetComp: number,
  streamId: number, rate: number, startStop: number,
): Uint8Array {
  const buf = new Uint8Array(6);
  const dv = new DataView(buf.buffer);
  dv.setUint16(0, rate, true);
  dv.setUint8(2, targetSys);
  dv.setUint8(3, targetComp);
  dv.setUint8(4, streamId);
  dv.setUint8(5, startStop);
  return buf;
}

/**
 * Dispatch a decoded frame to the appropriate handler.
 */
export function dispatchFrame(frame: MavFrame, handlers: Partial<MessageHandlers>): void {
  switch (frame.msgId) {
    case 0:   handlers.onHeartbeat?.(decodeHeartbeat(frame.payload), frame); break;
    case 1:   handlers.onSysStatus?.(decodeSysStatus(frame.payload), frame); break;
    case 24:  handlers.onGpsRawInt?.(decodeGpsRawInt(frame.payload), frame); break;
    case 30:  handlers.onAttitude?.(decodeAttitude(frame.payload), frame); break;
    case 33:  handlers.onGlobalPositionInt?.(decodeGlobalPositionInt(frame.payload), frame); break;
    case 65:  handlers.onRcChannels?.(decodeRcChannels(frame.payload), frame); break;
    case 36:  handlers.onServoOutput?.(decodeServoOutput(frame.payload), frame); break;
    case 74:  handlers.onVfrHud?.(decodeVfrHud(frame.payload), frame); break;
    case 22:  handlers.onParamValue?.(decodeParamValue(frame.payload), frame); break;
    case 77:  handlers.onCommandAck?.(decodeCommandAck(frame.payload), frame); break;
    case 42:  handlers.onMissionCurrent?.(decodeMissionCurrent(frame.payload), frame); break;
    case 47:  handlers.onMissionAck?.(decodeMissionAck(frame.payload), frame); break;
    case 44:  handlers.onMissionCount?.(decodeMissionCount(frame.payload), frame); break;
    case 73:  handlers.onMissionItemInt?.(decodeMissionItemInt(frame.payload), frame); break;
    case 242: handlers.onHomePosition?.(decodeHomePosition(frame.payload), frame); break;
    case 241: handlers.onVibration?.(decodeVibration(frame.payload), frame); break;
    case 168: handlers.onWind?.(decodeWind(frame.payload), frame); break;
    case 253: handlers.onStatusText?.(decodeStatusText(frame.payload), frame); break;
    default:  handlers.onUnknown?.(frame); break;
  }
}

export interface MessageHandlers {
  onHeartbeat: (msg: Heartbeat, frame: MavFrame) => void;
  onSysStatus: (msg: SysStatus, frame: MavFrame) => void;
  onGpsRawInt: (msg: GpsRawInt, frame: MavFrame) => void;
  onAttitude: (msg: Attitude, frame: MavFrame) => void;
  onGlobalPositionInt: (msg: GlobalPositionInt, frame: MavFrame) => void;
  onRcChannels: (msg: RcChannels, frame: MavFrame) => void;
  onServoOutput: (msg: ServoOutput, frame: MavFrame) => void;
  onVfrHud: (msg: VfrHud, frame: MavFrame) => void;
  onParamValue: (msg: ParamValue, frame: MavFrame) => void;
  onCommandAck: (msg: CommandAck, frame: MavFrame) => void;
  onMissionCurrent: (msg: MissionCurrent, frame: MavFrame) => void;
  onMissionAck: (msg: MissionAck, frame: MavFrame) => void;
  onMissionCount: (msg: MissionCount, frame: MavFrame) => void;
  onMissionItemInt: (msg: MissionItemInt, frame: MavFrame) => void;
  onHomePosition: (msg: HomePosition, frame: MavFrame) => void;
  onVibration: (msg: Vibration, frame: MavFrame) => void;
  onWind: (msg: Wind, frame: MavFrame) => void;
  onStatusText: (msg: StatusText, frame: MavFrame) => void;
  onUnknown: (frame: MavFrame) => void;
}
