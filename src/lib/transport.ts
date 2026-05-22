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
} from './mavlink';
import { openSerial, serialWrite, serialReadLoop, isWebSerialSupported } from './serial';
import type { SerialConnection } from './serial';
import { addToast } from './stores.svelte';

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
        dispatchFrame(frame, serial.handlers);
      }
    }).catch((e) => { console.error('[Serial] read loop error', e); }).finally(() => {
      const wasRunning = serial.running;
      serial.running = false;
      if (wasRunning) {
        addToast('Serial connection lost', 'error', 8000);
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
