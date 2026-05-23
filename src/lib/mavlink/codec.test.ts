import { describe, it, expect } from 'vitest';
import { parseFrames, encodeFrame } from './codec';
import type { MavFrame } from './codec';
import { crc16, crcAccumulate, CRC_EXTRA } from './crc';
import {
  decodeHeartbeat,
  decodeAttitude,
  decodeGlobalPositionInt,
  decodeVfrHud,
  decodeCommandAck,
  decodeStatusText,
  decodeParamValue,
  decodeSysStatus,
  decodeHomePosition,
  decodeMissionCurrent,
  decodeMissionCount,
  decodeMissionAck,
  decodeWind,
  decodeVibration,
  encodeHeartbeat,
  encodeCommandLong,
  encodeSetMode,
  encodeParamRequestList,
  encodeParamSet,
  encodeRequestDataStream,
  dispatchFrame,
  decodeServoOutput,
} from './messages';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a MavFrame from a raw Uint8Array payload (not a full wire frame). */
function makeMavFrame(msgId: number, payload: Uint8Array, sysId = 1, compId = 1, seq = 0): MavFrame {
  return {
    msgId,
    sysId,
    compId,
    seq,
    payload: new DataView(payload.buffer, payload.byteOffset, payload.byteLength),
    payloadLen: payload.length,
  };
}

// ---------------------------------------------------------------------------
// CRC
// ---------------------------------------------------------------------------

describe('CRC-16/MCRF4XX', () => {
  it('returns 0xFFFF for empty input', () => {
    expect(crc16(new Uint8Array([]))).toBe(0xFFFF);
  });

  it('computes correct value for single byte 0x00', () => {
    const result = crc16(new Uint8Array([0x00]));
    // Verified empirically against the implementation
    expect(result).toBe(0x0F87);
  });

  it('produces a 16-bit value for multi-byte input', () => {
    const data = new Uint8Array([0x01, 0x02, 0x03]);
    const result = crc16(data);
    expect(result).toBeGreaterThan(0);
    expect(result).toBeLessThanOrEqual(0xFFFF);
  });

  it('different inputs produce different CRCs', () => {
    const a = crc16(new Uint8Array([0x01, 0x02, 0x03]));
    const b = crc16(new Uint8Array([0x01, 0x02, 0x04]));
    expect(a).not.toBe(b);
  });

  it('supports custom initial value', () => {
    const a = crc16(new Uint8Array([0x42]), 0xFFFF);
    const b = crc16(new Uint8Array([0x42]), 0x0000);
    expect(a).not.toBe(b);
  });

  it('crcAccumulate matches byte-at-a-time computation', () => {
    const data = new Uint8Array([0xAA, 0xBB, 0xCC, 0xDD]);
    const wholeCrc = crc16(data);
    let runningCrc = 0xFFFF;
    for (const b of data) {
      runningCrc = crcAccumulate(b, runningCrc);
    }
    expect(runningCrc).toBe(wholeCrc);
  });
});

