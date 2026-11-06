export interface DFMessage {
  type: string;
  timestamp: number;
  fields: Record<string, number | string>;
}

export interface DFFormat {
  type: number;
  length: number;
  name: string;
  format: string;
  columns: string[];
  /** The column that says which GPS, IMU or battery a row belongs to, if there are several. */
  instance?: string;
}

export interface DFLog {
  messages: DFMessage[];
  formats: Map<string, DFFormat>;
  types: string[];
  duration: number;
}

const HEAD1 = 0xa3;
const HEAD2 = 0x95;

function readField(dv: DataView, offset: number, fmt: string): [number | string, number] {
  switch (fmt) {
    case 'b':
      return [dv.getInt8(offset), 1];
    case 'B':
    case 'M':
      return [dv.getUint8(offset), 1];
    case 'h':
      return [dv.getInt16(offset, true), 2];
    case 'H':
      return [dv.getUint16(offset, true), 2];
    case 'i':
      return [dv.getInt32(offset, true), 4];
    case 'I':
      return [dv.getUint32(offset, true), 4];
    case 'f':
      return [dv.getFloat32(offset, true), 4];
    case 'd':
      return [dv.getFloat64(offset, true), 8];
    case 'c':
      return [dv.getInt16(offset, true) / 100, 2];
    case 'C':
      return [dv.getUint16(offset, true) / 100, 2];
    case 'e':
      return [dv.getInt32(offset, true) / 100, 4];
    case 'E':
      return [dv.getUint32(offset, true) / 100, 4];
    case 'L':
      return [dv.getInt32(offset, true) / 1e7, 4];
    case 'n': {
      const bytes = new Uint8Array(dv.buffer, dv.byteOffset + offset, 4);
      return [String.fromCharCode(...bytes).replace(/\0/g, ''), 4];
    }
    case 'N': {
      const bytes = new Uint8Array(dv.buffer, dv.byteOffset + offset, 16);
      return [String.fromCharCode(...bytes).replace(/\0/g, ''), 16];
    }
    case 'Z': {
      const bytes = new Uint8Array(dv.buffer, dv.byteOffset + offset, 64);
      return [String.fromCharCode(...bytes).replace(/\0/g, ''), 64];
    }
    case 'q': {
      const lo = dv.getUint32(offset, true);
      const hi = dv.getInt32(offset + 4, true);
      return [hi * 0x100000000 + lo, 8];
    }
    case 'Q': {
      const lo = dv.getUint32(offset, true);
      const hi = dv.getUint32(offset + 4, true);
      return [hi * 0x100000000 + lo, 8];
    }
    default:
      return [0, 1];
  }
}

export function parseDFLog(buffer: ArrayBuffer): DFLog {
  const data = new Uint8Array(buffer);
  const dv = new DataView(buffer);
  const formats = new Map<number, DFFormat>();
  const formatsByName = new Map<string, DFFormat>();
  const messages: DFMessage[] = [];
  let pos = 0;
  const len = data.length;

  while (pos < len - 3) {
    if (data[pos] !== HEAD1 || data[pos + 1] !== HEAD2) {
      pos++;
      continue;
    }
    const msgType = data[pos + 2];
    pos += 3;

    if (msgType === 128) {
      if (pos + 86 > len) break;
      const type = data[pos];
      const length = data[pos + 1];
      const nameBytes = data.slice(pos + 2, pos + 6);
      const name = String.fromCharCode(...nameBytes).replace(/\0/g, '');
      const fmtBytes = data.slice(pos + 6, pos + 22);
      const format = String.fromCharCode(...fmtBytes).replace(/\0/g, '');
      const colBytes = data.slice(pos + 22, pos + 86);
      const colStr = String.fromCharCode(...colBytes).replace(/\0/g, '');
      const columns = colStr.split(',').filter((c) => c);
      const def = { type, length, name, format, columns };
      formats.set(type, def);
      formatsByName.set(name, def);
      pos += 86;
      continue;
    }

    const fmt = formats.get(msgType);
    if (!fmt) {
      pos++;
      continue;
    }

    const msgLen = fmt.length - 3;
    if (pos + msgLen > len) break;

    const fields: Record<string, number | string> = {};
    let fpos = pos;
    for (let i = 0; i < fmt.format.length && i < fmt.columns.length; i++) {
      const [val, size] = readField(dv, fpos, fmt.format[i]);
      fields[fmt.columns[i]] = val;
      fpos += size;
    }

    // FMTU gives each column of a type a unit, and '#' is the instance
    // (libraries/AP_Logger/LogStructure.h log_Units).
    if (fmt.name === 'FMTU') {
      const described = formats.get(fields['FmtType'] as number);
      const at = String(fields['UnitIds'] ?? '').indexOf('#');
      if (described && at >= 0) described.instance = described.columns[at];
    }

    let timestamp = 0;
    if ('TimeUS' in fields) timestamp = (fields['TimeUS'] as number) / 1e6;
    else if ('TimeMS' in fields) timestamp = (fields['TimeMS'] as number) / 1e3;

    messages.push({ type: fmt.name, timestamp, fields });
    pos += msgLen;
  }

  const types = [...new Set(messages.map((m) => m.type))].sort();
  const duration = messages.length > 0 ? messages[messages.length - 1].timestamp - messages[0].timestamp : 0;

  return { messages, formats: formatsByName, types, duration };
}

