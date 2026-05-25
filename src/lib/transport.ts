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
  encodeMissionSetCurrent,
  encodeMissionRequestList,
  encodeMissionRequestInt,
  encodeMissionAck,
  encodeLogRequestList,
  encodeLogRequestData,
  encodeLogRequestEnd,
  encodeCommandAck,
} from './mavlink';
import { openSerial, serialWrite, serialReadLoop, isWebSerialSupported } from './serial';
import type { SerialConnection } from './serial';
import { addToast, addEvent, app } from './stores.svelte';
import { t } from './i18n.svelte';
import {
  buildMissionItems, buildFenceItems, missionItemsToWaypoints,
  validateMissionWaypoints, validateFencePolygon,
} from './missionUpload';
import type { MissionItem, RawMissionItem } from './missionUpload';
import type { Waypoint } from './types';
import {
  logState, setLogList, startDownload,
  appendLogChunkBinary, updateDownloadProgress, completeDownload, cancelDownload,
} from './logStore.svelte';
import type { LogEntry as LogEntryShape } from './logStore.svelte';

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
            const p = _padView(frame.payload, 2);
            _onMissionRequest(p.getUint16(0, true));
          } else if (frame.msgId === 47) {
            // MISSION_ACK type is at offset 2 (after target_system, target_component).
            const p = _padView(frame.payload, 3);
            _onMissionAck(p.getUint8(2));
          }
        }
        // Mission download state machine listens on MISSION_COUNT (44) and
        // MISSION_ITEM_INT (73). Upload and download are mutually exclusive,
        // so the order of these intercepts doesn't matter.
        if (download.pending) {
          if (frame.msgId === 44) _onMissionCountDl(_padView(frame.payload, 4));
          else if (frame.msgId === 73) _onMissionItemIntDl(_padView(frame.payload, 37));
        }
        // Log list / download state machines listen on LOG_ENTRY (118) and
        // LOG_DATA (120). Internal intercept first; external dispatch still
        // runs so user handlers see the frames if registered.
        if (logSession.listPending && frame.msgId === 118) {
          _onLogEntry(_padView(frame.payload, 14));
        } else if (logSession.dlPending && frame.msgId === 120) {
          _onLogData(_padView(frame.payload, 7));
        }
        // Compass cal progress: translate binary MAG_CAL_PROGRESS (191) and
        // MAG_CAL_REPORT (192) into the same locale-aware event-stream
        // entries the backend emits, so the existing CalibrationPanel
        // regex heuristic (compassParsed) keeps working unchanged.
        if (frame.msgId === 191) _onMagCalProgress(_padView(frame.payload, 17));
        else if (frame.msgId === 192) _onMagCalReport(_padView(frame.payload, 44));
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
      if (download.pending) {
        _resolveDownload({ ok: false, error: 'Serial link lost mid-download' });
      }
      // Tear down any in-flight log operation so its watchdog doesn't
      // fire spuriously after disconnect.
      if (logSession.listPending) _resolveLogList({ ok: false, error: 'Serial link lost' });
      if (logSession.dlPending) _abortLogDownload('Serial link lost mid-download');
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