describe('CRC_EXTRA table', () => {
  it('has entry for HEARTBEAT (0) = 50', () => {
    expect(CRC_EXTRA[0]).toBe(50);
  });

  it('has entry for COMMAND_LONG (76) = 152', () => {
    // 152 is COMMAND_LONG. 143 is COMMAND_ACK (77).
    expect(CRC_EXTRA[76]).toBe(152);
  });

  it('has entry for STATUSTEXT (253) = 83', () => {
    expect(CRC_EXTRA[253]).toBe(83);
  });

  it('returns undefined for unknown message IDs', () => {
    expect(CRC_EXTRA[9999]).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Frame encoding
// ---------------------------------------------------------------------------

describe('encodeFrame', () => {
  it('produces valid MAVLink v2 header', () => {
    const payload = new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]);
    const frame = encodeFrame(0, payload, 255, 190, 42);

    expect(frame[0]).toBe(0xFD);   // STX
    expect(frame[1]).toBe(9);      // payload length
    expect(frame[2]).toBe(0);      // incompat_flags
    expect(frame[3]).toBe(0);      // compat_flags
    expect(frame[4]).toBe(42);     // seq
    expect(frame[5]).toBe(255);    // sysid
    expect(frame[6]).toBe(190);    // compid
    expect(frame[7]).toBe(0);      // msgid byte 0
    expect(frame[8]).toBe(0);      // msgid byte 1
    expect(frame[9]).toBe(0);      // msgid byte 2
  });

  it('total frame length = 10 + payload + 2', () => {
    const payload = new Uint8Array(20);
    const frame = encodeFrame(0, payload, 1, 1, 0);
    expect(frame.length).toBe(10 + 20 + 2);
  });

  it('encodes 24-bit message ID in little-endian', () => {
    const payload = new Uint8Array(2);
    // msgId = 0x010203
    const frame = encodeFrame(0x010203, payload, 1, 1, 0);
    expect(frame[7]).toBe(0x03); // low byte
    expect(frame[8]).toBe(0x02); // mid byte
    expect(frame[9]).toBe(0x01); // high byte
  });

  it('wraps sequence number to 8 bits', () => {
    const frame = encodeFrame(0, new Uint8Array(1), 1, 1, 256);
    expect(frame[4]).toBe(0); // 256 & 0xFF = 0

    const frame2 = encodeFrame(0, new Uint8Array(1), 1, 1, 300);
    expect(frame2[4]).toBe(44); // 300 & 0xFF = 44
  });

  it('payload bytes appear at offset 10', () => {
    const payload = new Uint8Array([0xDE, 0xAD, 0xBE, 0xEF]);
    const frame = encodeFrame(0, payload, 1, 1, 0);
    expect(frame[10]).toBe(0xDE);
    expect(frame[11]).toBe(0xAD);
    expect(frame[12]).toBe(0xBE);
    expect(frame[13]).toBe(0xEF);
  });

  it('appends valid CRC that parseFrames accepts', () => {
    const payload = new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]);
    const frame = encodeFrame(0, payload, 1, 1, 0);
    const { frames } = parseFrames(frame);
    expect(frames.length).toBe(1);
  });

  it('uses CRC_EXTRA 0 for unknown message IDs', () => {
    // msgId 65535 has no CRC_EXTRA entry, so encoder defaults to 0
    const payload = new Uint8Array([0x01, 0x02]);
    const frame = encodeFrame(65535, payload, 1, 1, 0);
    // Manually verify CRC was computed with crcExtra=0
    const crcData = frame.slice(1, 10 + 2);
    const computed = crc16(new Uint8Array([...crcData, 0]));
    const stored = frame[12] | (frame[13] << 8);
    expect(computed).toBe(stored);
  });
});

// ---------------------------------------------------------------------------
// Frame parsing
// ---------------------------------------------------------------------------

