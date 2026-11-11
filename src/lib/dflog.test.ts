import { describe, it, expect } from 'vitest';
import { parseDFLog, getTimeSeries, firstDataColumn, computeFFT, findPeaks, sampleInterval } from './dflog';
import type { DFLog } from './dflog';

/* ── Helpers ── */

/** Build a minimal binary log with one FMT message and N data messages. */
function buildBinaryLog(
  msgType: number,
  name: string,
  format: string,
  columns: string[],
  rows: ArrayBuffer[],
): ArrayBuffer {
  // FMT message: type 128, total length 89 (3 header + 86 body)
  const fmtBody = new Uint8Array(86);
  fmtBody[0] = msgType;
  // length = 3 header bytes + sum of field sizes
  const FMT_SIZES: Record<string, number> = {
    b: 1,
    B: 1,
    h: 2,
    H: 2,
    i: 4,
    I: 4,
    f: 4,
    d: 8,
    n: 4,
    N: 16,
    Z: 64,
    c: 2,
    C: 2,
    e: 4,
    E: 4,
    L: 4,
    M: 1,
    q: 8,
    Q: 8,
  };
  const bodyLen = format.split('').reduce((s, c) => s + (FMT_SIZES[c] || 1), 0);
  fmtBody[1] = 3 + bodyLen;
  for (let i = 0; i < 4 && i < name.length; i++) fmtBody[2 + i] = name.charCodeAt(i);
  for (let i = 0; i < 16 && i < format.length; i++) fmtBody[6 + i] = format.charCodeAt(i);
  const colStr = columns.join(',');
  for (let i = 0; i < 64 && i < colStr.length; i++) fmtBody[22 + i] = colStr.charCodeAt(i);

  // Total buffer: 3+86 for FMT + (3+bodyLen)*rows.length
  const totalLen = 89 + rows.length * (3 + bodyLen);
  const buf = new ArrayBuffer(totalLen);
  const u8 = new Uint8Array(buf);
  let pos = 0;

  // Write FMT header
  u8[pos++] = 0xa3;
  u8[pos++] = 0x95;
  u8[pos++] = 128;
  u8.set(fmtBody, pos);
  pos += 86;

  // Write data messages
  for (const row of rows) {
    u8[pos++] = 0xa3;
    u8[pos++] = 0x95;
    u8[pos++] = msgType;
    u8.set(new Uint8Array(row), pos);
    pos += bodyLen;
  }
  return buf;
}

/** Create a data row with a single float field. */
function floatRow(val: number): ArrayBuffer {
  const buf = new ArrayBuffer(4);
  new DataView(buf).setFloat32(0, val, true);
  return buf;
}

/** Create a data row with a Q (uint64, TimeUS) + float field. */
function timeFloatRow(timeUS: number, val: number): ArrayBuffer {
  const buf = new ArrayBuffer(12);
  const dv = new DataView(buf);
  // Q: lo 4 bytes, hi 4 bytes (little endian)
  dv.setUint32(0, timeUS & 0xffffffff, true);
  dv.setUint32(4, Math.floor(timeUS / 0x100000000), true);
  dv.setFloat32(8, val, true);
  return buf;
}

/* ── Format parsing ── */
describe('parseDFLog — format parsing', () => {
  it('recognises HEAD1 and HEAD2 bytes', () => {
    // Empty log with just garbage — no 0xa3 0x95 sequences
    const garbage = new Uint8Array([0x00, 0x01, 0x02, 0x03]).buffer;
    const log = parseDFLog(garbage);
    expect(log.messages).toEqual([]);
    expect(log.types).toEqual([]);
  });

  it('parses a FMT message and registers the format', () => {
    const buf = buildBinaryLog(10, 'TEST', 'f', ['Val'], []);
    const log = parseDFLog(buf);
    expect(log.formats.has('TEST')).toBe(true);
    const fmt = log.formats.get('TEST')!;
    expect(fmt.name).toBe('TEST');
    expect(fmt.format).toBe('f');
    expect(fmt.columns).toEqual(['Val']);
  });

  it('parses data messages using the registered format', () => {
    const buf = buildBinaryLog(10, 'VALU', 'f', ['V'], [floatRow(3.14)]);
    const log = parseDFLog(buf);
    expect(log.messages.length).toBe(1);
    expect(log.messages[0].type).toBe('VALU');
    expect(log.messages[0].fields['V']).toBeCloseTo(3.14, 2);
  });

  it('reports correct duration from TimeUS fields', () => {
    const rows = [timeFloatRow(1_000_000, 0), timeFloatRow(6_000_000, 0)];
    const buf = buildBinaryLog(10, 'TST', 'Qf', ['TimeUS', 'V'], rows);
    const log = parseDFLog(buf);
    expect(log.duration).toBeCloseTo(5.0, 1);
  });

  it('lists unique message types sorted', () => {
    // Build a log with two different message types
    const buf1 = buildBinaryLog(10, 'BBB', 'f', ['V'], [floatRow(1)]);
    const buf2 = buildBinaryLog(11, 'AAA', 'f', ['V'], [floatRow(2)]);
    // Concatenate the two buffers
    const combined = new Uint8Array(buf1.byteLength + buf2.byteLength);
    combined.set(new Uint8Array(buf1), 0);
    combined.set(new Uint8Array(buf2), buf1.byteLength);
    const log = parseDFLog(combined.buffer);
    expect(log.types).toEqual(['AAA', 'BBB']);
  });
});

