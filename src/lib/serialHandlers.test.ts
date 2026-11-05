import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const H = vi.hoisted(() => ({
  drone: {} as Record<string, unknown>,
  events: [] as { event_type: string; text: string }[],
  toasts: [] as { text: string; level: string }[],
  flights: [] as Record<string, unknown>[],
}));

vi.mock('./stores.svelte', () => ({
  app: { drone: H.drone, events: H.events },
  addToast: (text: string, level: string) => H.toasts.push({ text, level }),
  addEvent: (ev: { event_type: string; text: string }) => H.events.push(ev),
  isPlane: () => false,
}));
vi.mock('./i18n.svelte', () => ({
  t: (key: string) => key,
  i18nState: { locale: 'en' },
}));
vi.mock('./flightDb', () => ({ saveFlightRecord: (r: Record<string, unknown>) => H.flights.push(r) }));

import { buildSerialHandlers } from './serialHandlers';
import type { MavFrame, MessageHandlers } from './mavlink';

const frame = {} as MavFrame;
const heartbeat = (armed: boolean) => ({
  type: 2,
  autopilot: 3,
  baseMode: armed ? 128 : 0,
  customMode: 4,
  systemStatus: 4,
  mavlinkVersion: 3,
});
const position = (lat: number, lon: number, altRel = 0) => ({
  lat,
  lon,
  altMsl: altRel,
  altRel,
  vx: 0,
  vy: 0,
  vz: 0,
  hdg: 0,
});

describe('connect-time command answers', () => {
  it.each([511, 512])("a refused %i is nobody's business", (command) => {
    H.events.length = 0;
    H.toasts.length = 0;
    const h = buildSerialHandlers();
    h.onCommandAck!({ command, result: 2 } as never, { payloadLen: 3 } as MavFrame);
    expect(H.events).toHaveLength(0);
    expect(H.toasts).toHaveLength(0);
  });
});

