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
import { app, pushUndo, saveWaypoints, addToast, showSlide, cancelSlide, slideState } from './stores.svelte';
import { paramState } from './paramStore.svelte';
import { cleanWaypoints, MissionDataError } from './missionIO';
import { validateMissionWaypoints } from './missionUpload';
import { dispatch, isSerialConnected, linkLossCount, modeRequestCount, serialUploadMission } from './transport';
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
  /** The newest event when it was asked for: a disarm after it ends the flight it was for. */
  mark: DroneEvent | undefined;
  /** The page's link drops when it was asked for: the WebSerial link notes none as an event. */
  linkLosses: number;
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
// After the flight controller has accepted the mode, how long to wait for a heartbeat to show it.
const ACCEPTED_WAIT_MS = 2500;
// MAV_CMD_DO_SET_MODE, as both links send a mode (backend send_set_mode, transport serialSendMode):
// ArduPilot libraries/GCS_MAVLink/GCS_Common.cpp:5741 routes it to handle_command_do_set_mode.
const DO_SET_MODE = 176;

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
          enqueue(proposal);
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
    // The name is in the page's language; the number is ArduPilot's, per vehicle.
    mode_number: d.mode_id,
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
  // As transport.dispatch refuses them: a proposal accepted on such a vehicle would wait for
  // an upload that was never sent, and report a silence instead of the reason.
  const ap = app.drone.autopilot;
  if (ap != null && ap !== 0 && ap !== 3) {
    return `Argus does not send commands to ${ap === 12 ? 'PX4' : `autopilot=${ap}`}.`;
  }
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

/** Events after mark, the newest event at some moment. By the event itself, as nextEvent does. */
function eventsAfter(mark: DroneEvent | undefined): DroneEvent[] {
  return mark === undefined ? app.events : app.events.slice(app.events.lastIndexOf(mark) + 1);
}

/** What ends the flight a command was asked for: a disarm, a link that dropped, or another
 * vehicle taken over (its armed state comes from the fleet list, so a switch can look like the
 * same flight). The page can miss the disarm itself (the link or its websocket was down:
 * ws_manager starts the cursor at the total, and the trim takes the oldest first), so a drop is
 * taken with it. */
const FLIGHT_ENDS = new Set(['disarmed', 'disconnected', 'link_lost', 'vehicle_switch']);

/** Why this flight command cannot be asked for or sent now, with the operator's toast, or null.
 * since: when it was asked for. A disarm or a link that dropped after that ended the flight it
 * was for, even if the vehicle is armed again. The toast is the text to show. */
function commandRefusal(
  command: FlightCommand,
  since?: { mark: DroneEvent | undefined; linkLosses: number },
): { error: string; toast: string } | null {
  if (!app.drone.connected) return { error: 'No vehicle is connected to Argus.', toast: t('err.noLink') };
  if (!app.drone.armed) {
    return {
      error: 'The vehicle is not armed: a flight command is for a vehicle that is.',
      toast: t('assistant.notArmed'),
    };
  }
  if (since) {
    // The mark anchors the flight. Gone from the list, what happened after it cannot be told:
    // the trim takes the oldest first, and an event older than the ones left may hide a disarm.
    if (since.mark !== undefined && app.events.lastIndexOf(since.mark) < 0) {
      return {
        error: 'The page no longer holds the event this was asked at: ask again.',
        toast: t('assistant.otherFlight'),
      };
    }
    if (linkLossCount() !== since.linkLosses || eventsAfter(since.mark).some((e) => FLIGHT_ENDS.has(e.event_type))) {
      return {
        error: 'The vehicle has disarmed, or the link to it dropped, since it was asked for: it was for that flight.',
        toast: t('assistant.otherFlight'),
      };
    }
  }
  // Mirrors transport.dispatch, which refuses the same vehicles: a command sent nowhere would
  // otherwise wait its 10 s and report a silence that is not the flight controller's.
  const ap = app.drone.autopilot;
  if (ap != null && ap !== 0 && ap !== 3) {
    const fcName = ap === 12 ? 'PX4' : `autopilot=${ap}`;
    return {
      error: `Argus does not send commands to ${fcName}.`,
      toast: t('conn.unsupportedFc').replace('{fc}', fcName),
    };
  }
  if (specialModes()[command] === null) {
    return { error: `This ${vehicleKind()} has ${NO_MODE[command]} in Argus.`, toast: t('assistant.noMode') };
  }
  return null;
}

function proposeCommand(id: string, args: Fields): CommandProposal | { error: string } {
  const command = args.command;
  if (typeof command !== 'string' || !COMMANDS.includes(command)) return { error: 'command: rtl, hold or land.' };
  const refused = commandRefusal(command as FlightCommand);
  if (refused) return { error: refused.error };
  const mark = app.events[app.events.length - 1];
  return {
    id,
    kind: 'propose_command',
    command: command as FlightCommand,
    reason: reasonOf(args),
    mark,
    linkLosses: linkLossCount(),
  };
}

/** In the order asked for, but a flight command before a mission or parameters: those wait for a
 * vehicle that is not armed, and the command for one that is. */