describe('parseFrames', () => {
  it('roundtrip encode -> parse preserves all header fields', () => {
    const payload = new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]);
    const encoded = encodeFrame(0, payload, 255, 190, 7);
    const { frames, remaining } = parseFrames(encoded);

    expect(frames.length).toBe(1);
    expect(frames[0].msgId).toBe(0);
    expect(frames[0].sysId).toBe(255);
    expect(frames[0].compId).toBe(190);
    expect(frames[0].seq).toBe(7);
    expect(frames[0].payloadLen).toBe(9);
    expect(remaining.length).toBe(0);
  });

  it('roundtrip preserves payload bytes', () => {
    const payload = new Uint8Array([0xAA, 0xBB, 0xCC]);
    const encoded = encodeFrame(253, payload, 1, 1, 0);
    const { frames } = parseFrames(encoded);
    expect(frames.length).toBe(1);
    const p = frames[0].payload;
    expect(new Uint8Array(p.buffer, p.byteOffset, p.byteLength)).toEqual(payload);
  });

  it('rejects frame with corrupted CRC (last byte flipped)', () => {
    const payload = new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]);
    const encoded = encodeFrame(0, payload, 255, 190, 0);
    encoded[encoded.length - 1] ^= 0xFF;
    const { frames } = parseFrames(encoded);
    expect(frames.length).toBe(0);
  });

  it('rejects frame with corrupted CRC (first CRC byte flipped)', () => {
    const payload = new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]);
    const encoded = encodeFrame(0, payload, 1, 1, 0);
    encoded[encoded.length - 2] ^= 0x01;
    const { frames } = parseFrames(encoded);
    expect(frames.length).toBe(0);
  });

  it('handles multiple concatenated frames', () => {
    const p1 = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 0);
    const p2 = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 1);
    const p3 = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 2, 2, 2);
    const combined = new Uint8Array(p1.length + p2.length + p3.length);
    combined.set(p1);
    combined.set(p2, p1.length);
    combined.set(p3, p1.length + p2.length);
    const { frames } = parseFrames(combined);
    expect(frames.length).toBe(3);
    expect(frames[0].seq).toBe(0);
    expect(frames[1].seq).toBe(1);
    expect(frames[2].seq).toBe(2);
    expect(frames[2].sysId).toBe(2);
  });

  it('returns truncated frame as remaining bytes', () => {
    const full = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 0);
    const partial = full.slice(0, 8);
    const { frames, remaining } = parseFrames(partial);
    expect(frames.length).toBe(0);
    expect(remaining.length).toBe(8);
  });

  it('returns remaining when payload is incomplete', () => {
    const full = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 0);
    // Keep header + 4 payload bytes but not all 9 + CRC
    const partial = full.slice(0, 14);
    const { frames, remaining } = parseFrames(partial);
    expect(frames.length).toBe(0);
    expect(remaining.length).toBe(partial.length);
  });

  it('skips leading garbage before a valid frame', () => {
    const valid = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 5);
    const withGarbage = new Uint8Array(5 + valid.length);
    withGarbage.set([0x00, 0x11, 0x22, 0x33, 0x44]);
    withGarbage.set(valid, 5);
    const { frames } = parseFrames(withGarbage);
    expect(frames.length).toBe(1);
    expect(frames[0].seq).toBe(5);
  });

  it('skips a CRC-invalid frame and finds the next valid frame', () => {
    // Build two heartbeat frames; corrupt the CRC of the first
    const valid1 = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 10);
    const valid2 = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 99);
    // Corrupt CRC of first frame
    valid1[valid1.length - 1] ^= 0xFF;
    const buf = new Uint8Array(valid1.length + valid2.length);
    buf.set(valid1);
    buf.set(valid2, valid1.length);
    const { frames } = parseFrames(buf);
    // The corrupted first frame is skipped; the second is parsed
    expect(frames.length).toBe(1);
    expect(frames[0].seq).toBe(99);
  });

  it('returns empty arrays for a buffer with no STX byte', () => {
    const buf = new Uint8Array([0x00, 0x01, 0x02, 0x03]);
    const { frames, remaining } = parseFrames(buf);
    expect(frames.length).toBe(0);
    expect(remaining.length).toBe(0);
  });

  it('passes through unknown msgId frames when no CRC_EXTRA entry exists', () => {
    // Since CRC_EXTRA lookup returns undefined, the parser skips CRC validation
    const payload = new Uint8Array([0x42]);
    const encoded = encodeFrame(9999, payload, 1, 1, 0);
    const { frames } = parseFrames(encoded);
    expect(frames.length).toBe(1);
    expect(frames[0].msgId).toBe(9999);
  });

  it('extracts valid frame even with trailing incomplete frame', () => {
    const full = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 10);
    const trailer = new Uint8Array([0xFD, 0x05, 0x00]); // incomplete second frame
    const combined = new Uint8Array(full.length + trailer.length);
    combined.set(full);
    combined.set(trailer, full.length);
    const { frames, remaining } = parseFrames(combined);
    expect(frames.length).toBe(1);
    expect(frames[0].seq).toBe(10);
    expect(remaining.length).toBe(trailer.length);
  });
});

