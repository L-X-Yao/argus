/**
 * Requests of the AI assistant (backend/mcp_server.py). The backend passes them to the page that
 * holds command authority (backend/ws_manager.py), and this answers them. A read is answered
 * from what the page shows. A change waits in `assistant.queue` until the operator approves or
 * declines it in AssistantDialog, and an approval runs it through the code the panels use, on
 * either link. A flight command takes a slide after the approval, as the RTL button does. Nothing
 * here changes the vehicle without that approval.
 *
 * What goes back to the assistant is English written for the model, and is not shown here.
 */
import { app, pushUndo, saveWaypoints, addToast, showSlide } from './stores.svelte';
import { paramState } from './paramStore.svelte';
import { cleanWaypoints, MissionDataError } from './missionIO';
import { validateMissionWaypoints } from './missionUpload';
import { dispatch, isSerialConnected, serialUploadMission } from './transport';
import { specialModes, vehicleKind } from './vehicleModes';
import { t } from './i18n.svelte';
import type { DroneEvent, Waypoint } from './types';

export interface MissionProposal {
  id: string;
  kind: 'propose_mission';
  waypoints: Waypoint[];
  takeoffAlt: number;
  reason: string;
}

export interface ParameterProposal {
  id: string;
  kind: 'propose_parameters';
  changes: { name: string; from: number; to: number }[];
  reason: string;
}

export type FlightCommand = 'rtl' | 'hold' | 'land';

/** A flight command, for a vehicle that is armed: to bring it back, stop it or put it down. */
export interface CommandProposal {
  id: string;
  kind: 'propose_command';
  command: FlightCommand;
  reason: string;
}

export type Proposal = MissionProposal | ParameterProposal | CommandProposal;

export interface AssistantReply {
  type: 'assistant_reply';
  id: string;
  ok: boolean;
  result?: unknown;
  error?: string;
}

/** Where a proposal stands before its answer: before the operator, or approved and running. */
export interface AssistantStateMsg {
  type: 'assistant_state';
  id: string;
  state: 'waiting' | 'running';
}

/** How a proposal ended other than done: backend/mcp_server.py tells the model by it. */
type Ending = 'declined' | 'withdrawn' | 'refused' | 'failed';
type Outcome = { ok: true; result: unknown } | { ok: false; error: string; ending?: Ending };
type Fields = Record<string, unknown>;

class AssistantState {
  /** Assistants connected to the backend. */
  present: number = $state(0);
  /** Changes waiting for the operator, oldest first. */
  queue: Proposal[] = $state([]);
  /** An approved change on its way to the vehicle. */
  running: boolean = $state(false);
}

/** The proposal approved and running now: no withdrawal stops it. */
let runningId: string | null = null;

export const assistant = new AssistantState();

// The only fields a proposed waypoint may have: no relay drop, servo, camera or other command.
const WAYPOINT_FIELDS = new Set(['lat', 'lon', 'alt', 'type', 'loiter_param', 'delay', 'speed']);
const MAX_VALUES = 200;
const MAX_CHANGES = 50;
const REASON_MAX = 500;
// The backend allows an upload 30 s for each item (config MISSION_ITEM_TIMEOUT), and a slow
// radio needs several seconds for a long one: the wait grows with the mission.
const UPLOAD_WAIT_MS = 15000;
const UPLOAD_WAIT_PER_WAYPOINT_MS = 1000;
const PARAM_WAIT_MS = 10000;
// A mode change shows in the next heartbeat, about one a second, also over a slow radio.
const COMMAND_WAIT_MS = 10000;

const OFF_THE_MAP = 'A waypoint is off the map: latitude within ±90, longitude within ±180.';

const MISSION_ERRORS: Record<string, string> = {
  'mission.err.noWaypoints': 'The mission has no waypoints.',
  'mission.err.tooLarge': 'A mission holds at most 500 waypoints.',
  'mission.err.badCoords':
    'A waypoint is off the map: latitude within ±90 and not 0, longitude within ±180, altitude from -500 to 100000 m.',
};

