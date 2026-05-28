/**
 * Wire-byte contract test for _serialDispatch ↔ backend _DISPATCH semantic parity.
 *
 * The existing test_contract_serial_dispatch.py only verifies that every
 * backend command key is present in _serialDispatch (and vice versa). The
 * 2026-05-28 ultrareview found 7 bugs where key parity passed but wire
 * bytes diverged — camera_trigger sent all zeros (no-op), do_set_roi sent
 * cmd 197 (DO_SET_ROI_NONE) instead of 201, takeoff/guided_goto skipped
 * mode switches, mission_set_current ignored the HOME/TAKEOFF seq offset,
 * mission_start omitted the explicit MISSION_START cmd, param_save did
 * FC NVRAM instead of host JSON backup.
 *
 * This test decodes the frames each serial dispatch entry emits and
 * asserts the command id + relevant params + mode-switch ordering match
 * what the corresponding backend cmd_* handler would have sent. Run
 * alongside the python contract test for both directions of guarantee.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const writes: Uint8Array[] = [];
let readLoopResolve: ((v: void) => void) | null = null;
let _isPlaneFlag = false;

vi.mock('./serial', () => ({
  isWebSerialSupported: () => true,
  openSerial: vi.fn(async () => ({
    readable: {} as ReadableStream<Uint8Array>,
    writable: {} as WritableStream<Uint8Array>,
    close: vi.fn(async () => {}),
    info: {},
  })),
  serialWrite: vi.fn(async (_conn: unknown, data: Uint8Array) => {
    writes.push(new Uint8Array(data));
  }),
  serialReadLoop: vi.fn(
    (_conn: unknown, _onChunk: (c: Uint8Array) => void) =>
      new Promise<void>((resolve) => {
        readLoopResolve = resolve;
      }),
  ),
}));

vi.mock('./stores.svelte', () => ({
  app: { activeTransport: 'none' as 'none' | 'ws' | 'serial', drone: {} },
  addToast: vi.fn(),
  addEvent: vi.fn(),
  isPlane: () => _isPlaneFlag,
}));

vi.mock('./i18n.svelte', () => ({
  t: (key: string) => key,
  i18nState: { locale: 'en' },
}));

vi.mock('./logStore.svelte', () => ({
  logState: { list: [], downloading: false, downloadId: -1, progress: 0 },
  setLogList: vi.fn(),
  startDownload: vi.fn(),
  appendLogChunkBinary: vi.fn(),
  updateDownloadProgress: vi.fn(),
  completeDownload: vi.fn(),
  cancelDownload: vi.fn(),
}));

const wsSendCommand = vi.fn();
vi.mock('./ws', () => ({
  sendCommand: wsSendCommand,
}));

// Import AFTER mocks
import { connectSerial, disconnectSerial, dispatch } from './transport';

// ─────────────────────────────────────────────────────────────────────────
// Frame decode helpers — MAVLink 2 wire layout
// ─────────────────────────────────────────────────────────────────────────

interface DecodedFrame {
  msgId: number;
  payload: Uint8Array;  // re-padded if zero-trimmed
}

function decodeFrame(bytes: Uint8Array, expectedPayloadLen?: number): DecodedFrame {
  // MAVLink 2 header: STX(1) len(1) incompat(1) compat(1) seq(1) sys(1) comp(1) msgId(3)
  // then payload, then CRC(2).
  const len = bytes[1];
  const msgId = bytes[7] | (bytes[8] << 8) | (bytes[9] << 16);
  let payload = bytes.slice(10, 10 + len);
  if (expectedPayloadLen !== undefined && payload.length < expectedPayloadLen) {
    // MAVLink 2 zero-trim — pad back to full length so offset reads work.
    const padded = new Uint8Array(expectedPayloadLen);
    padded.set(payload);
    payload = padded;
  }
  return { msgId, payload };
}

interface CommandLong {
  command: number;
  p1: number;
  p2: number;
  p3: number;
  p4: number;
  p5: number;
  p6: number;
  p7: number;
  targetSys: number;
  targetComp: number;
}

function decodeCommandLong(bytes: Uint8Array): CommandLong {
  const { msgId, payload } = decodeFrame(bytes, 33);
  expect(msgId).toBe(76);  // COMMAND_LONG
  const dv = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  return {
    p1: dv.getFloat32(0, true),
    p2: dv.getFloat32(4, true),
    p3: dv.getFloat32(8, true),
    p4: dv.getFloat32(12, true),
    p5: dv.getFloat32(16, true),
    p6: dv.getFloat32(20, true),
    p7: dv.getFloat32(24, true),
    command: dv.getUint16(28, true),
    targetSys: dv.getUint8(30),
    targetComp: dv.getUint8(31),
  };
}

function decodeSetMode(bytes: Uint8Array): { customMode: number; baseMode: number; targetSys: number } {
  const { msgId, payload } = decodeFrame(bytes, 6);
  expect(msgId).toBe(11);  // SET_MODE
  const dv = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  return {
    customMode: dv.getUint32(0, true),
    targetSys: dv.getUint8(4),
    baseMode: dv.getUint8(5),
  };
}

function decodeMissionSetCurrent(bytes: Uint8Array): { seq: number } {
  const { msgId, payload } = decodeFrame(bytes, 4);
  expect(msgId).toBe(41);
  const dv = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  return { seq: dv.getUint16(0, true) };
}

function decodePositionTargetGlobal(bytes: Uint8Array): {
  lat: number;
  lon: number;
  alt: number;
  typeMask: number;
  frame: number;
} {
  const { msgId, payload } = decodeFrame(bytes, 53);
  expect(msgId).toBe(86);
  const dv = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  return {
    lat: dv.getInt32(4, true) / 1e7,
    lon: dv.getInt32(8, true) / 1e7,
    alt: dv.getFloat32(12, true),
    typeMask: dv.getUint16(48, true),
    frame: dv.getUint8(52),
  };
}

// Skip the connect-boot frames (heartbeat + REQUEST_DATA_STREAMs) and
// return only msgIds that this test cares about.
function filterAppFrames(allWrites: Uint8Array[]): Uint8Array[] {
  return allWrites.filter((w) => {
    const msgId = w[7] | (w[8] << 8) | (w[9] << 16);
    // Drop boot-time msgs: HEARTBEAT(0), REQUEST_DATA_STREAM(66).
    return msgId !== 0 && msgId !== 66;
  });
}

beforeEach(async () => {
  writes.length = 0;
  wsSendCommand.mockClear();
  readLoopResolve = null;
  _isPlaneFlag = false;
  await connectSerial(115200, {});
  writes.length = 0;  // discard boot frames
});

afterEach(async () => {
  const r = readLoopResolve;
  readLoopResolve = null;
  if (r) r();
  await new Promise<void>((res) => setTimeout(res, 0));
  await disconnectSerial();
});

describe('_serialDispatch wire-byte semantics', () => {
  // ── arm/disarm sanity ────────────────────────────────────────────────
  it('arm sends MAV_CMD_COMPONENT_ARM_DISARM (400) p1=1', () => {
    dispatch('arm');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(400);
    expect(cmd.p1).toBe(1);
  });

  it('disarm sends MAV_CMD_COMPONENT_ARM_DISARM (400) p1=0', () => {
    dispatch('disarm');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(400);
    expect(cmd.p1).toBe(0);
  });

  // ── force_disarm: 21196 magic ────────────────────────────────────────
  it('force_disarm uses AP arming-bypass magic 21196 in p2', () => {
    dispatch('force_disarm');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(400);
    expect(cmd.p1).toBe(0);
    expect(cmd.p2).toBe(21196);
  });

  // ── rtl: Plane=11, Copter=6 ──────────────────────────────────────────
  it('rtl on Plane sends SET_MODE custom_mode=11 (RTL, NOT 21=QRTL)', () => {
    _isPlaneFlag = true;
    dispatch('rtl');
    expect(decodeSetMode(writes[0]).customMode).toBe(11);
  });

  it('rtl on Copter sends SET_MODE custom_mode=6', () => {
    _isPlaneFlag = false;
    dispatch('rtl');
    expect(decodeSetMode(writes[0]).customMode).toBe(6);
  });

  // ── takeoff: Plane needs GUIDED first ────────────────────────────────
  it('takeoff on Plane switches to GUIDED (15) before sending NAV_TAKEOFF (22)', () => {
    _isPlaneFlag = true;
    dispatch('takeoff', undefined, { alt: 50 });
    expect(writes.length).toBe(2);
    expect(decodeSetMode(writes[0]).customMode).toBe(15);  // GUIDED
    const cmd = decodeCommandLong(writes[1]);
    expect(cmd.command).toBe(22);
    expect(cmd.p7).toBe(50);
  });

  it('takeoff on Copter sends NAV_TAKEOFF directly (no mode switch)', () => {
    _isPlaneFlag = false;
    dispatch('takeoff', undefined, { alt: 30 });
    expect(writes.length).toBe(1);
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(22);
    expect(cmd.p7).toBe(30);
  });

  // ── mission_start: AUTO mode + delayed MISSION_START (300) ───────────
  it('mission_start sets AUTO mode then sends MAV_CMD_MISSION_START (300) after delay', async () => {
    vi.useFakeTimers();
    _isPlaneFlag = false;
    dispatch('mission_start');
    expect(writes.length).toBe(1);
    expect(decodeSetMode(writes[0]).customMode).toBe(3);  // Copter AUTO
    // Cmd 300 fires after 1s — advance timers, then await microtasks.
    await vi.advanceTimersByTimeAsync(1000);
    expect(writes.length).toBe(2);
    expect(decodeCommandLong(writes[1]).command).toBe(300);
    vi.useRealTimers();
  });

  // ── mission_set_current: HOME/TAKEOFF offset ─────────────────────────
  it('mission_set_current adds +2 HOME/TAKEOFF offset to wp_index', () => {
    dispatch('mission_set_current', undefined, { wp_index: 0 });
    expect(decodeMissionSetCurrent(writes[0]).seq).toBe(2);
  });

  it('mission_set_current wp_index=5 sends seq=7', () => {
    dispatch('mission_set_current', undefined, { wp_index: 5 });
    expect(decodeMissionSetCurrent(writes[0]).seq).toBe(7);
  });

  // ── guided_goto: mode switch + SET_POSITION_TARGET_GLOBAL_INT ────────
  it('guided_goto on Plane: GUIDED (15) then msg 86 with int32 lat/lon', () => {
    _isPlaneFlag = true;
    dispatch('guided_goto', undefined, { lat: 40.7128, lon: -74.006, alt: 100 });
    expect(writes.length).toBe(2);
    expect(decodeSetMode(writes[0]).customMode).toBe(15);
    const tgt = decodePositionTargetGlobal(writes[1]);
    expect(tgt.lat).toBeCloseTo(40.7128, 6);
    expect(tgt.lon).toBeCloseTo(-74.006, 6);
    expect(tgt.alt).toBe(100);
    expect(tgt.typeMask).toBe(0x0FF8);
    expect(tgt.frame).toBe(6);  // MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
  });

  it('guided_goto on Copter: GUIDED (4) then msg 86', () => {
    _isPlaneFlag = false;
    dispatch('guided_goto', undefined, { lat: 40, lon: -74, alt: 50 });
    expect(decodeSetMode(writes[0]).customMode).toBe(4);
    expect(decodePositionTargetGlobal(writes[1]).alt).toBe(50);
  });

  // ── do_set_roi: cmd 201 (NOT 197), p1=3 ──────────────────────────────
  it('do_set_roi sends MAV_CMD_DO_SET_ROI (201) with p1=3, NOT 197 (DO_SET_ROI_NONE)', () => {
    dispatch('do_set_roi', undefined, { lat: 40.7, lon: -74, alt: 50 });
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(201);
    expect(cmd.command).not.toBe(197);  // explicit anti-regression
    expect(cmd.p1).toBe(3);
    expect(cmd.p5).toBeCloseTo(40.7, 3);
    expect(cmd.p6).toBeCloseTo(-74, 3);
    expect(cmd.p7).toBe(50);
  });

  // ── camera_trigger: p5=1 (NOT all zeros) ─────────────────────────────
  it('camera_trigger sends DO_DIGICAM_CONTROL (203) with p5=1', () => {
    dispatch('camera_trigger');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(203);
    expect(cmd.p5).toBe(1);  // shoot command — all zeros is a no-op
  });

  // ── param_save split: save_to_flash hits FC NVRAM, save falls through to WS
  it('param_save_to_flash sends PREFLIGHT_STORAGE (245) p1=1', () => {
    dispatch('param_save_to_flash');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(245);
    expect(cmd.p1).toBe(1);
  });

  it('param_save falls through to WS (no serial write) — writes JSON backup, not FC NVRAM', async () => {
    dispatch('param_save');
    // Give the dynamic import time to resolve.
    await new Promise<void>((res) => setTimeout(res, 0));
    expect(filterAppFrames(writes).length).toBe(0);
    expect(wsSendCommand).toHaveBeenCalledWith('param_save', undefined, undefined);
  });

  // ── drop / drop_stop ─────────────────────────────────────────────────
  it('drop sends DO_PARACHUTE (181) p2=0 (RELEASE)', () => {
    dispatch('drop');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(181);
    expect(cmd.p2).toBe(0);
  });

  it('drop_stop sends DO_PARACHUTE (181) p2=1 (DISABLE)', () => {
    dispatch('drop_stop');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(181);
    expect(cmd.p2).toBe(1);
  });

  // ── reboot variants ──────────────────────────────────────────────────
  it('reboot sends PREFLIGHT_REBOOT_SHUTDOWN (246) p1=1 (autopilot reboot)', () => {
    dispatch('reboot');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(246);
    expect(cmd.p1).toBe(1);
  });

  it('reboot_bootloader sends PREFLIGHT_REBOOT_SHUTDOWN (246) p1=3', () => {
    dispatch('reboot_bootloader');
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(246);
    expect(cmd.p1).toBe(3);
  });

  // ── motor_test bounds (defensive — UI clamps, but dispatch must too) ──
  it('motor_test rejects out-of-bounds motor index (>7)', () => {
    dispatch('motor_test', undefined, { motor: 99, throttle: 5, duration: 2 });
    expect(filterAppFrames(writes).length).toBe(0);
  });

  it('motor_test rejects out-of-bounds throttle (>100)', () => {
    dispatch('motor_test', undefined, { motor: 0, throttle: 200, duration: 2 });
    expect(filterAppFrames(writes).length).toBe(0);
  });

  it('motor_test rejects out-of-bounds duration (>30)', () => {
    dispatch('motor_test', undefined, { motor: 0, throttle: 5, duration: 60 });
    expect(filterAppFrames(writes).length).toBe(0);
  });

  it('motor_test with valid input sends DO_MOTOR_TEST (209) with 1-based motor index', () => {
    dispatch('motor_test', undefined, { motor: 0, throttle: 10, duration: 2 });
    const cmd = decodeCommandLong(writes[0]);
    expect(cmd.command).toBe(209);
    expect(cmd.p1).toBe(1);  // motor 0 (UI) → 1 (AP wire)
    expect(cmd.p3).toBe(10);  // throttle %
    expect(cmd.p4).toBe(2);   // duration s
    expect(cmd.p5).toBe(1);   // motor count
  });
});