// ---------------------------------------------------------------------------
// Message decoders
// ---------------------------------------------------------------------------

describe('message decoders', () => {
  it('decodeHeartbeat parses all fields', () => {
    const buf = new Uint8Array(9);
    const dv = new DataView(buf.buffer);
    dv.setUint32(0, 12345, true); // customMode
    dv.setUint8(4, 2);           // type (quadrotor)
    dv.setUint8(5, 3);           // autopilot (ArduPilot)
    dv.setUint8(6, 0x81);        // baseMode
    dv.setUint8(7, 4);           // systemStatus
    dv.setUint8(8, 3);           // mavlinkVersion
    const hb = decodeHeartbeat(new DataView(buf.buffer));
    expect(hb.customMode).toBe(12345);
    expect(hb.type).toBe(2);
    expect(hb.autopilot).toBe(3);
    expect(hb.baseMode).toBe(0x81);
    expect(hb.systemStatus).toBe(4);
    expect(hb.mavlinkVersion).toBe(3);
  });

  it('decodeAttitude converts radians to degrees', () => {
    const buf = new Uint8Array(16);
    const dv = new DataView(buf.buffer);
    dv.setUint32(0, 0, true);                             // time_boot_ms
    dv.setFloat32(4, Math.PI / 4, true);                   // roll
    dv.setFloat32(8, -Math.PI / 6, true);                  // pitch
    dv.setFloat32(12, Math.PI, true);                      // yaw
    const att = decodeAttitude(dv);
    expect(att.roll).toBeCloseTo(45, 3);
    expect(att.pitch).toBeCloseTo(-30, 3);
    expect(att.yaw).toBeCloseTo(180, 3);
  });

  it('decodeGlobalPositionInt scales lat/lon/alt correctly', () => {
    const buf = new Uint8Array(28);
    const dv = new DataView(buf.buffer);
    dv.setUint32(0, 0, true);               // time_boot_ms
    dv.setInt32(4, 473977420, true);         // lat (47.3977420)
    dv.setInt32(8, 85327780, true);          // lon (8.5327780)
    dv.setInt32(12, 408000, true);           // alt MSL (408.0 m)
    dv.setInt32(16, 50000, true);            // alt relative (50.0 m)
    dv.setInt16(20, 150, true);              // vx (1.50 m/s)
    dv.setInt16(22, -200, true);             // vy (-2.00 m/s)
    dv.setInt16(24, 10, true);               // vz (0.10 m/s)
    dv.setUint16(26, 18000, true);           // hdg (180.00 deg)
    const gpi = decodeGlobalPositionInt(dv);
    expect(gpi.lat).toBeCloseTo(47.397742, 5);
    expect(gpi.lon).toBeCloseTo(8.532778, 5);
    expect(gpi.altMsl).toBe(408);
    expect(gpi.altRel).toBe(50);
    expect(gpi.vx).toBeCloseTo(1.5, 2);
    expect(gpi.vy).toBeCloseTo(-2.0, 2);
    expect(gpi.vz).toBeCloseTo(0.1, 2);
    expect(gpi.hdg).toBe(180);
  });

  it('decodeVfrHud reads float and int fields', () => {
    // VFR_HUD (74) wire layout, MAVLink 2 (sorted by field size, largest first):
    //   0..3:  airspeed (float)
    //   4..7:  groundspeed (float)
    //   8..11: alt (float)
    //   12..15: climb (float)
    //   16..17: heading (int16)
    //   18..19: throttle (uint16)
    const buf = new Uint8Array(20);
    const dv = new DataView(buf.buffer);
    dv.setFloat32(0, 15.5, true);
    dv.setFloat32(4, 12.3, true);
    dv.setFloat32(8, 100.5, true);
    dv.setFloat32(12, 2.5, true);
    dv.setInt16(16, 270, true);
    dv.setUint16(18, 45, true);
    const vfr = decodeVfrHud(dv);
    expect(vfr.airspeed).toBeCloseTo(15.5, 1);
    expect(vfr.groundspeed).toBeCloseTo(12.3, 1);
    expect(vfr.alt).toBeCloseTo(100.5, 1);
    expect(vfr.climb).toBeCloseTo(2.5, 1);
    expect(vfr.heading).toBe(270);
    expect(vfr.throttle).toBe(45);
  });

  it('decodeCommandAck reads command and result', () => {
    const buf = new Uint8Array(3);
    const dv = new DataView(buf.buffer);
    dv.setUint16(0, 400, true);  // MAV_CMD_COMPONENT_ARM_DISARM
    dv.setUint8(2, 0);           // MAV_RESULT_ACCEPTED
    const ack = decodeCommandAck(dv);
    expect(ack.command).toBe(400);
    expect(ack.result).toBe(0);
  });

  it('decodeStatusText reads severity and null-terminated text', () => {
    const text = 'Armed';
    const enc = new TextEncoder();
    const textBytes = enc.encode(text);
    const buf = new Uint8Array(1 + 50); // severity + up to 50 chars
    buf[0] = 6; // MAV_SEVERITY_INFO
    buf.set(textBytes, 1);
    // Remaining bytes are 0 (null terminated)
    const st = decodeStatusText(new DataView(buf.buffer));
    expect(st.severity).toBe(6);
    expect(st.text).toBe('Armed');
  });

  it('decodeParamValue reads param ID string and numeric fields', () => {
    // PARAM_VALUE (22) wire layout, MAVLink 2 (sorted by field size):
    //   0..3:   param_value (float)
    //   4..5:   param_count (uint16)
    //   6..7:   param_index (uint16)
    //   8..23:  param_id (char[16])
    //   24:     param_type (uint8)
    const buf = new Uint8Array(25);
    const dv = new DataView(buf.buffer);
    dv.setFloat32(0, 42.5, true);
    dv.setUint16(4, 1024, true);
    dv.setUint16(6, 7, true);
    const nameBytes = new TextEncoder().encode('BATT_CAPACITY');
    buf.set(nameBytes, 8);
    dv.setUint8(24, 9);
    const pv = decodeParamValue(dv);
    expect(pv.paramId).toBe('BATT_CAPACITY');
    expect(pv.paramValue).toBeCloseTo(42.5, 1);
    expect(pv.paramCount).toBe(1024);
    expect(pv.paramIndex).toBe(7);
    expect(pv.paramType).toBe(9);
  });

  it('decodeSysStatus reads voltage, current, remaining', () => {
    const buf = new Uint8Array(31);
    const dv = new DataView(buf.buffer);
    dv.setUint16(14, 12600, true); // voltage = 12.6V
    dv.setInt16(16, 1500, true);   // current = 15.00A
    dv.setInt8(30, 85);            // remaining = 85%
    const ss = decodeSysStatus(dv);
    expect(ss.voltage).toBeCloseTo(12.6, 2);
    expect(ss.current).toBeCloseTo(15.0, 2);
    expect(ss.remaining).toBe(85);
  });

  it('decodeHomePosition scales lat/lon/alt', () => {
    const buf = new Uint8Array(12);
    const dv = new DataView(buf.buffer);
    dv.setInt32(0, 340000000, true); // lat 34.0
    dv.setInt32(4, -1184000000, true); // lon -118.4
    dv.setInt32(8, 100000, true); // alt 100.0 m
    const hp = decodeHomePosition(dv);
    expect(hp.lat).toBeCloseTo(34.0, 5);
    expect(hp.lon).toBeCloseTo(-118.4, 5);
    expect(hp.alt).toBe(100);
  });

  it('decodeMissionCurrent reads sequence number', () => {
    const buf = new Uint8Array(2);
    const dv = new DataView(buf.buffer);
    dv.setUint16(0, 42, true);
    expect(decodeMissionCurrent(dv).seq).toBe(42);
  });

  it('decodeMissionCount reads count', () => {
    const buf = new Uint8Array(2);
    const dv = new DataView(buf.buffer);
    dv.setUint16(0, 10, true);
    expect(decodeMissionCount(dv).count).toBe(10);
  });

  it('decodeMissionAck reads type', () => {
    // MISSION_ACK (47) — all 1-byte fields, declared order:
    //   0: target_system, 1: target_component, 2: type
    const buf = new Uint8Array(3);
    buf[0] = 1; // target_system
    buf[1] = 1; // target_component
    buf[2] = 0; // MAV_MISSION_ACCEPTED
    expect(decodeMissionAck(new DataView(buf.buffer)).type).toBe(0);
  });

  it('decodeWind reads direction and speed', () => {
    const buf = new Uint8Array(8);
    const dv = new DataView(buf.buffer);
    dv.setFloat32(0, 270.0, true);
    dv.setFloat32(4, 5.5, true);
    const w = decodeWind(dv);
    expect(w.direction).toBeCloseTo(270, 1);
    expect(w.speed).toBeCloseTo(5.5, 1);
  });

  it('decodeVibration reads xyz and clip counts', () => {
    const buf = new Uint8Array(32);
    const dv = new DataView(buf.buffer);
    dv.setFloat32(8, 0.5, true);   // x
    dv.setFloat32(12, 1.2, true);  // y
    dv.setFloat32(16, 0.3, true);  // z
    dv.setUint32(20, 10, true);    // clip0
    dv.setUint32(24, 20, true);    // clip1
    dv.setUint32(28, 30, true);    // clip2
    const v = decodeVibration(dv);
    expect(v.x).toBeCloseTo(0.5, 2);
    expect(v.y).toBeCloseTo(1.2, 2);
    expect(v.z).toBeCloseTo(0.3, 2);
    expect(v.clip0).toBe(10);
    expect(v.clip1).toBe(20);
    expect(v.clip2).toBe(30);
  });
});

