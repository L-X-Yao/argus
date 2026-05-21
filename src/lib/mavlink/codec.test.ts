import { describe, it, expect } from 'vitest';
import { parseFrames, encodeFrame } from './codec';
import { crc16, CRC_EXTRA } from './crc';

describe('MAVLink CRC', () => {
  it('computes CRC-16/MCRF4XX correctly', () => {
    const data = new Uint8Array([0x01, 0x02, 0x03]);
    const result = crc16(data);
    expect(typeof result).toBe('number');
    expect(result).toBeGreaterThan(0);
    expect(result).toBeLessThanOrEqual(0xFFFF);
  });

  it('CRC_EXTRA has entry for HEARTBEAT (0)', () => {
    expect(CRC_EXTRA[0]).toBe(50);
  });

  it('CRC_EXTRA has entry for COMMAND_LONG (76)', () => {
    expect(CRC_EXTRA[76]).toBe(143);
  });
});

describe('MAVLink v2 codec', () => {
  it('encodeFrame produces valid frame header', () => {
    const payload = new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]);
    const frame = encodeFrame(0, payload, 255, 190, 42);

    expect(frame[0]).toBe(0xFD); // STX
    expect(frame[1]).toBe(9);     // payload length
    expect(frame[4]).toBe(42);    // seq
    expect(frame[5]).toBe(255);   // sysid
    expect(frame[6]).toBe(190);   // compid
    expect(frame[7]).toBe(0);     // msgid low
  });

  it('roundtrip encode → parse produces matching frame', () => {
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

  it('parse rejects corrupted CRC', () => {
    const payload = new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]);
    const encoded = encodeFrame(0, payload, 255, 190, 0);
    encoded[encoded.length - 1] ^= 0xFF; // corrupt CRC
    const { frames } = parseFrames(encoded);
    expect(frames.length).toBe(0);
  });

  it('parse handles multiple frames in buffer', () => {
    const p1 = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 0);
    const p2 = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 1);
    const combined = new Uint8Array(p1.length + p2.length);
    combined.set(p1);
    combined.set(p2, p1.length);
    const { frames } = parseFrames(combined);
    expect(frames.length).toBe(2);
    expect(frames[0].seq).toBe(0);
    expect(frames[1].seq).toBe(1);
  });

  it('parse handles incomplete frame (returns remaining)', () => {
    const full = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 0);
    const partial = full.slice(0, 8); // cut short
    const { frames, remaining } = parseFrames(partial);
    expect(frames.length).toBe(0);
    expect(remaining.length).toBe(8);
  });

  it('parse skips garbage before valid frame', () => {
    const valid = encodeFrame(0, new Uint8Array([0, 0, 0, 0, 6, 8, 0, 0, 3]), 1, 1, 5);
    const withGarbage = new Uint8Array(5 + valid.length);
    withGarbage.set([0x00, 0x11, 0x22, 0x33, 0x44]); // garbage
    withGarbage.set(valid, 5);
    const { frames } = parseFrames(withGarbage);
    expect(frames.length).toBe(1);
    expect(frames[0].seq).toBe(5);
  });
});
