/**
 * Transport abstraction layer — unified interface for both:
 * 1. WebSerial direct connection (no backend needed)
 * 2. WebSocket connection via Python backend
 *
 * The frontend code calls transport functions which internally route
 * to the appropriate backend based on the active connection mode.
 */

import { parseFrames, encodeFrame, dispatchFrame } from './mavlink';
import type { MessageHandlers } from './mavlink';
import {
  encodeHeartbeat,
  encodeCommandLong,
  encodeSetMode,
  encodeParamRequestList,
  encodeParamSet,
  encodeRequestDataStream,
  encodeMissionCount,
  encodeMissionItemInt,
  encodeMissionClearAll,
} from './mavlink';
import { openSerial, serialWrite, serialReadLoop, isWebSerialSupported } from './serial';
import type { SerialConnection } from './serial';
import { addToast, app } from './stores.svelte';
import { buildMissionItems, validateMissionWaypoints } from './missionUpload';
import type { MissionItem } from './missionUpload';
import type { Waypoint } from './types';

export type TransportMode = 'websocket' | 'serial';

interface SerialState {
  conn: SerialConnection | null;
  buf: Uint8Array;
  seq: number;
  running: boolean;
  hbInterval: ReturnType<typeof setInterval> | null;
  targetSysId: number;
  targetCompId: number;
  handlers: Partial<MessageHandlers>;
}

const serial: SerialState = {
  conn: null,
  buf: new Uint8Array(0),
  seq: 0,
  running: false,
  hbInterval: null,
  targetSysId: 1,
  targetCompId: 1,
  handlers: {},
};

export function getTransportMode(): TransportMode {
  return serial.conn ? 'serial' : 'websocket';
}

export function isSerialConnected(): boolean {
  return serial.conn !== null && serial.running;
}

export function webSerialAvailable(): boolean {
  return isWebSerialSupported();
}

/**
 * Connect via WebSerial.
 * Returns true if connection was established.
 */
export async function connectSerial(
  baudRate: number,
  handlers: Partial<MessageHandlers>,
): Promise<boolean> {
  if (serial.conn) await disconnectSerial();

  try {
    serial.conn = await openSerial(baudRate);
    serial.handlers = handlers;
    serial.running = true;
    serial.seq = 0;
    serial.buf = new Uint8Array(0);

    // Start heartbeat at 1Hz
    serial.hbInterval = setInterval(() => {
      sendSerialFrame(0, encodeHeartbeat());
    }, 1000);

    // Request data streams
    requestStreams();

    // Start read loop (runs until disconnected)
    serialReadLoop(serial.conn, (chunk) => {
      const combined = new Uint8Array(serial.buf.length + chunk.length);
      combined.set(serial.buf);
      combined.set(chunk, serial.buf.length);

      const { frames, remaining } = parseFrames(combined);
      serial.buf = remaining;

      for (const frame of frames) {
        if (serial.targetSysId === 1 && frame.sysId > 0 && frame.msgId === 0) {
          serial.targetSysId = frame.sysId;
          serial.targetCompId = frame.compId;
        }
        // Mission upload state machine runs BEFORE the external dispatch so the
        // upload completes deterministically even if the user's handler set is
        // missing onMissionRequest / onMissionAck. frame.payload is a DataView.
        if (upload?.pending) {
          if (frame.msgId === 40 || frame.msgId === 51) {
            const seq = frame.payload.byteLength >= 2 ? frame.payload.getUint16(0, true) : 0;
            _onMissionRequest(seq);
          } else if (frame.msgId === 47) {
            // MISSION_ACK type is at offset 2 (after target_system, target_component).
            const type = frame.payload.byteLength > 2 ? frame.payload.getUint8(2) : 0;
            _onMissionAck(type);
          }
        }
        dispatchFrame(frame, serial.handlers);
      }
    }).catch((e) => { console.error('[Serial] read loop error', e); }).finally(() => {
      const wasRunning = serial.running;
      serial.running = false;
      if (wasRunning) {
        addToast('Serial connection lost', 'error', 8000);
        // Release the transport mutex so the user can switch to WS without
        // having to click the (now-stale) USB button first.
        if (app.activeTransport === 'serial') app.activeTransport = 'none';
      }
      // Surface a link-lost error to any in-flight upload promise so the
      // MissionPanel doesn't wait the full 30s timeout.
      if (upload?.pending) {
        _resolveUpload({ ok: false, error: 'Serial link lost mid-upload' });
      }
    });

    return true;
  } catch {
    serial.conn = null;
    return false;
  }
}

export async function disconnectSerial(): Promise<void> {
  serial.running = false;
  if (serial.hbInterval) {
    clearInterval(serial.hbInterval);
    serial.hbInterval = null;
  }
  if (serial.conn) {
    await serial.conn.close();
    serial.conn = null;
  }
  serial.buf = new Uint8Array(0);
}

function sendSerialFrame(msgId: number, payload: Uint8Array): void {
  if (!serial.conn || !serial.running) return;
  const frame = encodeFrame(msgId, payload, 255, 190, serial.seq++);
  serialWrite(serial.conn, frame).catch((e) => { console.error('[Serial] write error', e); });
}

function requestStreams(): void {
  const streams = [
    [1, 2],   // RAW_SENSORS
    [2, 2],   // EXTENDED_STATUS
    [3, 2],   // RC_CHANNELS
    [6, 5],   // POSITION
    [10, 2],  // EXTRA1 (attitude)
    [11, 2],  // EXTRA2 (VFR_HUD)
    [12, 2],  // EXTRA3 (vibration, EKF)
  ];
  for (const [id, rate] of streams) {
    sendSerialFrame(66, encodeRequestDataStream(
      serial.targetSysId, serial.targetCompId, id, rate, 1,
    ));
  }
}