/* ── Field reading ── */
describe('parseDFLog — field types', () => {
  it('reads int8 (b)', () => {
    const row = new ArrayBuffer(1);
    new DataView(row).setInt8(0, -42);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'b', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBe(-42);
  });

  it('reads uint8 (B)', () => {
    const row = new ArrayBuffer(1);
    new DataView(row).setUint8(0, 200);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'B', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBe(200);
  });

  it('reads int16 (h)', () => {
    const row = new ArrayBuffer(2);
    new DataView(row).setInt16(0, -1234, true);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'h', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBe(-1234);
  });

  it('reads uint16 (H)', () => {
    const row = new ArrayBuffer(2);
    new DataView(row).setUint16(0, 50000, true);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'H', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBe(50000);
  });

  it('reads int32 (i)', () => {
    const row = new ArrayBuffer(4);
    new DataView(row).setInt32(0, -100000, true);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'i', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBe(-100000);
  });

  it('reads uint32 (I)', () => {
    const row = new ArrayBuffer(4);
    new DataView(row).setUint32(0, 3000000000, true);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'I', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBe(3000000000);
  });

  it('reads float32 (f)', () => {
    const log = parseDFLog(buildBinaryLog(10, 'T', 'f', ['V'], [floatRow(1.5)]));
    expect(log.messages[0].fields['V']).toBeCloseTo(1.5, 5);
  });

  it('reads float64 (d)', () => {
    const row = new ArrayBuffer(8);
    new DataView(row).setFloat64(0, 123456.789012, true);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'd', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBeCloseTo(123456.789012, 4);
  });

  it('reads centi-int16 (c) — value / 100', () => {
    const row = new ArrayBuffer(2);
    new DataView(row).setInt16(0, 3456, true);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'c', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBeCloseTo(34.56, 4);
  });

  it('reads lat/lon (L) — value / 1e7', () => {
    const row = new ArrayBuffer(4);
    new DataView(row).setInt32(0, 399042000, true); // 39.9042 * 1e7
    const log = parseDFLog(buildBinaryLog(10, 'T', 'L', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBeCloseTo(39.9042, 3);
  });

  it('reads mode byte (M) same as uint8', () => {
    const row = new ArrayBuffer(1);
    new DataView(row).setUint8(0, 15);
    const log = parseDFLog(buildBinaryLog(10, 'T', 'M', ['V'], [row]));
    expect(log.messages[0].fields['V']).toBe(15);
  });
});

/* ── getTimeSeries ── */
describe('getTimeSeries', () => {
  function makeSampleLog(): DFLog {
    const rows = [timeFloatRow(1_000_000, 10.0), timeFloatRow(2_000_000, 20.0), timeFloatRow(3_000_000, 30.0)];
    return parseDFLog(buildBinaryLog(10, 'SENS', 'Qf', ['TimeUS', 'Val'], rows));
  }

  it('extracts matching field as arrays', () => {
    const log = makeSampleLog();
    const { t, v } = getTimeSeries(log, 'SENS', 'Val');
    expect(t.length).toBe(3);
    expect(v.length).toBe(3);
    expect(v[0]).toBeCloseTo(10.0, 2);
    expect(v[2]).toBeCloseTo(30.0, 2);
  });

  it('returns time relative to first message', () => {
    const log = makeSampleLog();
    const { t } = getTimeSeries(log, 'SENS', 'Val');
    expect(t[0]).toBeCloseTo(0, 1);
    expect(t[1]).toBeCloseTo(1, 1);
    expect(t[2]).toBeCloseTo(2, 1);
  });

  it('returns empty for non-existent message type', () => {
    const log = makeSampleLog();
    const { t, v } = getTimeSeries(log, 'NOPE', 'Val');
    expect(t).toEqual([]);
    expect(v).toEqual([]);
  });

  it('returns empty for non-existent field', () => {
    const log = makeSampleLog();
    const { t, v } = getTimeSeries(log, 'SENS', 'Nope');
    expect(t).toEqual([]);
    expect(v).toEqual([]);
  });
});

/* ── computeFFT ── */
describe('a type with instances', () => {
  // IMU: TimeUS, I, GyrX, with FMTU marking I as the instance the way ArduPilot does.
  const imuRow = (timeUS: number, instance: number, gyr: number) => {
    const buf = new ArrayBuffer(13);
    const dv = new DataView(buf);
    dv.setUint32(0, timeUS, true);
    dv.setUint8(8, instance);
    dv.setFloat32(9, gyr, true);
    return buf;
  };
  const fmtuRow = (type: number, units: string) => {
    const buf = new ArrayBuffer(41);
    const u8 = new Uint8Array(buf);
    u8[8] = type;
    for (let i = 0; i < units.length; i++) u8[9 + i] = units.charCodeAt(i);
    return buf;
  };
  const join = (...parts: ArrayBuffer[]) => {
    const out = new Uint8Array(parts.reduce((n, p) => n + p.byteLength, 0));
    let at = 0;
    for (const p of parts) {
      out.set(new Uint8Array(p), at);
      at += p.byteLength;
    }
    return out.buffer;
  };
  const imuHeader = new Uint8Array([0xa3, 0x95, 41]).buffer;
  const makeLog = () =>
    parseDFLog(
      join(
        buildBinaryLog(41, 'IMU', 'QBf', ['TimeUS', 'I', 'GyrX'], []),
        buildBinaryLog(40, 'FMTU', 'QBNN', ['TimeUS', 'FmtType', 'UnitIds', 'MultIds'], [fmtuRow(41, 's#E')]),
        ...[imuRow(1000, 0, 1), imuRow(1000, 1, 9), imuRow(2000, 0, 2), imuRow(2000, 1, 9)].flatMap((row) => [
          imuHeader,
          row,
        ]),
      ),
    );

  it('names the column FMTU gives the unit # as the instance', () => {
    expect(makeLog().formats.get('IMU')?.instance).toBe('I');
  });

  it('plots the first column that holds data', () => {
    expect(firstDataColumn(makeLog().formats.get('IMU')!)).toBe('GyrX');
  });

  it('reads one sensor, not all of them in turn', () => {
    expect(getTimeSeries(makeLog(), 'IMU', 'GyrX').v).toEqual([1, 2]);
  });
});

describe('sampleInterval', () => {
  it('takes a pause in the log for a pause, not for a slower rate', () => {
    const times = Array.from({ length: 4000 }, (_, i) => i / 400);
    const resumed = times.map((t, i) => (i < 2000 ? t : t + 7.4)); // logging stops at a disarm
    expect(sampleInterval(resumed)).toBeCloseTo(1 / 400, 9);
  });

  it('has nothing to say about a single sample', () => {
    expect(sampleInterval([1])).toBe(0);
  });

  it('looks past samples logged at one instant', () => {
    expect(sampleInterval([0, 0, 0, 0, 0, 0.01, 0.01, 0.01, 0.01, 0.02])).toBeCloseTo(0.01, 9);
  });
});

describe('findPeaks', () => {
  const freq = [0, 0.1, 0.2, 5, 6, 7, 34, 35, 36, 70, 71, 72];
  const mag = [0, 9, 0, 0, 8, 0, 0, 3, 0, 0, 2, 0];

  it('leaves out what is under the lowest notch the FC takes', () => {
    expect(findPeaks(freq, mag, 3).map((p) => p.freq)).toEqual([35, 71]);
  });

  it('gives the strongest first, and no more than asked for', () => {
    expect(findPeaks(freq, mag, 1).map((p) => p.freq)).toEqual([35]);
  });
});

describe('computeFFT', () => {
  it('returns empty for very short input', () => {
    const result = computeFFT([1, 2, 3], 100);
    expect(result.freq).toEqual([]);
    expect(result.mag).toEqual([]);
  });

  it('detects a pure sine wave at the correct frequency bin', () => {
    const N = 256;
    const fs = 400;
    const f0 = 50;
    const signal = Array.from({ length: N }, (_, i) => Math.sin((2 * Math.PI * f0 * i) / fs));
    const { freq, mag } = computeFFT(signal, fs);

    expect(freq.length).toBeGreaterThan(0);
    const peakIdx = mag.indexOf(Math.max(...mag));
    // 50 Hz at 400 Hz sample rate, N=256 → bin 32 → freq[31] = 50 Hz
    expect(freq[peakIdx]).toBeCloseTo(f0, 0);
    expect(Math.max(...mag)).toBeGreaterThan(0.3);
    const weakBins = mag.filter((m) => m < Math.max(...mag) * 0.1);
    expect(weakBins.length).toBeGreaterThan(mag.length * 0.8);
  });

  it('DC input produces negligible magnitude', () => {
    const N = 64;
    const signal = new Array(N).fill(5.0);
    const { mag } = computeFFT(signal, 100);
    // DC bin is excluded (starts at bin 1), so all magnitudes should be ~0
    for (const m of mag) {
      expect(m).toBeLessThan(0.01);
    }
  });

  it('output length is half of the power-of-2 input minus 1', () => {
    const N = 128;
    const signal = Array.from({ length: N }, () => Math.random());
    const { freq, mag } = computeFFT(signal, 100);
    expect(freq.length).toBe(N / 2 - 1);
    expect(mag.length).toBe(N / 2 - 1);
  });

  it('truncates non-power-of-2 input to the largest power of 2', () => {
    const signal = Array.from({ length: 100 }, () => Math.random());
    const { freq } = computeFFT(signal, 100);
    // 100 → truncated to 64 → output length = 64/2 - 1 = 31
    expect(freq.length).toBe(31);
  });
});

/* ── A log that is damaged ── */

describe('parseDFLog on a damaged log', () => {
  /** An FMT record that declares message `type` with the given total length. */
  function fmt(type: number, length: number, name: string, format: string, columns: string): Uint8Array {
    const rec = new Uint8Array(89);
    rec.set([0xa3, 0x95, 128, type, length]);
    for (let i = 0; i < name.length; i++) rec[5 + i] = name.charCodeAt(i);
    for (let i = 0; i < format.length; i++) rec[9 + i] = format.charCodeAt(i);
    for (let i = 0; i < columns.length; i++) rec[25 + i] = columns.charCodeAt(i);
    return rec;
  }
  const join = (...parts: Uint8Array[]) => {
    const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
    let at = 0;
    for (const p of parts) {
      out.set(p, at);
      at += p.length;
    }
    return out.buffer;
  };

  // The length counts the 3-byte header, so 0, 1 and 2 step backwards: 0 onto the same header
  // for ever, 1 and 2 into it, which reads the header as a message. Without the check the first
  // of these does not fail: it never ends, and takes the page down the same way.
  it.each([0, 1, 2])('ends on a format that declares a length of %i', (length) => {
    const log = parseDFLog(join(fmt(1, length, 'BAD', '', ''), new Uint8Array([0xa3, 0x95, 1, 0, 0])));
    expect(log.messages).toEqual([]);
  });

  it('reads a message that has a header and nothing else', () => {
    const log = parseDFLog(join(fmt(1, 3, 'EMP', '', ''), new Uint8Array([0xa3, 0x95, 1, 0xa3, 0x95, 1, 0, 0, 0])));
    expect(log.messages.map((m) => m.type)).toEqual(['EMP', 'EMP']);
  });

  it('stops at a format that lists more fields than the file has left', () => {
    // Four bytes declared, eight read: the second field runs past the end of the file.
    const log = parseDFLog(join(fmt(1, 7, 'LIE', 'II', 'A,B'), new Uint8Array([0xa3, 0x95, 1, 1, 0, 0, 0])));
    expect(log.messages).toEqual([]);
  });

  it('keeps what came before the damage', () => {
    const good = new Uint8Array([0xa3, 0x95, 2, 7, 0, 0, 0]);
    const log = parseDFLog(
      join(fmt(2, 7, 'OK', 'I', 'A'), good, fmt(1, 7, 'LIE', 'II', 'A,B'), new Uint8Array([0xa3, 0x95, 1, 1, 0, 0, 0])),
    );
    expect(log.messages).toEqual([{ type: 'OK', timestamp: 0, fields: { A: 7 } }]);
  });
});