// ---------------------------------------------------------------------------
// Message encoders
// ---------------------------------------------------------------------------

describe('message encoders', () => {
  it('encodeHeartbeat produces 9-byte GCS heartbeat', () => {
    const hb = encodeHeartbeat();
    expect(hb.length).toBe(9);
    const dv = new DataView(hb.buffer);
    expect(dv.getUint8(4)).toBe(6);  // MAV_TYPE_GCS
    expect(dv.getUint8(5)).toBe(8);  // MAV_AUTOPILOT_INVALID
    expect(dv.getUint8(8)).toBe(3);  // mavlink_version
  });

  it('encodeHeartbeat accepts custom sysType and autopilot', () => {
    const hb = encodeHeartbeat(2, 3); // quadrotor, ArduPilot
    const dv = new DataView(hb.buffer);
    expect(dv.getUint8(4)).toBe(2);
    expect(dv.getUint8(5)).toBe(3);
  });

  it('encodeCommandLong produces 33-byte payload with all params', () => {
    const cmd = encodeCommandLong(1, 1, 400, 0, 1, 0, 0, 0, 0, 0, 0);
    expect(cmd.length).toBe(33);
    const dv = new DataView(cmd.buffer);
    expect(dv.getFloat32(0, true)).toBeCloseTo(1, 0); // p1
    expect(dv.getUint16(28, true)).toBe(400);           // command
    expect(dv.getUint8(30)).toBe(1);                    // targetSys
    expect(dv.getUint8(31)).toBe(1);                    // targetComp
    expect(dv.getUint8(32)).toBe(0);                    // confirmation
  });

  it('encodeSetMode produces 6-byte payload', () => {
    const sm = encodeSetMode(1, 209, 5);
    expect(sm.length).toBe(6);
    const dv = new DataView(sm.buffer);
    expect(dv.getUint32(0, true)).toBe(5);  // customMode
    expect(dv.getUint8(4)).toBe(1);          // targetSys
    expect(dv.getUint8(5)).toBe(209);        // baseMode
  });

  it('encodeParamRequestList produces 2-byte payload', () => {
    const pl = encodeParamRequestList(1, 1);
    expect(pl.length).toBe(2);
    expect(pl[0]).toBe(1);
    expect(pl[1]).toBe(1);
  });

  it('encodeParamSet encodes param name and value', () => {
    const ps = encodeParamSet(1, 1, 'THR_MIN', 130, 9);
    expect(ps.length).toBe(23);
    const dv = new DataView(ps.buffer);
    expect(dv.getFloat32(0, true)).toBeCloseTo(130, 0);
    expect(dv.getUint8(4)).toBe(1);  // targetSys
    expect(dv.getUint8(5)).toBe(1);  // targetComp
    // param name starts at offset 6
    const nameBytes = ps.slice(6, 6 + 7);
    expect(new TextDecoder().decode(nameBytes)).toBe('THR_MIN');
    expect(dv.getUint8(22)).toBe(9); // paramType
  });

  it('encodeRequestDataStream produces 6-byte payload', () => {
    const rds = encodeRequestDataStream(1, 1, 2, 10, 1);
    expect(rds.length).toBe(6);
    const dv = new DataView(rds.buffer);
    expect(dv.getUint16(0, true)).toBe(10); // rate
    expect(dv.getUint8(2)).toBe(1);          // targetSys
    expect(dv.getUint8(3)).toBe(1);          // targetComp
    expect(dv.getUint8(4)).toBe(2);          // streamId
    expect(dv.getUint8(5)).toBe(1);          // startStop
  });
});

