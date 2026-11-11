import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('./transport', () => ({
  dispatch: vi.fn(),
  isSerialConnected: vi.fn(() => false),
  serialUploadMission: vi.fn(async () => ({ ok: true })),
}));

import { dispatch, isSerialConnected, serialUploadMission } from './transport';
import {
  assistant,
  answerThrough,
  approve,
  decline,
  forgetAssistant,
  handleAssistantRequest,
  withdraw,
  type AssistantReply,
  type AssistantStateMsg,
} from './assistant.svelte';
import { app } from './stores.svelte';
import { paramState } from './paramStore.svelte';
import { defaultState } from './types';

let sent: (AssistantReply | AssistantStateMsg)[];

const replies = () => sent.filter((m): m is AssistantReply => m.type === 'assistant_reply');
const states = (id = 'k1') =>
  sent.filter((m) => m.type === 'assistant_state' && m.id === id).map((m) => (m as AssistantStateMsg).state);
const reply = (id = 'k1') => replies().find((r) => r.id === id);

function ask(kind: string, args: Record<string, unknown> = {}, id = 'k1') {
  handleAssistantRequest({ type: 'assistant_request', id, kind, args });
}

const MISSION = {
  waypoints: [
    { lat: 34.25, lon: 108.94, alt: 30 },
    { lat: 34.26, lon: 108.95, alt: 40, type: 'loiter_time', loiter_param: 10 },
  ],
  takeoff_alt: 15,
  reason: 'Survey the north field',
};

function event(event_type: string, text = event_type, seq?: number) {
  app.events.push({ type: 'event', time: '12:00:00', text, event_type, seq });
}

