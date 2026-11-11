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
} from './assistant.svelte';
import { app } from './stores.svelte';
import { paramState } from './paramStore.svelte';
import { defaultState } from './types';

let replies: AssistantReply[];

function ask(kind: string, args: Record<string, unknown> = {}, id = 'k1') {
  handleAssistantRequest({ type: 'assistant_request', id, kind, args });
}

const reply = (id = 'k1') => replies.find((r) => r.id === id);

const MISSION = {
  waypoints: [
    { lat: 34.25, lon: 108.94, alt: 30 },
    { lat: 34.26, lon: 108.95, alt: 40, type: 'loiter_time', loiter_param: 10 },
  ],
  takeoff_alt: 15,
  reason: 'Survey the north field',
};

function event(seq: number, event_type: string, text = event_type) {
  app.events.push({ type: 'event', time: '12:00:00', text, event_type, seq });
}

beforeEach(() => {
  replies = [];
  answerThrough((r) => replies.push(r));
  app.drone = { ...defaultState, connected: true, mode: 'LOITER', lat: 34.25, lon: 108.94 };
  app.activeTransport = 'ws';
  app.waypoints = [];
  app.undoStack = [];
  app.events = [];
  app.defaultAlt = 30;
  paramState.list = [
    { name: 'BATT_CAPACITY', value: 5200, type: 9, index: 0 },
    { name: 'BATT_MONITOR', value: 4, type: 9, index: 1 },
    { name: 'WPNAV_SPEED', value: 500, type: 9, index: 2 },
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
    const status = reply()!.result as Record<string, unknown>;
    expect(reply()!.ok).toBe(true);
    expect(status).toMatchObject({
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
    expect(replies).toHaveLength(1);
    expect(reply()!.ok).toBe(false);
  });
});

describe('proposals wait for the operator', () => {
  it('a mission is queued and nothing is sent', () => {
    ask('propose_mission', MISSION);
    expect(replies).toEqual([]);
    expect(assistant.queue).toHaveLength(1);
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
    expect(replies).toEqual([]);
    expect(assistant.queue[0]).toMatchObject({ changes: [{ name: 'WPNAV_SPEED', from: 500, to: 800 }] });
  });

  it.each([
    ['no vehicle', () => (app.drone.connected = false), 'No vehicle'],
    ['an armed vehicle', () => (app.drone.armed = true), 'armed'],
  ])('nothing is taken with %s', (_, setUp, words) => {
    setUp();
    ask('propose_mission', MISSION);
    ask('propose_parameters', { values: { WPNAV_SPEED: 800 } }, 'k2');
    expect(assistant.queue).toEqual([]);
    expect(reply('k1')!.error).toContain(words);
    expect(reply('k2')!.error).toContain(words);
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
});

describe("the operator's decision", () => {
  it('declined: answered so, and nothing sent', () => {
    ask('propose_mission', MISSION);
    decline('k1');
    expect(reply()).toEqual({ type: 'assistant_reply', id: 'k1', ok: false, error: 'The operator declined it.' });
    expect(assistant.queue).toEqual([]);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('withdrawn by the assistant: gone, and no answer due', () => {
    ask('propose_mission', MISSION);
    withdraw('k1');
    expect(assistant.queue).toEqual([]);
    expect(replies).toEqual([]);
  });

  it('a mission approved over the backend replaces the plan, uploads it and waits for the ack', async () => {
    event(7, 'connected');
    ask('propose_mission', MISSION);
    const done = approve('k1');
    expect(app.undoStack).toHaveLength(1);
    expect(app.waypoints).toHaveLength(2);
    expect(dispatch).toHaveBeenCalledWith('mission_upload', undefined, {
      waypoints: app.waypoints,
      takeoff_alt: 15,
    });
    event(8, 'mission_ack_ok', 'Mission ack: success');
    await done;
    expect(reply()).toEqual({
      type: 'assistant_reply',
      id: 'k1',
      ok: true,
      result: { uploaded_waypoints: 2, takeoff_alt_m: 15 },
    });
    expect(assistant.queue).toEqual([]);
  });

  it('an ack from before the upload is not its answer', async () => {
    vi.useFakeTimers();
    event(7, 'mission_ack_ok');
    ask('propose_mission', MISSION);
    const done = approve('k1');
    await vi.advanceTimersByTimeAsync(16000);
    await done;
    expect(reply()!.ok).toBe(false);
    expect(reply()!.error).toContain('No answer');
  });

  it('a mission the flight controller refuses', async () => {
    ask('propose_mission', MISSION);
    const done = approve('k1');
    event(1, 'mission_ack_fail', 'Mission ack: failed(1)');
    await done;
    expect(reply()!.ok).toBe(false);
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
    expect(reply()!.error).toContain('armed');
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
    expect(reply()!.ok).toBe(false);
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