// MAVLink 2 zero-trim defense for the in-loop interceptors that read at
// specific offsets. dispatchFrame() pads via padPayload() before invoking
// user handlers, but our state-machine intercepts run on the raw payload
// BEFORE dispatchFrame, so trimmed frames would silently drop without this.
// Mirrors backend/mavlink_handlers.py:_pad. See protocol_design.md #2.
function _padView(p: DataView, minBytes: number): DataView {
  if (p.byteLength >= minBytes) return p;
  const buf = new Uint8Array(minBytes);
  buf.set(new Uint8Array(p.buffer, p.byteOffset, p.byteLength));
  return new DataView(buf.buffer);
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

/**
 * Gimbal pitch/yaw: wraps the COMMAND_INT (msg 75) path the gimbal manager
 * handler expects. Mirrors backend cmd_gimbal_pitchyaw at
 * backend/commands/_hardware.py — same NaN-as-skip semantics for the four
 * angle/rate params, same flags-as-x bitfield, same instance-as-z (z is the
 * float slot but the AP handler casts to uint8). See AP_Mount.cpp:363-417.
 */
export function serialGimbalPitchYaw(data: {
  pitch?: number; yaw?: number;
  pitch_rate?: number; yaw_rate?: number;
  flags?: number; instance?: number;
}): void {
  if (!isSerialConnected()) return;
  const f = (v: number | undefined): number => (v == null ? NaN : Number(v));
  const pitch = f(data.pitch);
  const yaw = f(data.yaw);
  const pitchRate = f(data.pitch_rate);
  const yawRate = f(data.yaw_rate);
  const flags = Number(data.flags ?? 0);
  const instance = Number(data.instance ?? 0);

  const payload = new Uint8Array(35);
  const dv = new DataView(payload.buffer);
  dv.setFloat32(0, pitch, true);
  dv.setFloat32(4, yaw, true);
  dv.setFloat32(8, pitchRate, true);
  dv.setFloat32(12, yawRate, true);
  dv.setInt32(16, flags | 0, true);     // x: GIMBAL_MANAGER_FLAGS bitfield
  dv.setInt32(20, 0, true);              // y: unused
  dv.setFloat32(24, instance, true);     // z: gimbal device id
  dv.setUint16(28, 1000, true);          // command = MAV_CMD_DO_GIMBAL_MANAGER_PITCHYAW
  dv.setUint8(30, serial.targetSysId);
  dv.setUint8(31, serial.targetCompId);
  dv.setUint8(32, 0);                    // frame (unused for COMMAND_INT)
  dv.setUint8(33, 0);                    // current
  dv.setUint8(34, 0);                    // autocontinue
  sendSerialFrame(75, payload);
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
  missionType: number;   // 0=MISSION, 1=FENCE, 2=RALLY — passed through on
                         // MISSION_COUNT + each MISSION_ITEM_INT so the FC's
                         // AP_Mission/AP_Fence routes the upload correctly.
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
    item.current, item.autocontinue, upload.missionType,
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

function _startUpload(items: MissionItem[], missionType: number): Promise<{ ok: boolean; error?: string }> {
  return new Promise((resolve) => {
    upload = {
      items, missionType, resolve,
      itemTimer: null,
      overallTimer: setTimeout(() => {
        _resolveUpload({ ok: false, error: 'Mission upload timed out (30s overall)' });
      }, 30000),
      pending: true,
      lastSeq: -1,
    };
    sendSerialFrame(44, encodeMissionCount(
      serial.targetSysId, serial.targetCompId, items.length, missionType,
    ));
  });
}

export async function serialUploadMission(
  waypoints: Waypoint[], takeoffAlt: number,
): Promise<{ ok: boolean; error?: string }> {
  if (!isSerialConnected()) return { ok: false, error: 'Not connected via serial' };
  if (upload?.pending) return { ok: false, error: 'Another upload is in progress' };
  if (download.pending) return { ok: false, error: 'A mission download is in progress' };

  const validation = validateMissionWaypoints(waypoints);
  if (!validation.ok) return validation;
  return _startUpload(buildMissionItems(waypoints, takeoffAlt), 0);
}

/**
 * Fence polygon upload. Same protocol as a mission upload but with
 * mission_type=1 (MAV_MISSION_TYPE_FENCE) on both MISSION_COUNT and every
 * MISSION_ITEM_INT, so AP_Fence routes the upload to the fence buffer
 * instead of the mission buffer. Mirrors backend cmd_fence_upload.
 */
export async function serialUploadFence(
  polygon: { lat: number; lon: number }[],
): Promise<{ ok: boolean; error?: string }> {
  if (!isSerialConnected()) return { ok: false, error: 'Not connected via serial' };
  if (upload?.pending) return { ok: false, error: 'Another upload is in progress' };
  if (download.pending) return { ok: false, error: 'A mission download is in progress' };

  const validation = validateFencePolygon(polygon);
  if (!validation.ok) return validation;
  return _startUpload(buildFenceItems(polygon), 1);
}

export function serialClearMission(): void {
  if (!isSerialConnected()) return;
  sendSerialFrame(45, encodeMissionClearAll(
    serial.targetSysId, serial.targetCompId, 0,
  ));
}

export function serialMissionSetCurrent(seq: number): void {
  if (!isSerialConnected()) return;
  sendSerialFrame(41, encodeMissionSetCurrent(
    serial.targetSysId, serial.targetCompId, seq,
  ));
}

/* ── Mission DOWNLOAD state machine (WebSerial direct mode) ─────────────
 *
 * GCS → MISSION_REQUEST_LIST (43)
 * FC  → MISSION_COUNT (44)
 * GCS → MISSION_REQUEST_INT (51) for each seq 0..count-1
 * FC  → MISSION_ITEM_INT (73) for each
 * GCS → MISSION_ACK (47, type=0) on completion
 *
 * Mirrors backend handle_mission_count / handle_mission_item_int /
 * _request_dl_item in backend/mavlink_handlers.py. The items→Waypoint
 * collapse runs through missionItemsToWaypoints so the on-screen layout
 * matches a backend-mediated download for the same FC state.
 */

interface DownloadState {
  pending: boolean;
  resolve: ((r: { ok: boolean; error?: string; waypoints?: Waypoint[] }) => void) | null;
  items: (RawMissionItem | null)[];
  total: number;
  timer: ReturnType<typeof setTimeout> | null;
}

const download: DownloadState = {
  pending: false, resolve: null, items: [], total: 0, timer: null,
};

function _resetDownloadTimer(): void {
  if (download.timer) clearTimeout(download.timer);
  download.timer = setTimeout(() => {
    _resolveDownload({ ok: false, error: 'Mission download stalled (no FC reply in 5s)' });
  }, 5000);
}

function _resolveDownload(result: { ok: boolean; error?: string; waypoints?: Waypoint[] }): void {
  if (!download.pending) return;
  download.pending = false;
  if (download.timer) { clearTimeout(download.timer); download.timer = null; }
  download.items = [];
  download.total = 0;
  const r = download.resolve;
  download.resolve = null;
  if (r) r(result);
}

function _onMissionCountDl(p: DataView): void {
  // p is pre-padded to ≥4 bytes by the read-loop interceptor.
  if (!download.pending) return;
  const count = p.getUint16(0, true);
  download.total = count;
  download.items = new Array(count).fill(null);
  if (count === 0) {
    // FC has no mission. Send the ACK so we don't leak the request, and
    // resolve with an empty waypoint list.
    sendSerialFrame(47, encodeMissionAck(serial.targetSysId, serial.targetCompId, 0, 0));
    _resolveDownload({ ok: true, waypoints: [] });
    return;
  }
  sendSerialFrame(51, encodeMissionRequestInt(
    serial.targetSysId, serial.targetCompId, 0, 0,
  ));
  _resetDownloadTimer();
}

function _onMissionItemIntDl(p: DataView): void {
  // p is pre-padded to ≥37 bytes by the read-loop interceptor (matches
  // backend handle_mission_item_int's `_pad(p, 37)` at mavlink_handlers.py:406).
  if (!download.pending) return;
  // MISSION_ITEM_INT layout (matches decodeMissionItemInt at messages.ts:345
  // and backend handle_mission_item_int at mavlink_handlers.py:402-427).
  const p1 = p.getFloat32(0, true);
  const p2 = p.getFloat32(4, true);
  const p3 = p.getFloat32(8, true);
  const p4 = p.getFloat32(12, true);
  const x = p.getInt32(16, true);
  const y = p.getInt32(20, true);
  const z = p.getFloat32(24, true);
  const seq = p.getUint16(28, true);
  const cmd = p.getUint16(30, true);
  const frame = p.getUint8(34);
  const current = p.getUint8(35);
  const autocontinue = p.getUint8(36);

  if (seq < download.total) {
    download.items[seq] = {
      seq, cmd,
      lat: x / 1e7, lon: y / 1e7, alt: z,
      p1, p2, p3, p4,
      frame, current, autocontinue,
    };
  }

  if (seq + 1 < download.total) {
    sendSerialFrame(51, encodeMissionRequestInt(
      serial.targetSysId, serial.targetCompId, seq + 1, 0,
    ));
    _resetDownloadTimer();
  } else {
    // Final item received — send the MISSION_ACK and collapse to Waypoints.
    sendSerialFrame(47, encodeMissionAck(serial.targetSysId, serial.targetCompId, 0, 0));
    const items: RawMissionItem[] = download.items.filter((i): i is RawMissionItem => i !== null);
    const waypoints = missionItemsToWaypoints(items);
    _resolveDownload({ ok: true, waypoints });
  }
}

export async function serialDownloadMission(): Promise<{ ok: boolean; error?: string; waypoints?: Waypoint[] }> {
  if (!isSerialConnected()) return { ok: false, error: 'Not connected via serial' };
  if (download.pending) return { ok: false, error: 'Another mission download is in progress' };
  if (upload?.pending) return { ok: false, error: 'A mission upload is in progress' };

  return new Promise((resolve) => {
    download.pending = true;
    download.resolve = resolve;
    download.items = [];
    download.total = 0;
    _resetDownloadTimer();
    sendSerialFrame(43, encodeMissionRequestList(
      serial.targetSysId, serial.targetCompId, 0,
    ));
  });
}

/* ── Compass calibration (WebSerial direct mode) ─────────────────────────
 *
 * GCS → MAV_CMD_DO_START_MAG_CAL (42424) via COMMAND_LONG
 * FC  → MAG_CAL_PROGRESS (191) at ~10Hz with pct byte at offset 16
 * FC  → MAG_CAL_REPORT (192) once per compass with cal_status at offset 42
 *        (cal_status == 4 = MAG_CAL_SUCCESS, anything else = failed)
 * GCS → MAV_CMD_DO_ACCEPT_MAG_CAL (42425) when done, or
 *       MAV_CMD_DO_CANCEL_MAG_CAL (42426) to abort
 *
 * Mirrors backend's handle_mag_cal_progress / handle_mag_cal_report at
 * backend/mavlink_handlers.py:215-244 exactly — same dedup (5% bucket,
 * one-shot done flag) so the events sent to addEvent() match what the
 * WS-mediated path would have produced. CalibrationPanel's compassParsed
 * regex matches both locales.
 */

interface MagCalState {
  pct: number;     // last %% emitted, -1 = none
  done: boolean;   // one-shot to avoid double "complete" or progress-after-done
}

const magCal: MagCalState = { pct: -1, done: false };

function _resetMagCal(): void {
  magCal.pct = -1;
  magCal.done = false;
}

function _onMagCalProgress(p: DataView): void {
  // p is pre-padded to ≥17 bytes (matches backend's `_pad(p, 17)`).
  if (magCal.done) return;
  const pct = p.getUint8(16);
  // Emit only when crossing a new 5% bucket — same filter as backend
  // handle_mag_cal_progress (mavlink_handlers.py:223-226). Prevents 200+
  // events flooding the log over a 30s cal.
  if (pct > magCal.pct && Math.floor(pct / 5) !== Math.floor(magCal.pct / 5)) {
    magCal.pct = pct;
    addEvent({
      type: 'event',
      time: new Date().toLocaleTimeString(),
      text: t('cal.s.compassPct').replace('{pct}', String(pct)),
      event_type: 'cal_compass',
    });
  } else if (pct > magCal.pct) {
    magCal.pct = pct;  // track the value so the next bucket cross fires
  }
}

function _onMagCalReport(p: DataView): void {
  // p is pre-padded to ≥44 bytes (matches backend's `_pad(p, 44)`).
  // cal_status is at offset 42 — see backend handler.
  if (magCal.done) return;
  const calStatus = p.getUint8(42);
  magCal.done = true;
  magCal.pct = -1;
  if (calStatus === 4) {
    // MAG_CAL_SUCCESS. Backend emits TWO events (done + reboot hint);
    // CalibrationPanel only reads the first for completion detection but
    // we replicate both so the message log looks identical.
    addEvent({ type: 'event', time: new Date().toLocaleTimeString(),
               text: t('cal.s.compassDone'), event_type: 'cal_compass' });
    addEvent({ type: 'event', time: new Date().toLocaleTimeString(),
               text: t('cal.s.compassReboot'), event_type: 'cal_compass' });
  } else {
    addEvent({ type: 'event', time: new Date().toLocaleTimeString(),
               text: t('cal.s.compassFailed'), event_type: 'cal_compass' });
  }
}

export function serialCalCompass(): void {
  if (!isSerialConnected()) return;
  _resetMagCal();
  // MAV_CMD_DO_START_MAG_CAL: p1=mag_mask(0=all), p2-p4=options(0). Matches
  // backend cmd_cal_compass (send_cmd(link, 42424, p1=0, p2=0, p3=0, p4=0)).
  serialSendCommandLong(42424, 0, 0, 0, 0, 0, 0, 0);
}

export function serialCalCompassAccept(): void {
  if (!isSerialConnected()) return;
  serialSendCommandLong(42425, 0, 0, 0, 0, 0, 0, 0);
}

export function serialCalCancel(): void {
  if (!isSerialConnected()) return;
  // MAV_CMD_DO_CANCEL_MAG_CAL only cancels MAG cal (per cmd_cal_cancel
  // comment in backend/commands/_setup.py:62-68 — gyro/level/baro complete
  // in <1s and have no FC-side cancel). UI state reset stays the same.
  serialSendCommandLong(42426, 0, 0, 0, 0, 0, 0, 0);
  _resetMagCal();
}

export function serialCalGyro(): void {
  if (!isSerialConnected()) return;
  // MAV_CMD_PREFLIGHT_CALIBRATION (241), p1=1 = gyro cal.
  serialSendCommandLong(241, 1, 0, 0, 0, 0, 0, 0);
}

export function serialCalLevel(): void {
  if (!isSerialConnected()) return;
  // MAV_CMD_PREFLIGHT_CALIBRATION (241), p5=4 = level (board-orientation) cal.
  serialSendCommandLong(241, 0, 0, 0, 0, 4, 0, 0);
}

export function serialCalBaro(): void {
  if (!isSerialConnected()) return;
  // MAV_CMD_PREFLIGHT_CALIBRATION (241), p3=1 = ground pressure cal.
  serialSendCommandLong(241, 0, 0, 1, 0, 0, 0, 0);
}

/**
 * Accel calibration uses a TWO-PHASE protocol. Phase 1 (serialCalAccel) is
 * a standard COMMAND_LONG. Phase 2 (serialCalAccelNext) is NOT — it abuses
 * COMMAND_ACK (msg 77) with field semantics that contradict the MAVLink
 * spec. Anyone "cleaning up" the wire by sending MAV_CMD_ACCELCAL_VEHICLE_POS
 * (42429) or result=MAV_RESULT_ACCEPTED(0) will silently break accel cal.
 *
 * See [[feedback-protocol-discipline]] and protocol_design.md #1 — this is
 * the canonical example of FC-coupled code that looks wrong but is correct.
 */
export function serialCalAccel(): void {
  if (!isSerialConnected()) return;
  // MAV_CMD_PREFLIGHT_CALIBRATION (241), p5=1 = accel cal. Matches backend
  // cmd_cal_accel at backend/commands/_setup.py:27-29.
  serialSendCommandLong(241, 0, 0, 0, 0, 1, 0, 0);
}

export function serialCalAccelNext(): void {
  if (!isSerialConnected()) return;
  // AP_AccelCal::handle_command_ack (libraries/AP_AccelCal/AP_AccelCal.cpp:
  // 366-393) hijacks COMMAND_ACK with private semantics:
  //   if (packet.command > 6)                        return;  // not a MAV_CMD value
  //   if (packet.result != TEMPORARILY_REJECTED(1))  return;  // result MUST be 1
  // QGC sends command=0, result=1; we mirror QGC. Backend equivalent at
  // backend/commands/_setup.py:cmd_cal_accel_next (lines 47-58).
  sendSerialFrame(77, encodeCommandAck(0, 1));
}

/* ── Log list + download state machines (WebSerial direct mode) ─────────
 *
 * List: GCS → LOG_REQUEST_LIST (117). FC streams LOG_ENTRY (118) per log; the
 *       entry with id == last_log_num signals end-of-list and resolves the
 *       promise.
 * Download: GCS → LOG_REQUEST_DATA (119) with (ofs, count=4500). FC streams
 *           LOG_DATA (120) chunks ≤90 bytes. Matches backend's per-chunk
 *           re-request loop at backend/mavlink_handlers.py:660 so the FC
 *           sees an identical request cadence. count==0 in a LOG_DATA is
 *           AP_Logger's "EOF / log unreadable" signal — finalize as truncated.
 * Cancel:  GCS → LOG_REQUEST_END (122). Aborts any in-flight download.
 */

const LOG_CHUNK_BYTES = 90 * 50;  // matches backend cmd_log_download

interface LogSessionState {
  listPending: boolean;
  listResolve: ((r: { ok: boolean; error?: string }) => void) | null;
  listTimer: ReturnType<typeof setTimeout> | null;
  listEntries: LogEntryShape[];

  dlPending: boolean;
  dlResolve: ((r: { ok: boolean; error?: string }) => void) | null;
  dlTimer: ReturnType<typeof setTimeout> | null;
  dlId: number;
  dlSize: number;
  dlOfs: number;
}

const logSession: LogSessionState = {
  listPending: false, listResolve: null, listTimer: null, listEntries: [],
  dlPending: false, dlResolve: null, dlTimer: null, dlId: -1, dlSize: 0, dlOfs: 0,
};

function _resolveLogList(result: { ok: boolean; error?: string }): void {
  if (!logSession.listPending) return;
  logSession.listPending = false;
  if (logSession.listTimer) { clearTimeout(logSession.listTimer); logSession.listTimer = null; }
  const r = logSession.listResolve;
  logSession.listResolve = null;
  if (r) r(result);
}

function _onLogEntry(p: DataView): void {
  // p is pre-padded to ≥14 bytes by the read-loop interceptor.
  const entry: LogEntryShape = {
    time_utc: p.getUint32(0, true),
    size: p.getUint32(4, true),
    id: p.getUint16(8, true),
    // num_logs at offset 10 (uint16) is informational; last_log_num at 12 is
    // what we actually check.
  };
  const lastLogNum = p.getUint16(12, true);
  logSession.listEntries.push(entry);
  // Reset the watchdog every time a new entry shows up — slow FCs can take
  // tens of seconds to list 100+ logs.
  if (logSession.listTimer) clearTimeout(logSession.listTimer);
  logSession.listTimer = setTimeout(() => {
    _resolveLogList({ ok: false, error: 'FC stopped sending LOG_ENTRY' });
  }, 5000);
  if (entry.id === lastLogNum) {
    setLogList([...logSession.listEntries]);
    _resolveLogList({ ok: true });
  }
}

function _abortLogDownload(error: string): void {
  if (!logSession.dlPending) return;
  logSession.dlPending = false;
  if (logSession.dlTimer) { clearTimeout(logSession.dlTimer); logSession.dlTimer = null; }
  cancelDownload();
  const r = logSession.dlResolve;
  logSession.dlResolve = null;
  if (r) r({ ok: false, error });
}

function _finishLogDownload(truncated: boolean): void {
  if (!logSession.dlPending) return;
  const id = logSession.dlId;
  const size = logSession.dlOfs;
  logSession.dlPending = false;
  if (logSession.dlTimer) { clearTimeout(logSession.dlTimer); logSession.dlTimer = null; }
  // Pass empty b64 — the streaming chunks already populated logState._chunks;
  // completeDownload assembles + triggers the browser download.
  completeDownload(id, undefined, size);
  const r = logSession.dlResolve;
  logSession.dlResolve = null;
  if (r) r({ ok: !truncated, error: truncated ? 'Download truncated (count=0 from FC)' : undefined });
}

function _onLogData(p: DataView): void {
  // p is pre-padded to ≥7 bytes; the actual data chunk extends beyond and
  // is clamped to min(count, byteLength-7) below to tolerate trimmed tails.
  const ofs = p.getUint32(0, true);
  const logId = p.getUint16(4, true);
  const count = p.getUint8(6);
  if (logId !== logSession.dlId) return;
  // FC count==0 is the AP_Logger "EOF / unreadable log" sentinel — see
  // backend handle_log_data at backend/mavlink_handlers.py:631.
  if (count === 0) {
    _finishLogDownload(true);
    return;
  }
  const data = new Uint8Array(p.buffer, p.byteOffset + 7, Math.min(count, p.byteLength - 7));
  appendLogChunkBinary(logId, ofs, data);
  const end = ofs + data.length;
  if (end > logSession.dlOfs) logSession.dlOfs = end;
  updateDownloadProgress(logSession.dlOfs, logSession.dlSize);

  if (logSession.dlTimer) clearTimeout(logSession.dlTimer);
  logSession.dlTimer = setTimeout(() => {
    _abortLogDownload('FC stopped sending LOG_DATA');
  }, 5000);

  if (logSession.dlOfs >= logSession.dlSize) {
    _finishLogDownload(false);
    return;
  }
  // Mirror backend's per-chunk re-request — AP_Logger treats duplicate
  // LOG_REQUEST_DATA as harmless and won't retransmit already-acked chunks.
  const remaining = logSession.dlSize - logSession.dlOfs;
  const next = Math.min(LOG_CHUNK_BYTES, remaining);
  sendSerialFrame(119, encodeLogRequestData(
    serial.targetSysId, serial.targetCompId,
    logId, logSession.dlOfs, next,
  ));
}

export function isSerialLogBusy(): boolean {
  return logSession.listPending || logSession.dlPending;
}

export async function serialLogList(): Promise<{ ok: boolean; error?: string }> {
  if (!isSerialConnected()) return { ok: false, error: 'Not connected via serial' };
  if (logSession.listPending || logSession.dlPending) {
    return { ok: false, error: 'Another log operation is in progress' };
  }
  return new Promise((resolve) => {
    logSession.listPending = true;
    logSession.listResolve = resolve;
    logSession.listEntries = [];
    logSession.listTimer = setTimeout(() => {
      _resolveLogList({ ok: false, error: 'LOG_REQUEST_LIST timed out (no LOG_ENTRY in 5s)' });
    }, 5000);
    sendSerialFrame(117, encodeLogRequestList(
      serial.targetSysId, serial.targetCompId, 0, 0xFFFF,
    ));
  });
}

export async function serialLogDownload(id: number): Promise<{ ok: boolean; error?: string }> {
  if (!isSerialConnected()) return { ok: false, error: 'Not connected via serial' };
  if (logSession.listPending || logSession.dlPending) {
    return { ok: false, error: 'Another log operation is in progress' };
  }
  const entry = logState.list.find((e) => e.id === id);
  if (!entry) return { ok: false, error: 'Log not in list — request the list first' };
  if (entry.size === 0) return { ok: false, error: 'Log is empty' };

  startDownload(id, entry.size);
  return new Promise((resolve) => {
    logSession.dlPending = true;
    logSession.dlResolve = resolve;
    logSession.dlId = id;
    logSession.dlSize = entry.size;
    logSession.dlOfs = 0;
    logSession.dlTimer = setTimeout(() => {
      _abortLogDownload('LOG_REQUEST_DATA timed out (no LOG_DATA in 5s)');
    }, 5000);
    const chunk = Math.min(LOG_CHUNK_BYTES, entry.size);
    sendSerialFrame(119, encodeLogRequestData(
      serial.targetSysId, serial.targetCompId, id, 0, chunk,
    ));
  });
}

export function serialLogCancel(): void {
  if (!isSerialConnected()) return;
  sendSerialFrame(122, encodeLogRequestEnd(
    serial.targetSysId, serial.targetCompId,
  ));
  if (logSession.dlPending) _abortLogDownload('Cancelled');
  if (logSession.listPending) _resolveLogList({ ok: false, error: 'Cancelled' });
}