// ---------------------------------------------------------------------------
// Full encode -> parse -> decode round-trip
// ---------------------------------------------------------------------------

describe('full round-trip (encode -> wire -> parse -> decode)', () => {
  it('heartbeat round-trip preserves all fields', () => {
    const payload = encodeHeartbeat(2, 3);
    const wire = encodeFrame(0, payload, 255, 190, 13);
    const { frames } = parseFrames(wire);
    expect(frames.length).toBe(1);
    const hb = decodeHeartbeat(frames[0].payload);
    expect(hb.type).toBe(2);
    expect(hb.autopilot).toBe(3);
    expect(hb.mavlinkVersion).toBe(3);
    expect(frames[0].sysId).toBe(255);
    expect(frames[0].compId).toBe(190);
    expect(frames[0].seq).toBe(13);
  });

  it('COMMAND_LONG round-trip preserves command and params', () => {
    const payload = encodeCommandLong(1, 1, 400, 0, 1.0, 0, 0, 0, 0, 0, 0);
    const wire = encodeFrame(76, payload, 255, 190, 0);
    const { frames } = parseFrames(wire);
    expect(frames.length).toBe(1);
    expect(frames[0].msgId).toBe(76);
    const dv = frames[0].payload;
    expect(dv.getFloat32(0, true)).toBeCloseTo(1.0, 2);
    expect(dv.getUint16(28, true)).toBe(400);
  });

  it('SET_MODE round-trip preserves customMode', () => {
    const payload = encodeSetMode(1, 209, 5);
    const wire = encodeFrame(11, payload, 255, 0, 50);
    const { frames } = parseFrames(wire);
    expect(frames.length).toBe(1);
    expect(frames[0].msgId).toBe(11);
    const dv = frames[0].payload;
    expect(dv.getUint32(0, true)).toBe(5);
    expect(dv.getUint8(5)).toBe(209);
  });
});