/* ── Serial command API (mirrors ws.ts sendCommand) ── */

export function serialSendArm(): void {
  sendSerialFrame(76, encodeCommandLong(
    serial.targetSysId, serial.targetCompId,
    400, 0, 1, 0, 0, 0, 0, 0, 0,
  ));
}

export function serialSendDisarm(): void {
  sendSerialFrame(76, encodeCommandLong(
    serial.targetSysId, serial.targetCompId,
    400, 0, 0, 0, 0, 0, 0, 0, 0,
  ));
}

export function serialSendMode(mode: number): void {
  sendSerialFrame(11, encodeSetMode(serial.targetSysId, 209, mode));
}

export function serialSendRtl(): void {
  serialSendMode(11); // RTL mode for copter
}

export function serialSendParamRequestAll(): void {
  sendSerialFrame(21, encodeParamRequestList(
    serial.targetSysId, serial.targetCompId,
  ));
}

export function serialSendParamSet(name: string, value: number, type: number = 9): void {
  sendSerialFrame(23, encodeParamSet(
    serial.targetSysId, serial.targetCompId, name, value, type,
  ));
}

export function serialSendCommandLong(
  command: number,
  p1 = 0, p2 = 0, p3 = 0, p4 = 0, p5 = 0, p6 = 0, p7 = 0,
): void {
  sendSerialFrame(76, encodeCommandLong(
    serial.targetSysId, serial.targetCompId,
    command, 0, p1, p2, p3, p4, p5, p6, p7,
  ));
}

/* ── Mission upload state machine (WebSerial direct mode) ───────────────
 *
 * Mirrors backend/commands/_mission.py:_upload_mission so the FC sees the
 * exact same MISSION_COUNT → MISSION_REQUEST_INT → MISSION_ITEM_INT → ...
 * → MISSION_ACK handshake as it would from a WebSocket-backed upload.
 *
 * The FC drives the cadence — every MISSION_REQUEST(_INT) we receive maps to
 * a single MISSION_ITEM_INT response. The 5s per-item timer guards against a
 * silent FC; the 30s overall guard catches the link-up-but-not-responding
 * case so the UI doesn't hang.
 */

interface UploadState {
  items: MissionItem[];
  resolve: (result: { ok: boolean; error?: string }) => void;
  itemTimer: ReturnType<typeof setTimeout> | null;
  overallTimer: ReturnType<typeof setTimeout> | null;
  pending: boolean;
  lastSeq: number;  // last seq the FC requested, -1 before first MISSION_REQUEST
}

let upload: UploadState | null = null;

function _resolveUpload(result: { ok: boolean; error?: string }): void {
  if (!upload) return;
  const u = upload;
  upload = null;
  if (u.itemTimer) clearTimeout(u.itemTimer);
  if (u.overallTimer) clearTimeout(u.overallTimer);
  if (u.pending) u.resolve(result);
}

function _onMissionRequest(seq: number): void {
  if (!upload?.pending) return;
  if (seq < 0 || seq >= upload.items.length) {
    _resolveUpload({ ok: false, error: `FC requested out-of-range seq ${seq}` });
    return;
  }
  const item = upload.items[seq];
  upload.lastSeq = seq;
  sendSerialFrame(73, encodeMissionItemInt(
    serial.targetSysId, serial.targetCompId,
    item.seq, item.command, item.frame,
    item.current, item.autocontinue, 0,  // missionType 0 = MAV_MISSION_TYPE_MISSION
    item.p1, item.p2, item.p3, item.p4,
    item.x, item.y, item.z,
  ));
  // 5s per-item watchdog: if the FC never asks for the next seq, fail loud.
  if (upload.itemTimer) clearTimeout(upload.itemTimer);
  upload.itemTimer = setTimeout(() => {
    _resolveUpload({ ok: false, error: `FC stopped requesting items after seq ${seq}` });
  }, 5000);
}

function _onMissionAck(type: number): void {
  if (!upload?.pending) return;
  // MAV_MISSION_ACCEPTED = 0. Anything else is a rejection from AP_Mission.
  if (type === 0) {
    _resolveUpload({ ok: true });
  } else {
    _resolveUpload({ ok: false, error: `MISSION_ACK type=${type}` });
  }
}

export function isSerialMissionUploading(): boolean {
  return upload?.pending === true;
}

export async function serialUploadMission(
  waypoints: Waypoint[], takeoffAlt: number,
): Promise<{ ok: boolean; error?: string }> {
  if (!isSerialConnected()) return { ok: false, error: 'Not connected via serial' };
  if (upload?.pending) return { ok: false, error: 'Another upload is in progress' };

  const validation = validateMissionWaypoints(waypoints);
  if (!validation.ok) return validation;

  const items = buildMissionItems(waypoints, takeoffAlt);

  return new Promise((resolve) => {
    upload = {
      items, resolve,
      itemTimer: null,
      overallTimer: setTimeout(() => {
        _resolveUpload({ ok: false, error: 'Mission upload timed out (30s overall)' });
      }, 30000),
      pending: true,
      lastSeq: -1,
    };
    sendSerialFrame(44, encodeMissionCount(
      serial.targetSysId, serial.targetCompId, items.length, 0,
    ));
  });
}

export function serialClearMission(): void {
  if (!isSerialConnected()) return;
  sendSerialFrame(45, encodeMissionClearAll(
    serial.targetSysId, serial.targetCompId, 0,
  ));
}
