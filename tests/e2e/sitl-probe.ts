import net from 'node:net';
import {
  dispatchFrame,
  encodeCommandLong,
  encodeFrame,
  encodeMissionRequestInt,
  encodeMissionRequestList,
  encodeParamSet,
  parseFrames,
  type GlobalPositionInt,
  type Heartbeat,
} from '../../src/lib/mavlink';

/**
 * A second link to SITL, on its SERIAL1 port, that the page knows nothing about. What a
 * panel shows proves little: this asks the firmware what actually happened.
 */
export interface StoredItem {
  seq: number;
  command: number;
  frame: number;
  param1: number;
  param2: number;
  param3: number;
  param4: number;
  lat: number;
  lon: number;
  alt: number;
}

const GCS_SYSID = 255; // SYSID_MYGCS: the FC takes RC override only from this system
const PROBE_COMPID = 190;
const MSG_INTERVAL = 511;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class Probe {
  texts: string[] = [];
  acks: { command: number; result: number }[] = [];
  heartbeat: Heartbeat | null = null;
  position: GlobalPositionInt | null = null;
  /** The highest the firmware has reported itself above home. */
  maxAltitude = 0;
  servo: number[] = [];
  rc: number[] = [];
  missionSeq = -1;
  reached: number[] = [];
  /** MAG_CAL_PROGRESS: -1 until a compass calibration runs, then how far it got. */
  magCal = -1;
  /** MAG_CAL_REPORT: cal_status of the last run, 4 = success. */
  magCalResult = -1;

  private seq = 0;
  private pending: Uint8Array = new Uint8Array(0);
  private params = new Map<string, number>();
  private paramTotal = 0;
  private count: number | null = null;
  private item: StoredItem | null = null;

  private constructor(private socket: net.Socket) {
    socket.on('data', (chunk) => this.onData(chunk as Buffer));
    // The FC reports where the link went; nothing here should end a test by itself.
    socket.on('error', () => {});
  }

  static async open(target: string): Promise<Probe> {
    const [host, port] = target.split(':');
    const socket = net.connect(Number(port), host);
    await new Promise((ok, fail) => socket.once('connect', ok).once('error', fail));
    const probe = new Probe(socket);
    // Per channel (GCS_Common.cpp set_message_interval), so this adds nothing to the page's link.
    for (const [id, interval] of [
      [0, 1_000_000], // HEARTBEAT
      [33, 100_000], // GLOBAL_POSITION_INT
      [36, 100_000], // SERVO_OUTPUT_RAW
      [65, 100_000], // RC_CHANNELS
      [42, 500_000], // MISSION_CURRENT
      [191, 500_000], // MAG_CAL_PROGRESS
      [192, 500_000], // MAG_CAL_REPORT
    ]) {
      probe.command(MSG_INTERVAL, id, interval);
    }
    return probe;
  }

  private onData(chunk: Buffer) {
    const joined = new Uint8Array(this.pending.length + chunk.length);
    joined.set(this.pending);
    joined.set(chunk, this.pending.length);
    const { frames, remaining } = parseFrames(joined);
    this.pending = remaining;
    for (const f of frames) {
      dispatchFrame(f, {
        onHeartbeat: (m, fr) => {
          // The FC forwards the backend's heartbeats to this port too.
          if (fr.sysId === 1 && fr.compId === 1) this.heartbeat = m;
        },
        onGlobalPositionInt: (m) => {
          this.position = m;
          this.maxAltitude = Math.max(this.maxAltitude, m.altRel);
        },
        onServoOutput: (m) => (this.servo = m.outputs),
        onRcChannels: (m) => (this.rc = m.channels),
        onParamValue: (m) => {
          this.params.set(m.paramId, m.paramValue);
          this.paramTotal = m.paramCount;
        },
        onCommandAck: (m) => this.acks.push(m),
        onMissionCurrent: (m) => (this.missionSeq = m.seq),
        onMissionItemReached: (m) => this.reached.push(m.seq),
        onMissionCount: (m) => (this.count = m.count),
        onMissionItemInt: (m) => {
          this.item = {
            seq: m.seq,
            command: m.command,
            frame: m.frame,
            param1: m.param1,
            param2: m.param2,
            param3: m.param3,
            param4: m.param4,
            lat: m.x / 1e7,
            lon: m.y / 1e7,
            alt: m.z,
          };
        },
        onMagCalProgress: (m) => (this.magCal = m.completionPct),
        onMagCalReport: (m) => (this.magCalResult = m.calStatus),
        onStatusText: (m) => this.texts.push(m.text),
      });
    }
  }

  private send(id: number, payload: Uint8Array) {
    this.socket.write(encodeFrame(id, payload, GCS_SYSID, PROBE_COMPID, this.seq++ & 0xff));
  }

  command(id: number, p1 = 0, p2 = 0, p3 = 0, p4 = 0, p5 = 0, p6 = 0, p7 = 0) {
    this.send(76, encodeCommandLong(1, 1, id, 0, p1, p2, p3, p4, p5, p6, p7));
  }

  private async until<T>(read: () => T | null | undefined, ask: () => void, what: string): Promise<T> {
    for (let attempt = 0; attempt < 5; attempt++) {
      ask();
      for (let i = 0; i < 20; i++) {
        const value = read();
        if (value !== null && value !== undefined) return value;
        await sleep(50);
      }
    }
    throw new Error(`no answer from the FC: ${what}`);
  }

  /** A parameter as the firmware holds it now. */
  param(name: string): Promise<number> {
    this.params.delete(name);
    const request = new Uint8Array(20);
    new DataView(request.buffer).setInt16(0, -1, true);
    request[2] = 1;
    request[3] = 1;
    request.set(new TextEncoder().encode(name).slice(0, 16), 4);
    return this.until(
      () => this.params.get(name),
      () => this.send(20, request),
      `PARAM_REQUEST_READ ${name}`,
    );
  }

  /** How many parameters the FC says it has. */
  async paramCount(): Promise<number> {
    await this.param('FLTMODE1');
    return this.paramTotal;
  }

  /** Puts a parameter back between tests. The panels under test never go through here. */
  async setParam(name: string, value: number): Promise<void> {
    this.send(23, encodeParamSet(1, 1, name, value, 9));
    await sleep(100);
  }

  /** Every item of a store (0 mission, 1 fence, 2 rally) as the FC reads it back. */
  async store(missionType = 0): Promise<StoredItem[]> {
    this.count = null;
    const count = await this.until(
      () => this.count,
      () => this.send(43, encodeMissionRequestList(1, 1, missionType)),
      `MISSION_REQUEST_LIST ${missionType}`,
    );
    const items: StoredItem[] = [];
    for (let seq = 0; seq < count; seq++) {
      this.item = null;
      items.push(
        await this.until(
          () => (this.item?.seq === seq ? this.item : null),
          () => this.send(51, encodeMissionRequestInt(1, 1, seq, missionType)),
          `MISSION_REQUEST_INT ${seq}`,
        ),
      );
    }
    return items;
  }

  /** The pilot's sticks: RC_CHANNELS_OVERRIDE, held for as long as it keeps being sent. */
  sticks(channels: number[]) {
    const payload = new Uint8Array(18);
    const dv = new DataView(payload.buffer);
    channels.slice(0, 8).forEach((pwm, i) => dv.setUint16(i * 2, pwm, true));
    payload[16] = 1;
    payload[17] = 1;
    this.send(70, payload);
  }

  get mode(): number {
    return this.heartbeat?.customMode ?? -1;
  }

  get armed(): boolean {
    return ((this.heartbeat?.baseMode ?? 0) & 0x80) !== 0;
  }

  /** Metres above home, from the firmware's own estimate. */
  get altitude(): number {
    return this.position?.altRel ?? 0;
  }

  close() {
    this.socket.destroy();
  }
}