// ---------------------------------------------------------------------------
// dispatchFrame
// ---------------------------------------------------------------------------

describe('dispatchFrame', () => {
  it('dispatches HEARTBEAT (msgId 0) to onHeartbeat', () => {
    const payload = encodeHeartbeat(2, 3);
    const frame = makeMavFrame(0, payload);
    let called = false;
    dispatchFrame(frame, {
      onHeartbeat: (msg, f) => {
        called = true;
        expect(msg.type).toBe(2);
        expect(msg.autopilot).toBe(3);
        expect(f.sysId).toBe(1);
      },
    });
    expect(called).toBe(true);
  });

  it('dispatches unknown msgId to onUnknown', () => {
    const frame = makeMavFrame(9999, new Uint8Array(4));
    let called = false;
    dispatchFrame(frame, {
      onUnknown: (f) => {
        called = true;
        expect(f.msgId).toBe(9999);
      },
    });
    expect(called).toBe(true);
  });

  it('does nothing if no matching handler is registered', () => {
    const frame = makeMavFrame(0, encodeHeartbeat());
    // No handlers -- should not throw
    expect(() => dispatchFrame(frame, {})).not.toThrow();
  });

  // MAVLink 2 zero-trim: senders strip trailing zero bytes. Decoders that
  // read at fixed offsets must tolerate this. Regression: previously a
  // command_ack with result=0 (ACCEPTED) trimmed to 2 bytes would throw
  // RangeError trying to read offset 2.
  it('zero-pads a trimmed COMMAND_ACK payload before decoding', () => {
    // Construct a frame where the payload was trimmed to 2 bytes
    // (command=400 → 0x90 0x01, result=0 trimmed).
    const trimmed = new Uint8Array([0x90, 0x01]);
    const frame = makeMavFrame(77, trimmed);
    let observedResult: number | undefined;
    expect(() => dispatchFrame(frame, {
      onCommandAck: (msg) => {
        observedResult = msg.result;
        expect(msg.command).toBe(400);
      },
    })).not.toThrow();
    expect(observedResult).toBe(0);
  });

  it('zero-pads a trimmed MISSION_ACK to read type at offset 2', () => {
    // After MAVLink 2 trim, target_system=255, target_component=1, type=0
    // could come through as a 2-byte payload.
    const trimmed = new Uint8Array([255, 1]);
    const frame = makeMavFrame(47, trimmed);
    let observedType: number | undefined;
    expect(() => dispatchFrame(frame, {
      onMissionAck: (msg) => { observedType = msg.type; },
    })).not.toThrow();
    expect(observedType).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// decodeServoOutput regression — servos 9-16 used to be off by one byte
// because the decoder treated all 16 outputs as contiguous, ignoring the
// `port` byte at offset 20 that the wire layout places between the
// servo1-8 block and the servo9-16 extension block.
// ---------------------------------------------------------------------------

describe('decodeServoOutput regression', () => {
  it('reads servo9-16 from offsets 21..36 (after the port byte)', () => {
    // Build a 37-byte payload:
    //   0..3  time_usec=0
    //   4..19 servo1..8 = 1000..1007
    //   20    port = 99
    //   21..36 servo9..16 = 2000..2007
    const buf = new Uint8Array(37);
    const dv = new DataView(buf.buffer);
    for (let i = 0; i < 8; i++) dv.setUint16(4 + i * 2, 1000 + i, true);
    dv.setUint8(20, 99);
    for (let i = 0; i < 8; i++) dv.setUint16(21 + i * 2, 2000 + i, true);
    const result = decodeServoOutput(dv);
    expect(result.outputs.slice(0, 8)).toEqual([1000, 1001, 1002, 1003, 1004, 1005, 1006, 1007]);
    expect(result.outputs.slice(8, 16)).toEqual([2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007]);
  });
});