/** The first column worth plotting: not the time, and not which sensor it is. */
export function firstDataColumn(fmt: DFFormat): string | undefined {
  return fmt.columns.find((c) => c !== 'TimeUS' && c !== 'TimeMS' && c !== fmt.instance);
}

/**
 * One field over time. Where a type has instances, only the first: every IMU writes its
 * rows into the same stream, and read as one series they make a saw-tooth at the log rate.
 */
/**
 * Seconds between samples. The median, because logging pauses at a disarm: the span over the
 * count takes the pause for a slower rate, and reads every frequency found from it low.
 */
export function sampleInterval(times: number[]): number {
  const gaps = Float64Array.from(times.slice(1), (time, i) => time - times[i]).sort();
  return gaps.length > 0 ? gaps[gaps.length >> 1] : 0;
}

export function getTimeSeries(log: DFLog, msgType: string, field: string): { t: number[]; v: number[] } {
  const t: number[] = [];
  const v: number[] = [];
  const t0 = log.messages.length > 0 ? log.messages[0].timestamp : 0;
  const instance = log.formats.get(msgType)?.instance;
  let first: number | string | undefined;
  for (const m of log.messages) {
    if (m.type === msgType && field in m.fields) {
      if (instance !== undefined) {
        first ??= m.fields[instance];
        if (m.fields[instance] !== first) continue;
      }
      const val = m.fields[field];
      if (typeof val === 'number') {
        t.push(m.timestamp - t0);
        v.push(val);
      }
    }
  }
  return { t, v };
}

// INS_HNTCH_FREQ @Range (libraries/Filter/HarmonicNotchFilter.cpp:71). Under it is the vehicle
// flying, not a vibration, and it is often the strongest thing in a spectrum.
const NOTCH_MIN_HZ = 10;

/** The strongest peaks a notch could be put on, with their width at half power. */
export function findPeaks(freq: number[], mag: number[], count: number): { freq: number; mag: number; bw: number }[] {
  if (mag.length < 3) return [];
  const peaks: { idx: number; val: number }[] = [];
  for (let i = 1; i < mag.length - 1; i++) {
    if (freq[i] >= NOTCH_MIN_HZ && mag[i] > mag[i - 1] && mag[i] > mag[i + 1]) {
      peaks.push({ idx: i, val: mag[i] });
    }
  }
  peaks.sort((a, b) => b.val - a.val);

  return peaks.slice(0, count).map((p) => {
    const threshold = p.val * 0.707;
    let lo = p.idx,
      hi = p.idx;
    while (lo > 0 && mag[lo] > threshold) lo--;
    while (hi < mag.length - 1 && mag[hi] > threshold) hi++;
    return { freq: freq[p.idx], mag: p.val, bw: Math.max(freq[hi] - freq[lo], freq[1] - freq[0]) };
  });
}

export function computeFFT(values: number[], sampleRate: number): { freq: number[]; mag: number[] } {
  const N = 1 << Math.floor(Math.log2(values.length));
  if (N < 8) return { freq: [], mag: [] };

  const re = values.slice(0, N);
  const im = new Array(N).fill(0);

  // Bit-reversal permutation — required for Cooley-Tukey DIT
  const logN = Math.log2(N);
  for (let i = 0; i < N; i++) {
    let rev = 0;
    for (let b = 0; b < logN; b++) rev |= ((i >> b) & 1) << (logN - 1 - b);
    if (rev > i) {
      [re[i], re[rev]] = [re[rev], re[i]];
      [im[i], im[rev]] = [im[rev], im[i]];
    }
  }

  for (let s = 1; s <= logN; s++) {
    const m = 1 << s;
    const wm_re = Math.cos((-2 * Math.PI) / m);
    const wm_im = Math.sin((-2 * Math.PI) / m);
    for (let k = 0; k < N; k += m) {
      let w_re = 1,
        w_im = 0;
      for (let j = 0; j < m / 2; j++) {
        const t_re = w_re * re[k + j + m / 2] - w_im * im[k + j + m / 2];
        const t_im = w_re * im[k + j + m / 2] + w_im * re[k + j + m / 2];
        const u_re = re[k + j],
          u_im = im[k + j];
        re[k + j] = u_re + t_re;
        im[k + j] = u_im + t_im;
        re[k + j + m / 2] = u_re - t_re;
        im[k + j + m / 2] = u_im - t_im;
        const nw_re = w_re * wm_re - w_im * wm_im;
        w_im = w_re * wm_im + w_im * wm_re;
        w_re = nw_re;
      }
    }
  }

  const freq: number[] = [];
  const mag: number[] = [];
  const halfN = N / 2;
  for (let i = 1; i < halfN; i++) {
    freq.push((i * sampleRate) / N);
    mag.push(Math.sqrt(re[i] * re[i] + im[i] * im[i]) / halfN);
  }
  return { freq, mag };
}