function enqueue(proposal: Proposal): void {
  if (proposal.kind !== 'propose_command') {
    assistant.queue.push(proposal);
    return;
  }
  const at = assistant.queue.findIndex((p) => p.kind !== 'propose_command');
  if (at < 0) assistant.queue.push(proposal);
  else assistant.queue.splice(at, 0, proposal);
}

// ---- the operator's decision ------------------------------------------------------------

function remove(id: string): void {
  assistant.queue = assistant.queue.filter((p) => p.id !== id);
  closeSlideOf(id);
}

/** The slide open for a flight command: its proposal, and what the slide runs. */
let sliding: { id: string; confirm: () => void } | null = null;

/** Its proposal left the queue (taken back, the assistant gone): a slide finished now would send
 * nothing, and must not seem to. Only the slide opened here, and only while it is still open. */
function closeSlideOf(id?: string): void {
  if (!sliding || (id !== undefined && sliding.id !== id)) return;
  if (slideState.visible && slideState._onConfirm === sliding.confirm) {
    cancelSlide();
    addToast(t('assistant.withdrawnNow'), 'warn', 5000);
  }
  sliding = null;
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
    const confirm = () => {
      sliding = null;
      // The slide takes seconds: by its end the vehicle may have landed. A proposal taken back
      // meanwhile has closed the slide (closeSlideOf).
      if (!waiting(proposal.id) || assistant.running || refuseCommand(proposal)) return;
      void run(proposal);
    };
    sliding = { id: proposal.id, confirm };
    showSlide(t(text), color, confirm);
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
  const refused = commandRefusal(proposal.command, { mark: proposal.mark, linkLosses: proposal.linkLosses });
  if (!refused) return false;
  finish(proposal, { ok: false, error: refused.error, ending: 'refused' });
  addToast(refused.toast, 'error', 5000);
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
  closeSlideOf();
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
 * (Q_RTL_MODE: ArduPlane/mode_rtl.cpp:23 and :33, ModeReason::QRTL_INSTEAD_OF_RTL), and RTL is 11,
 * QRTL 21 (ArduPlane/mode.h:49 and :60, enum class Number). */
function answers(command: FlightCommand, mode: number): boolean {
  if (command === 'rtl' && vehicleKind() === 'plane' && mode === 21) return true;
  return mode === specialModes()[command];
}

/**
 * Sent, and done once the vehicle reports the mode, or once the flight controller has accepted it:
 * a vehicle may go on from that mode before a heartbeat shows it, as a plane's RTL does to AUTO
 * for its landing (RTL_AUTOLAND: ArduPlane/mode_rtl.cpp:106-114), a QuadPlane's to QLAND
 * (mode_rtl.cpp:15-18), and a submarine at the surface from SURFACE (ArduSub/mode_surface.cpp:40).
 * Failed when the flight controller refuses it, or says nothing in 10 s.
 */
async function runCommand(proposal: CommandProposal): Promise<Outcome> {
  const mode = specialModes()[proposal.command]!;
  const already = answers(proposal.command, app.drone.mode_id);
  const mark = app.events[app.events.length - 1];
  // As the page's own buttons send them: RTL through the rtl command, the others as a mode.
  if (proposal.command === 'rtl') dispatch('rtl');
  else dispatch('mode', mode);
  // A COMMAND_ACK carries no request id: an acknowledgement answers the page's latest mode
  // command. One the operator sends meanwhile is not this one's, and its refusal is not this
  // command's answer. A command sent just before, whose answer had not come yet, still cannot
  // be told apart: MAVLink has nothing to match on.
  const requests = modeRequestCount();
  const now = (accepted: boolean): Outcome => ({
    ok: true,
    result: {
      mode: app.drone.mode,
      mode_number: app.drone.mode_id,
      ...(already ? { already_in_mode: true } : {}),
      ...(accepted ? { accepted: true } : {}),
    },
  });
  const deadline = Date.now() + COMMAND_WAIT_MS;
  let acceptedAt = 0;
  while (Date.now() < deadline) {
    if (answers(proposal.command, app.drone.mode_id) && (!already || acceptedAt)) return now(acceptedAt > 0);
    // The mark evicted (the list trims the oldest first), events after it cannot be told apart:
    // as in commandRefusal, stop reading them and let the mode the vehicle reports decide.
    const mine = modeRequestCount() === requests && (mark === undefined || app.events.lastIndexOf(mark) >= 0);
    const ack = mine ? eventsAfter(mark).find((e) => e.cmd === DO_SET_MODE) : undefined;
    if (ack?.event_type === 'cmd_ack_fail') {
      return { ok: false, error: `The flight controller answered: ${ack.text}. It is in ${app.drone.mode}.` };
    }
    if (ack?.event_type === 'cmd_ack_ok' && !acceptedAt) acceptedAt = Date.now();
    if (acceptedAt && Date.now() - acceptedAt >= ACCEPTED_WAIT_MS) return now(true);
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  if (already) return now(false);
  return {
    ok: false,
    error: `No answer from the flight controller in ${COMMAND_WAIT_MS / 1000} s: it is in ${app.drone.mode}.`,
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
      const found = eventsAfter(mark).find((e) => types.includes(e.event_type));
      if (found || Date.now() - started >= ms) {
        clearInterval(timer);
        resolve(found ?? null);
      }
    }, 100);
  });
}