let send: (msg: AssistantReply | AssistantStateMsg) => void = () => {};

/** Where answers go: the websocket the requests came in on (ws.ts). */
export function answerThrough(sender: (msg: AssistantReply | AssistantStateMsg) => void): void {
  send = sender;
}

const isFields = (v: unknown): v is Fields => typeof v === 'object' && v !== null && !Array.isArray(v);

/** The one answer each request gets. An ending other than done travels as result.outcome. */
function answer(id: string, outcome: Outcome): void {
  if (outcome.ok) send({ type: 'assistant_reply', id, ok: true, result: outcome.result });
  else
    send({
      type: 'assistant_reply',
      id,
      ok: false,
      error: outcome.error,
      result: { outcome: outcome.ending ?? 'failed' },
    });
}

export function handleAssistantRequest(msg: unknown): void {
  if (!isFields(msg) || typeof msg.id !== 'string' || typeof msg.kind !== 'string') return;
  const id = msg.id;
  const args = isFields(msg.args) ? msg.args : {};
  try {
    switch (msg.kind) {
      case 'status':
        answer(id, { ok: true, result: status() });
        return;
      case 'mission':
        answer(id, { ok: true, result: mission() });
        return;
      case 'parameters':
        answer(id, parameters(args));
        return;
      case 'propose_mission':
      case 'propose_parameters':
      case 'propose_command': {
        const proposal =
          msg.kind === 'propose_mission'
            ? proposeMission(id, args)
            : msg.kind === 'propose_parameters'
              ? proposeParameters(id, args)
              : proposeCommand(id, args);
        if ('error' in proposal) {
          answer(id, { ok: false, error: proposal.error, ending: 'refused' });
        } else {
          assistant.queue.push(proposal);
          send({ type: 'assistant_state', id, state: 'waiting' });
        }
        return;
      }
      default:
        answer(id, { ok: false, error: `Argus has no request called ${msg.kind}.` });
    }
  } catch (e) {
    answer(id, { ok: false, error: `The Argus page could not answer: ${e instanceof Error ? e.message : String(e)}` });
  }
}

// ---- reads ------------------------------------------------------------------------------

function status() {
  const d = app.drone;
  const at = (lat: number, lon: number) => (lat !== 0 || lon !== 0 ? { lat, lon } : null);
  return {
    // activeTransport says which link this page started. A page opened on a backend that some
    // other page connected never started one, and sees the vehicle all the same.
    link: app.activeTransport === 'serial' ? 'usb' : d.connected ? 'backend' : 'none',
    connected: d.connected,
    vehicle: d.connected ? vehicleKind() : null,
    autopilot: d.autopilot === 3 ? 'ArduPilot' : d.autopilot === 0 ? 'not known yet' : `MAV_AUTOPILOT ${d.autopilot}`,
    mode: d.mode,
    armed: d.armed,
    landed: d.landed,
    position: at(d.lat, d.lon),
    altitude_above_home_m: d.alt_rel,
    altitude_above_sea_m: d.alt_msl,
    heading_deg: d.hdg,
    ground_speed_ms: d.gs,
    air_speed_ms: d.airspeed,
    climb_ms: d.climb,
    home: at(d.home_lat, d.home_lon),
    distance_to_home_m: d.dist_home,
    flight_time_s: d.flight_time,
    battery: { voltage_v: d.voltage, current_a: d.current, remaining_pct: d.remaining },
    gps: { fix: d.gps_fix, satellites: d.gps_sats },
    mission_item: d.wp,
    seconds_since_last_message: d.link_age,
    prearm_failures: [...d.prearm],
    recent_messages: app.events.slice(-10).map((e) => ({ time: e.time, text: e.text })),
  };
}