describe('serial session state', () => {
  let h: Partial<MessageHandlers>;

  beforeEach(() => {
    for (const k of Object.keys(H.drone)) delete H.drone[k];
    H.drone.remaining = 80;
    H.drone.gs = 0;
    H.events.length = 0;
    H.toasts.length = 0;
    H.flights.length = 0;
    vi.useFakeTimers();
    vi.setSystemTime(1_000_000);
    h = buildSerialHandlers();
  });

  afterEach(() => vi.useRealTimers());

  describe('distance from home', () => {
    it('takes home from the first real fix', () => {
      h.onGlobalPositionInt!(position(34.2, 108.9) as never, frame);
      expect(H.drone.home_lat).toBe(34.2);
      expect(H.drone.dist_home).toBe(0);
      expect(H.events.map((e) => e.event_type)).toEqual(['home_set']);
    });

    it('ignores the (0,0) an FC reports before it has a position', () => {
      h.onGlobalPositionInt!(position(0, 0) as never, frame);
      expect(H.drone.home_lat).toBeUndefined();
      expect(H.events).toHaveLength(0);
    });

    it('measures from HOME_POSITION once the FC sends it', () => {
      h.onHomePosition!({ lat: 34.2, lon: 108.9 } as never, frame);
      h.onGlobalPositionInt!(position(34.201, 108.9) as never, frame);
      expect(H.drone.dist_home).toBeCloseTo(111.32, 1);
    });
  });

  describe('arming', () => {
    it('counts flight time while armed and stops at disarm', () => {
      h.onHeartbeat!(heartbeat(true) as never, frame);
      vi.advanceTimersByTime(5000);
      h.onHeartbeat!(heartbeat(true) as never, frame);
      expect(H.drone.flight_time).toBe(5);
      h.onHeartbeat!(heartbeat(false) as never, frame);
      expect(H.drone.flight_time).toBe(0);
    });

    it('announces arm and disarm once each', () => {
      h.onHeartbeat!(heartbeat(true) as never, frame);
      h.onHeartbeat!(heartbeat(true) as never, frame);
      h.onHeartbeat!(heartbeat(false) as never, frame);
      expect(H.events.map((e) => e.event_type)).toEqual(['armed', 'disarmed']);
      expect(H.toasts.filter((t) => t.text.startsWith('toast.')).map((t) => t.level)).toEqual(['warn', 'success']);
    });

    it('reports and records the flight at disarm', () => {
      h.onGlobalPositionInt!(position(34.2, 108.9) as never, frame);
      h.onHeartbeat!(heartbeat(true) as never, frame);
      vi.advanceTimersByTime(60000);
      h.onGlobalPositionInt!(position(34.2, 108.9, 30) as never, frame);
      h.onGlobalPositionInt!(position(34.201, 108.9, 12) as never, frame);
      H.drone.remaining = 70;
      h.onHeartbeat!(heartbeat(false) as never, frame);
      expect(H.drone.flight_summary).toEqual({
        duration: 60,
        max_alt: 30,
        max_speed: 0,
        total_dist: 111,
        bat_used: 10,
      });
      expect(H.flights).toHaveLength(1);
    });

    it('clears the last summary when armed again', () => {
      H.drone.flight_summary = { duration: 1 };
      h.onHeartbeat!(heartbeat(true) as never, frame);
      expect(H.drone.flight_summary).toBeNull();
    });
  });

  describe('battery time left', () => {
    const status = (remaining: number) => ({ voltage: 12, current: 1, remaining });

    it('estimates from the drain rate once there is enough history', () => {
      h.onHeartbeat!(heartbeat(true) as never, frame);
      H.drone.armed = true;
      h.onSysStatus!(status(80) as never, frame);
      vi.advanceTimersByTime(20000);
      h.onSysStatus!(status(78) as never, frame);
      expect(H.drone.bat_time).toBe(780);
    });

    it('gives no estimate on the ground', () => {
      h.onSysStatus!(status(80) as never, frame);
      vi.advanceTimersByTime(20000);
      h.onSysStatus!(status(78) as never, frame);
      expect(H.drone.bat_time).toBeUndefined();
    });
  });

  describe('pre-arm messages', () => {
    const text = (t: string) => ({ severity: 4, text: t });

    it('keeps one entry per cause', () => {
      h.onStatusText!(text('PreArm: Need 3D Fix') as never, frame);
      h.onStatusText!(text('PreArm: Need 3D Fix') as never, frame);
      h.onStatusText!(text('Arm: Compass not healthy') as never, frame);
      expect(H.drone.prearm).toEqual(['Need 3D Fix', 'Compass not healthy']);
      expect(H.events).toHaveLength(2);
    });

    it('leaves other messages alone', () => {
      h.onStatusText!(text('EKF3 IMU0 is using GPS') as never, frame);
      expect(H.drone.prearm).toBeUndefined();
      expect(H.events).toHaveLength(1);
    });

    it('does not grow without limit', () => {
      for (let i = 0; i < 25; i++) h.onStatusText!(text(`PreArm: cause ${i}`) as never, frame);
      expect((H.drone.prearm as string[]).length).toBeLessThanOrEqual(20);
    });
  });

  it('lists nearby aircraft and drops those not heard for a minute', () => {
    const aircraft = (icao: number) => ({
      icao,
      lat: 34.2,
      lon: 108.9,
      alt: 1200.4,
      hdg: 90.4,
      speed: 55.55,
      vs: -1.26,
      callsign: 'CCA123 ',
    });
    h.onAdsbVehicle!(aircraft(1) as never, frame);
    expect(H.drone.adsb).toMatchObject([{ icao: 1, alt: 1200, hdg: 90, speed: 55.6, vs: -1.3, callsign: 'CCA123' }]);
    vi.advanceTimersByTime(61000);
    h.onAdsbVehicle!(aircraft(2) as never, frame);
    expect((H.drone.adsb as { icao: number }[]).map((a) => a.icao)).toEqual([2]);
  });
});