beforeEach(() => {
  sent = [];
  answerThrough((m) => sent.push(m));
  app.drone = { ...defaultState, connected: true, mode: 'LOITER', lat: 34.25, lon: 108.94 };
  app.activeTransport = 'ws';
  app.waypoints = [];
  app.undoStack = [];
  app.events = [];
  app.defaultAlt = 30;
  // Types as ArduPilot reports them: 9 a float, 2 an INT8, 4 an INT16.
  paramState.list = [
    { name: 'BATT_CAPACITY', value: 5200, type: 6, index: 0 },
    { name: 'BATT_MONITOR', value: 4, type: 2, index: 1 },
    { name: 'WPNAV_SPEED', value: 500, type: 9, index: 2 },
    { name: 'RC1_TRIM', value: 1500, type: 4, index: 3 },
  ];
  forgetAssistant();
  vi.mocked(dispatch).mockClear();
  vi.mocked(isSerialConnected).mockReturnValue(false);
  vi.mocked(serialUploadMission).mockClear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('reads', () => {
  it('status says what the page shows, and no position for none', () => {
    app.drone.lat = 0;
    app.drone.lon = 0;
    ask('status');
    expect(reply()!.ok).toBe(true);
    expect(reply()!.result).toMatchObject({
      link: 'backend',
      connected: true,
      mode: 'LOITER',
      armed: false,
      position: null,
      home: null,
    });
  });

  it('the planned mission, numbered from 1, with its takeoff altitude', () => {
    app.waypoints = [{ lat: 1.5, lon: 2.5, alt: 20, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 }];
    ask('mission');
    expect(reply()!.result).toEqual({
      takeoff_alt_m: 30,
      waypoints: [
        { index: 1, lat: 1.5, lon: 2.5, alt: 20, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 },
      ],
    });
  });

  it('parameters by name and by prefix, and the names it does not know', () => {
    ask('parameters', { names: ['WPNAV_SPEED', 'BATT_*', 'NO_SUCH'] });
    expect(reply()!.result).toEqual({
      values: { WPNAV_SPEED: 500, BATT_CAPACITY: 5200, BATT_MONITOR: 4 },
      unknown: ['NO_SUCH'],
      left_out: 0,
    });
  });

  it('parameters the page has not read are not guessed at', () => {
    paramState.list = [];
    ask('parameters', { names: ['WPNAV_SPEED'] });
    expect(reply()!.ok).toBe(false);
    expect(reply()!.error).toContain('Read All');
  });

  it('at most 200 values in one answer', () => {
    paramState.list = Array.from({ length: 250 }, (_, i) => ({ name: `SR0_${i}`, value: i, type: 9, index: i }));
    ask('parameters', { names: ['SR0_*'] });
    const result = reply()!.result as { values: Record<string, number>; left_out: number };
    expect(Object.keys(result.values)).toHaveLength(200);
    expect(result.left_out).toBe(50);
  });

  it('an unknown request is answered, and one without an id is not', () => {
    ask('arm');
    handleAssistantRequest({ type: 'assistant_request', kind: 'status', args: {} });
    expect(replies()).toHaveLength(1);
    expect(reply()!.ok).toBe(false);
  });
});

describe('proposals wait for the operator', () => {
  it('a mission is queued, said to be waiting, and nothing is sent', () => {
    ask('propose_mission', MISSION);
    expect(replies()).toEqual([]);
    expect(states()).toEqual(['waiting']);
    expect(assistant.queue[0]).toMatchObject({
      kind: 'propose_mission',
      takeoffAlt: 15,
      reason: 'Survey the north field',
    });
    expect(assistant.queue[0].kind === 'propose_mission' && assistant.queue[0].waypoints[1]).toMatchObject({
      type: 'loiter_time',
      loiter_param: 10,
      drop: false,
    });
    expect(dispatch).not.toHaveBeenCalled();
    expect(app.waypoints).toEqual([]);
  });

  it('parameter changes are queued with the values they replace', () => {
    ask('propose_parameters', { values: { WPNAV_SPEED: 800 }, reason: 'faster' });
    expect(replies()).toEqual([]);
    expect(assistant.queue[0]).toMatchObject({ changes: [{ name: 'WPNAV_SPEED', from: 500, to: 800 }] });
  });

  it.each([
    ['no vehicle', () => (app.drone.connected = false), 'No vehicle'],
    ['an armed vehicle', () => (app.drone.armed = true), 'armed'],
  ])('nothing is taken with %s, and the ending says refused', (_, setUp, words) => {
    setUp();
    ask('propose_mission', MISSION);
    ask('propose_parameters', { values: { WPNAV_SPEED: 800 } }, 'k2');
    expect(assistant.queue).toEqual([]);
    for (const id of ['k1', 'k2']) {
      expect(reply(id)!.error).toContain(words);
      expect(reply(id)!.result).toEqual({ outcome: 'refused' });
    }
  });

  it.each([
    [{ lat: 34.2, lon: 108.9, alt: 30, drop: true }, 'drop'],
    [{ lat: 34.2, lon: 108.9, alt: 30, cmd_servo: { num: 9, pwm: 1900 } }, 'cmd_servo'],
    [{ lat: 95, lon: 108.9, alt: 30 }, 'off the map'],
    [{ lat: 34.2, lon: 190, alt: 30 }, 'off the map'],
    [{ lat: 34.2, lon: 'east', alt: 30 }, 'lon'],
  ])('a waypoint that cannot be proposed: %o', (waypoint, words) => {
    ask('propose_mission', { waypoints: [waypoint] });
    expect(assistant.queue).toEqual([]);
    expect(reply()!.error).toContain(words);
  });

  it('a spline is no waypoint for a plane', () => {
    app.drone.vtype_raw = 1;
    ask('propose_mission', { waypoints: [{ lat: 34.2, lon: 108.9, alt: 30, type: 'spline' }] });
    expect(reply()!.error).toContain('spline');
  });

  it('a takeoff altitude of 0 or less', () => {
    ask('propose_mission', { ...MISSION, takeoff_alt: 0 });
    expect(reply()!.error).toContain('takeoff_alt');
  });

  it('a parameter the page does not know, or no number', () => {
    ask('propose_parameters', { values: { NO_SUCH: 1 } });
    ask('propose_parameters', { values: { WPNAV_SPEED: Number.NaN } }, 'k2');
    expect(reply('k1')!.error).toContain('NO_SUCH');
    expect(reply('k2')!.error).toContain('finite');
    expect(assistant.queue).toEqual([]);
  });

  // ArduPilot would store 1 for 1.5 and 127 for 300 in an INT8 (AP_Param.cpp set_float).
  it.each([
    [{ BATT_MONITOR: 1.5 }, 'BATT_MONITOR holds whole numbers from -128 to 127'],
    [{ BATT_MONITOR: 300 }, 'BATT_MONITOR holds whole numbers from -128 to 127'],
    [{ RC1_TRIM: 40000 }, 'RC1_TRIM holds whole numbers from -32768 to 32767'],
  ])('a value an integer parameter cannot hold: %o', (values, words) => {
    ask('propose_parameters', { values });
    expect(reply()!.error).toBe(`${words}.`);
    expect(assistant.queue).toEqual([]);
  });

  it('a float parameter takes a fraction, an integer one a whole number in range', () => {
    ask('propose_parameters', { values: { WPNAV_SPEED: 512.5, BATT_MONITOR: -5, BATT_CAPACITY: 2_000_000 } });
    expect(replies()).toEqual([]);
    expect(assistant.queue).toHaveLength(1);
  });
});

describe("the operator's decision", () => {
  it('declined: answered so, and nothing sent', () => {
    ask('propose_mission', MISSION);
    decline('k1');
    expect(reply()).toEqual({
      type: 'assistant_reply',
      id: 'k1',
      ok: false,
      error: 'The operator declined it.',
      result: { outcome: 'declined' },
    });
    expect(assistant.queue).toEqual([]);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('withdrawn by the assistant while it waits: gone, and answered withdrawn', () => {
    ask('propose_mission', MISSION);
    withdraw('k1');
    expect(assistant.queue).toEqual([]);
    expect(reply()).toMatchObject({ ok: false, result: { outcome: 'withdrawn' } });
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('a mission approved over the backend replaces the plan, uploads it and waits for the ack', async () => {
    event('connected');
    ask('propose_mission', MISSION);
    const done = approve('k1');
    expect(states()).toEqual(['waiting', 'running']);
    expect(app.undoStack).toHaveLength(1);
    expect(app.waypoints).toHaveLength(2);
    expect(dispatch).toHaveBeenCalledWith('mission_upload', undefined, {
      waypoints: app.waypoints,
      takeoff_alt: 15,
    });
    event('mission_ack_ok', 'Mission ack: success');
    await done;
    expect(reply()).toEqual({
      type: 'assistant_reply',
      id: 'k1',
      ok: true,
      result: { uploaded_waypoints: 2, takeoff_alt_m: 15 },
    });
    expect(assistant.queue).toEqual([]);
  });

  it('a withdrawal once approved does not stop it, and the result still comes', async () => {
    ask('propose_mission', MISSION);
    const done = approve('k1');
    withdraw('k1');
    expect(reply()).toBeUndefined();
    event('mission_ack_ok');
    await done;
    expect(reply()!.ok).toBe(true);
  });

  it('an ack from before the upload is not its answer, whatever its number', async () => {
    vi.useFakeTimers();
    // From a backend before a restart: numbered higher than anything the new one sends.
    event('mission_ack_ok', 'old', 120);
    ask('propose_mission', MISSION);
    const done = approve('k1');
    event('connected', 'new backend', 1);
    await vi.advanceTimersByTimeAsync(18000);
    await done;
    expect(reply()!.ok).toBe(false);
    expect(reply()!.error).toContain('No answer');
  });

  it('a long mission is given longer to upload', async () => {
    vi.useFakeTimers();
    const waypoints = Array.from({ length: 30 }, (_, i) => ({ lat: 34.25 + i * 0.001, lon: 108.94, alt: 30 }));
    ask('propose_mission', { waypoints });
    const done = approve('k1');
    await vi.advanceTimersByTimeAsync(40000);
    expect(reply()).toBeUndefined();
    event('mission_ack_ok');
    await vi.advanceTimersByTimeAsync(200);
    await done;
    expect(reply()!.ok).toBe(true);
  });

  it('a mission the flight controller refuses', async () => {
    ask('propose_mission', MISSION);
    const done = approve('k1');
    event('mission_ack_fail', 'Mission ack: failed(1)');
    await done;
    expect(reply()).toMatchObject({ ok: false, result: { outcome: 'failed' } });
    expect(reply()!.error).toContain('failed(1)');
  });

  it('over USB the upload is the panel one, with the takeoff altitude asked for', async () => {
    vi.mocked(isSerialConnected).mockReturnValue(true);
    ask('propose_mission', MISSION);
    await approve('k1');
    expect(serialUploadMission).toHaveBeenCalledWith(app.waypoints, 15);
    expect(dispatch).not.toHaveBeenCalled();
    expect(reply()!.ok).toBe(true);
  });

  it('armed while it waited: refused at approval, nothing sent', async () => {
    ask('propose_mission', MISSION);
    app.drone.armed = true;
    await approve('k1');
    expect(reply()).toMatchObject({ ok: false, result: { outcome: 'refused' } });
    expect(reply()!.error).toContain('armed');
    expect(states()).toEqual(['waiting']);
    expect(dispatch).not.toHaveBeenCalled();
    expect(app.waypoints).toEqual([]);
  });

  it('parameters approved: each is set, and the answer waits for the flight controller', async () => {
    ask('propose_parameters', { values: { WPNAV_SPEED: 800, BATT_MONITOR: 4 } });
    const done = approve('k1');
    expect(vi.mocked(dispatch).mock.calls).toEqual([
      ['param_set', undefined, { name: 'WPNAV_SPEED', value: 800 }],
      ['param_set', undefined, { name: 'BATT_MONITOR', value: 4 }],
    ]);
    paramState.list = paramState.list.map((p) => (p.name === 'WPNAV_SPEED' ? { ...p, value: 800 } : p));
    await done;
    expect(reply()).toMatchObject({ ok: true, result: { values: { WPNAV_SPEED: 800, BATT_MONITOR: 4 } } });
  });

  it('a value the flight controller does not take back is reported', async () => {
    vi.useFakeTimers();
    ask('propose_parameters', { values: { WPNAV_SPEED: 800 } });
    const done = approve('k1');
    await vi.advanceTimersByTimeAsync(11000);
    await done;
    expect(reply()).toMatchObject({ ok: false, result: { outcome: 'failed' } });
    expect(reply()!.error).toContain('did not confirm WPNAV_SPEED');
  });

  it('only one approval runs at a time', async () => {
    ask('propose_parameters', { values: { BATT_MONITOR: 4 } });
    ask('propose_parameters', { values: { BATT_MONITOR: 4 } }, 'k2');
    const first = approve('k1');
    await approve('k2');
    await first;
    expect(reply('k2')).toBeUndefined();
    expect(assistant.queue.map((p) => p.id)).toEqual(['k2']);
  });

  it('a closed websocket drops what waits', () => {
    ask('propose_mission', MISSION);
    assistant.present = 1;
    forgetAssistant();
    expect(assistant.queue).toEqual([]);
    expect(assistant.present).toBe(0);
  });
});