function mission() {
  return {
    takeoff_alt_m: app.defaultAlt,
    waypoints: app.waypoints.map((w, i) => ({ index: i + 1, ...JSON.parse(JSON.stringify(w)) })),
  };
}

function byName(): Map<string, number> {
  return new Map(paramState.list.map((p) => [p.name, p.value]));
}

// MAV_PARAM_TYPE of the integer kinds, and the values each holds. ArduPilot reports AP_PARAM_INT8,
// INT16 and INT32 as these (libraries/GCS_MAVLink/GCS_MAVLink.cpp:119, mav_param_type), and stores
// a value set for one of them with 0.01 added, cut to its range and truncated
// (libraries/AP_Param/AP_Param.cpp:2299, set_float): 1.5 becomes 1 and 300 in an INT8 becomes 127.
const WHOLE: Record<number, [number, number]> = {
  1: [0, 255],
  2: [-128, 127],
  3: [0, 65535],
  4: [-32768, 32767],
  5: [0, 4294967295],
  6: [-2147483648, 2147483647],
};

const NOT_READ = 'The page has not read the parameters. Ask the operator to read them: Params view, Read All.';

function parameters(args: Fields): Outcome {
  const names = args.names;
  if (!Array.isArray(names) || names.length === 0 || !names.every((n) => typeof n === 'string')) {
    return { ok: false, error: 'names: a list of parameter names, or prefixes ending in *.' };
  }
  if (paramState.list.length === 0) return { ok: false, error: NOT_READ };
  const known = byName();
  const values: Record<string, number> = {};
  const unknown: string[] = [];
  for (const name of names as string[]) {
    if (name.endsWith('*')) {
      const prefix = name.slice(0, -1);
      for (const [n, v] of known) if (n.startsWith(prefix)) values[n] = v;
    } else if (known.has(name)) {
      values[name] = known.get(name)!;
    } else {
      unknown.push(name);
    }
  }
  const found = Object.keys(values);
  const kept = Object.fromEntries(found.slice(0, MAX_VALUES).map((n) => [n, values[n]]));
  return { ok: true, result: { values: kept, unknown, left_out: Math.max(0, found.length - MAX_VALUES) } };
}

// ---- proposals --------------------------------------------------------------------------

/** Why no change can be asked for or made now, or null. */
function refusal(): string | null {
  if (!app.drone.connected) return 'No vehicle is connected to Argus.';
  if (app.drone.armed) return 'The vehicle is armed: Argus takes no changes from the assistant while it is armed.';
  return null;
}

function reasonOf(args: Fields): string {
  return typeof args.reason === 'string' ? args.reason.slice(0, REASON_MAX) : '';
}

function proposeMission(id: string, args: Fields): MissionProposal | { error: string } {
  const refused = refusal();
  if (refused) return { error: refused };
  const raw = args.waypoints;
  if (!Array.isArray(raw) || raw.length === 0) return { error: 'waypoints: a list of at least one waypoint.' };
  for (const [i, item] of raw.entries()) {
    if (!isFields(item)) return { error: `waypoints[${i}] is no object.` };
    const extra = Object.keys(item).filter((k) => !WAYPOINT_FIELDS.has(k));
    if (extra.length > 0) return { error: `waypoints[${i}]: ${extra.join(', ')} cannot be proposed.` };
    // A file's longitude past 180 is read as the same meridian (wrapLongitude). One from the
    // assistant is a mistake, and is not moved to where it might have meant.
    if (typeof item.lon === 'number' && Math.abs(item.lon) > 180) return { error: OFF_THE_MAP };
  }
  let waypoints: Waypoint[];
  try {
    waypoints = cleanWaypoints(raw, app.defaultAlt);
  } catch (e) {
    if (e instanceof MissionDataError) {
      return { error: e.message === 'position' ? OFF_THE_MAP : `waypoints: ${e.message} is not usable.` };
    }
    throw e;
  }
  const valid = validateMissionWaypoints(waypoints);
  if (!valid.ok) return { error: MISSION_ERRORS[valid.error] ?? valid.error };
  // As the upload itself checks, on both links.
  const kind = vehicleKind();
  if (kind === 'plane' && waypoints.some((w) => w.type === 'spline')) {
    return { error: 'A plane flies no spline waypoints.' };
  }
  if (kind === 'sub' && waypoints.some((w) => w.alt > 0)) {
    return { error: 'A submarine takes depths: altitudes of 0 or less.' };
  }
  const takeoff = args.takeoff_alt;
  if (
    takeoff !== undefined &&
    !(typeof takeoff === 'number' && Number.isFinite(takeoff) && takeoff > 0 && takeoff <= 10000)
  ) {
    return { error: 'takeoff_alt: metres above home, more than 0.' };
  }
  return {
    id,
    kind: 'propose_mission',
    waypoints,
    takeoffAlt: typeof takeoff === 'number' ? takeoff : app.defaultAlt,
    reason: reasonOf(args),
  };
}

function proposeParameters(id: string, args: Fields): ParameterProposal | { error: string } {
  const refused = refusal();
  if (refused) return { error: refused };
  const values = args.values;
  if (!isFields(values) || Object.keys(values).length === 0) return { error: 'values: parameter names and numbers.' };
  if (Object.keys(values).length > MAX_CHANGES) return { error: `At most ${MAX_CHANGES} parameters at a time.` };
  if (paramState.list.length === 0) return { error: NOT_READ };
  const known = new Map(paramState.list.map((p) => [p.name, p]));
  const unknown = Object.keys(values).filter((n) => !known.has(n));
  if (unknown.length > 0) return { error: `The page has no parameter called ${unknown.join(', ')}.` };
  const changes: ParameterProposal['changes'] = [];
  for (const [name, to] of Object.entries(values)) {
    if (typeof to !== 'number' || !Number.isFinite(to)) return { error: `${name}: a finite number.` };
    const row = known.get(name)!;
    const range = WHOLE[row.type];
    if (range && !(Number.isInteger(to) && to >= range[0] && to <= range[1])) {
      return { error: `${name} holds whole numbers from ${range[0]} to ${range[1]}.` };
    }
    changes.push({ name, from: row.value, to });
  }
  return { id, kind: 'propose_parameters', changes, reason: reasonOf(args) };
}

const COMMANDS: readonly string[] = ['rtl', 'hold', 'land'];
const NO_MODE: Record<FlightCommand, string> = {
  rtl: 'no return to launch',
  hold: 'no hold mode',
  land: 'no landing mode',
};

/** Why this flight command cannot be asked for or sent now, or null. */
function commandRefusal(command: FlightCommand): string | null {
  if (!app.drone.connected) return 'No vehicle is connected to Argus.';
  if (!app.drone.armed) return 'The vehicle is not armed: a flight command is for a vehicle that is.';
  if (specialModes()[command] === null) return `This ${vehicleKind()} has ${NO_MODE[command]} in Argus.`;
  return null;
}

function proposeCommand(id: string, args: Fields): CommandProposal | { error: string } {
  const command = args.command;
  if (typeof command !== 'string' || !COMMANDS.includes(command)) return { error: 'command: rtl, hold or land.' };
  const refused = commandRefusal(command as FlightCommand);
  if (refused) return { error: refused };
  return { id, kind: 'propose_command', command: command as FlightCommand, reason: reasonOf(args) };
}

// ---- the operator's decision ------------------------------------------------------------

function remove(id: string): void {
  assistant.queue = assistant.queue.filter((p) => p.id !== id);
}

function finish(proposal: Proposal, outcome: Outcome): void {
  remove(proposal.id);
  answer(proposal.id, outcome);
}

const SLIDES: Record<FlightCommand, [string, 'red' | 'orange']> = {
  rtl: ['slide.rtl', 'red'],
  hold: ['assistant.slideHold', 'orange'],
  land: ['assistant.slideLand', 'red'],
};

const waiting = (id: string) => assistant.queue.some((p) => p.id === id);

export async function approve(id: string): Promise<void> {
  const proposal = assistant.queue.find((p) => p.id === id);
  if (!proposal || assistant.running) return;
  if (proposal.kind === 'propose_command') {
    if (refuseCommand(proposal)) return;
    const [text, color] = SLIDES[proposal.command];
    showSlide(t(text), color, () => {
      // The slide takes seconds: by its end the assistant may have taken the proposal back, or
      // the vehicle landed.
      if (!waiting(proposal.id) || assistant.running || refuseCommand(proposal)) return;
      void run(proposal);
    });
    return;
  }
  // It may have waited a while: the vehicle can be armed by now.
  const refused = refusal();
  if (refused) {
    finish(proposal, { ok: false, error: refused, ending: 'refused' });
    addToast(t('assistant.refusedNow'), 'error', 5000);
    return;
  }
  await run(proposal);
}

/** Refuses it when it cannot be sent now, and says so to both; whether it did. */
function refuseCommand(proposal: CommandProposal): boolean {
  const refused = commandRefusal(proposal.command);
  if (!refused) return false;
  finish(proposal, { ok: false, error: refused, ending: 'refused' });
  addToast(t(app.drone.connected ? 'assistant.notArmed' : 'err.noLink'), 'error', 5000);
  return true;
}

async function run(proposal: Proposal): Promise<void> {
  assistant.running = true;
  runningId = proposal.id;
  // From here a withdrawal no longer stops it, and the assistant hears so.
  send({ type: 'assistant_state', id: proposal.id, state: 'running' });
  try {
    const outcome =
      proposal.kind === 'propose_mission'
        ? await runMission(proposal)
        : proposal.kind === 'propose_parameters'
          ? await runParameters(proposal)
          : await runCommand(proposal);
    finish(proposal, outcome);
    if (outcome.ok) addToast(t('assistant.done'), 'success', 4000);
    else addToast(`${t('assistant.failed')}: ${outcome.error}`, 'error', 6000);
  } finally {
    assistant.running = false;
    runningId = null;
  }
}

export function decline(id: string): void {
  const proposal = assistant.queue.find((p) => p.id === id);
  if (proposal && proposal.id !== runningId)
    finish(proposal, { ok: false, error: 'The operator declined it.', ending: 'declined' });
}

/** The assistant takes it back, or has gone. One still waiting is withdrawn and answered so; the
 * one running goes on, and its answer is its result. */
export function withdraw(id: unknown): void {
  if (typeof id !== 'string' || id === runningId) return;
  const proposal = assistant.queue.find((p) => p.id === id);
  if (proposal) finish(proposal, { ok: false, error: 'Withdrawn by the assistant.', ending: 'withdrawn' });
}

/** The websocket closed: the backend has told the assistant, and the requests are gone. */
export function forgetAssistant(): void {
  assistant.queue = [];
  assistant.present = 0;
}

async function runMission(proposal: MissionProposal): Promise<Outcome> {
  pushUndo();
  app.waypoints = proposal.waypoints.map((w) => ({ ...w }));
  saveWaypoints();
  const done = {
    ok: true as const,
    result: { uploaded_waypoints: proposal.waypoints.length, takeoff_alt_m: proposal.takeoffAlt },
  };
  if (isSerialConnected()) {
    const res = await serialUploadMission(app.waypoints, proposal.takeoffAlt);
    return res.ok ? done : { ok: false, error: `The upload failed: ${res.error}` };
  }
  const mark = app.events[app.events.length - 1];
  dispatch('mission_upload', undefined, { waypoints: app.waypoints, takeoff_alt: proposal.takeoffAlt });
  const wait = UPLOAD_WAIT_MS + UPLOAD_WAIT_PER_WAYPOINT_MS * proposal.waypoints.length;
  const ack = await nextEvent(mark, ['mission_ack_ok', 'mission_ack_fail'], wait);
  if (ack?.event_type === 'mission_ack_ok') return done;
  return {
    ok: false,
    error: ack
      ? `The flight controller refused the mission: ${ack.text}`
      : 'No answer from the flight controller to the upload. It may still be going on: read the mission back before anything else.',
  };
}

const confirmed = (now: number, asked: number) => Math.abs(now - asked) <= Math.max(1e-6, Math.abs(asked) * 1e-6);

async function runParameters(proposal: ParameterProposal): Promise<Outcome> {
  for (const change of proposal.changes) dispatch('param_set', undefined, { name: change.name, value: change.to });
  const deadline = Date.now() + PARAM_WAIT_MS;
  let pending = proposal.changes;
  while (true) {
    const now = byName();
    pending = pending.filter((c) => !confirmed(now.get(c.name) ?? NaN, c.to));
    if (pending.length === 0 || Date.now() >= deadline) break;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  const now = byName();
  const values = Object.fromEntries(proposal.changes.map((c) => [c.name, now.get(c.name) ?? null]));
  if (pending.length === 0) return { ok: true, result: { values } };
  const names = pending.map((c) => c.name).join(', ');
  return { ok: false, error: `The flight controller did not confirm ${names}. Values now: ${JSON.stringify(values)}` };
}

/** Modes that answer the command. A QuadPlane may go on from RTL to QRTL at once, or near home
 * (Q_RTL_MODE: ArduPlane/mode_rtl.cpp:22 and :33, ModeReason::QRTL_INSTEAD_OF_RTL), and RTL is 11,
 * QRTL 21 (ArduPlane/mode.h:49 and :60, enum class Number). */
function answers(command: FlightCommand, mode: number): boolean {
  if (command === 'rtl' && vehicleKind() === 'plane' && mode === 21) return true;
  return mode === specialModes()[command];
}

async function runCommand(proposal: CommandProposal): Promise<Outcome> {
  const mode = specialModes()[proposal.command]!;
  const mark = app.events[app.events.length - 1];
  // As the page's own buttons send them: RTL through the rtl command, the others as a mode.
  if (proposal.command === 'rtl') dispatch('rtl');
  else dispatch('mode', mode);
  const deadline = Date.now() + COMMAND_WAIT_MS;
  while (Date.now() < deadline) {
    if (answers(proposal.command, app.drone.mode_id)) return { ok: true, result: { mode: app.drone.mode } };
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  const after = mark === undefined ? app.events : app.events.slice(app.events.lastIndexOf(mark) + 1);
  const refused = after.filter((e) => e.event_type === 'cmd_ack_fail').map((e) => e.text);
  return {
    ok: false,
    error:
      `The flight controller did not report the mode in ${COMMAND_WAIT_MS / 1000} s: it is in ${app.drone.mode}.` +
      (refused.length > 0 ? ` It answered: ${refused.join('; ')}` : ''),
  };
}

/**
 * The first event of these types that came after mark, the newest event when the wait began, or
 * null after ms. By the event itself, not its number: the backend numbers its events from 0 each
 * time it starts, and the page keeps those of before across a reconnect. Trimming takes the
 * oldest first, so when mark is gone, every event left came after it.
 */
function nextEvent(mark: DroneEvent | undefined, types: string[], ms: number): Promise<DroneEvent | null> {
  return new Promise((resolve) => {
    const started = Date.now();
    const timer = setInterval(() => {
      const after = mark === undefined ? app.events : app.events.slice(app.events.lastIndexOf(mark) + 1);
      const found = after.find((e) => types.includes(e.event_type));
      if (found || Date.now() - started >= ms) {
        clearInterval(timer);
        resolve(found ?? null);
      }
    }, 100);
  });
}
