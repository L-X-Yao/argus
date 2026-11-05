/**
 * WebSerial telemetry handlers: decoded MAVLink messages → app.drone store.
 *
 * This is the serial-mode twin of the backend path (mavlink_handlers.py →
 * get_state() → ws push → updateState). Extracted from ConnectionForm.svelte
 * so tests/test_contract_dualstack_state_parity.py can drive the REAL mapping
 * code: the same FC frame must land in app.drone with the same values on both
 * transports, and that harness is the only thing keeping these two mappings
 * from drifting apart — update BOTH sides (and the parity fixture) when
 * adding a field.
 */
import type { MessageHandlers } from './mavlink';
import { app, addEvent, addToast } from './stores.svelte';
import { t, i18nState } from './i18n.svelte';
import { getModeButtons, getModeName, vehicleType } from './modeStore';
import { saveFlightRecord } from './flightDb';
import { serialWpIndex } from './transport';

// Mirrors backend/constants.py FIX_NAMES and FIX_NAMES_EN.
const FIX_NAMES: Record<'en' | 'zh', Record<number, string>> = {
  en: { 0: 'No Fix', 1: 'No Fix', 2: '2D', 3: '3D', 4: 'DGPS', 5: 'RTK Float', 6: 'RTK Fixed' },
  zh: { 0: '无定位', 1: '无定位', 2: '2D', 3: '3D', 4: '差分', 5: 'RTK浮动', 6: 'RTK固定' },
};

// Mirrors the labels in backend DroneLink._get_vehicle_info.
const VEHICLE_LABELS: Record<'en' | 'zh', Record<VehicleType, string>> = {
  en: { copter: 'Multirotor', plane: 'Fixed Wing', rover: 'Rover', sub: 'Sub' },
  zh: { copter: '多旋翼', plane: '固定翼', rover: '地面车', sub: '水下机器人' },
};

const uiLocale = (): 'en' | 'zh' => (i18nState.locale === 'zh' ? 'zh' : 'en');

// Mirrors backend/mavlink_handlers.py _CMD_NAMES_* and _ACK_RESULTS_*.
const ACK_COMMANDS: Record<number, string> = {
  22: 'ack.cmd.takeoff',
  176: 'ack.cmd.mode',
  181: 'ack.cmd.relay',
  241: 'ack.cmd.calibration',
  300: 'ack.cmd.missionStart',
  400: 'ack.cmd.armDisarm',
  410: 'ack.cmd.guided',
  42424: 'ack.cmd.compassCal',
  42425: 'ack.cmd.compassAccept',
  42426: 'ack.cmd.compassCancel',
};
const ACK_RESULTS: Record<number, string> = {
  0: 'ack.result.accepted',
  1: 'ack.result.temporarilyRejected',
  2: 'ack.result.denied',
  3: 'ack.result.unsupported',
  4: 'ack.result.failed',
  7: 'ack.result.commandLongOnly',
  8: 'ack.result.commandIntOnly',
};
const ACK_QUIET_ON_SUCCESS = new Set([241, 42424, 42425, 42426]);

const METERS_PER_DEG = 111320;
const ADSB_MAX_AGE_S = 60;

function metersBetween(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = (lat1 - lat2) * METERS_PER_DEG;
  const dLon = (lon1 - lon2) * METERS_PER_DEG * Math.cos((lat1 * Math.PI) / 180);
  return Math.hypot(dLat, dLon);
}

const event = (text: string, event_type: string) =>
  addEvent({ type: 'event', time: new Date().toLocaleTimeString(), text, event_type });

// Flight bookkeeping, twin of what the backend keeps on DroneLink. It outlives
// buildSerialHandlers on purpose: a USB link that drops mid-flight and comes back is the
// same flight, and arming events must not fire again for it.
function newSession() {
  return {
    homeSet: false,
    armed: false,
    armedAt: 0,
    maxAlt: 0,
    maxSpeed: 0,
    totalDist: 0,
    prevPos: null as [number, number] | null,
    batHistory: [] as [number, number][],
    batStart: -1,
    adsb: new Map<number, Record<string, number | string>>(),
  };
}

let session = newSession();

/**
 * A connection is starting. Back after a USB drop it is the same flight; anything else
 * may be a different vehicle, so its parameters go too, as in the 'connected' case of ws.ts.
 */
export function beginSerialSession(): void {
  if (app.serialLinkLost) return;
  resetSerialSession();
  clearParams();
}

/** The user ended the session: the next connection may be a different vehicle. */
export function resetSerialSession(): void {
  session = newSession();
  app.serialLinkLost = false;
  const {
    vtol_state,
    flight_summary,
    home_lat,
    home_lon,
    dist_home,
    wp,
    wp_idx,
    flight_time,
    bat_time,
    servo,
    cells,
    adsb,
    prearm,
    fw_version,
    fw_git,
    board_id,
    wind_dir,
    wind_speed,
    terrain_alt,
    gimbal_pitch,
    gimbal_yaw,
  } = defaultState;
  Object.assign(app.drone, {
    vtol_state,
    flight_summary,
    home_lat,
    home_lon,
    dist_home,
    wp,
    wp_idx,
    flight_time,
    bat_time,
    servo,
    cells,
    adsb,
    prearm,
    fw_version,
    fw_git,
    board_id,
    wind_dir,
    wind_speed,
    terrain_alt,
    gimbal_pitch,
    gimbal_yaw,
  });
}

export function buildSerialHandlers(): Partial<MessageHandlers> {
  // One-shot per connection, like the backend's _unsupported_fc_warned
  // (reset on connect) — a mixed AP+GCS link must not toast every second.
  let warnedUnsupported = false;
  // Per-session flight bookkeeping, twin of what the backend keeps on DroneLink.
  let homeSet = false;
  let wasArmed = false;
  let armedAt = 0;
  let maxAlt = 0;
  let maxSpeed = 0;
  let totalDist = 0;
  let prevPos: [number, number] | null = null;
  let batHistory: [number, number][] = [];
  let batStart = -1;
  const adsb = new Map<number, Record<string, number | string>>();

  const onArmedChange = (armed: boolean) => {
    event(t(armed ? 'toast.armed' : 'toast.disarmed'), armed ? 'armed' : 'disarmed');
    addToast(t(armed ? 'toast.armed' : 'toast.disarmed'), armed ? 'warn' : 'success', armed ? 5000 : 4000);
    if (armed) {
      app.drone.flight_summary = null;
      armedAt = Date.now();
      maxAlt = maxSpeed = totalDist = 0;
      prevPos = null;
      batHistory = [];
      batStart = app.drone.remaining;
      return;
    }
    const remaining = app.drone.remaining;
    const summary = {
      duration: armedAt ? Math.trunc((Date.now() - armedAt) / 1000) : 0,
      max_alt: Math.round(maxAlt * 10) / 10,
      max_speed: Math.round(maxSpeed * 10) / 10,
      total_dist: Math.round(totalDist),
      bat_used: batStart >= 0 && remaining >= 0 ? batStart - remaining : -1,
    };
    app.drone.flight_summary = summary;
    app.drone.bat_time = -1;
    saveFlightRecord({
      date: new Date().toISOString(),
      duration: summary.duration,
      maxAlt: summary.max_alt,
      maxSpeed: summary.max_speed,
      totalDist: summary.total_dist,
      batUsed: summary.bat_used,
      vtype: app.drone.vtype,
      fw: app.drone.fw_version,
      eventCount: app.events?.length ?? 0,
    });
  };

  return {
    onHeartbeat: (msg) => {
      if (!app.drone.connected) {
        app.drone.connected = true;
        app.drone.prearm = [];
        addToast(t('conn.serialConnected'), 'success');
      }
      app.drone.vtype_raw = msg.type;
      app.drone.vtype = VEHICLE_LABELS[uiLocale()][vehicleType(msg.type)];
      const armed = (msg.baseMode & 128) !== 0;
      if (armed !== wasArmed) onArmedChange(armed);
      wasArmed = armed;
      app.drone.armed = armed;
      app.drone.flight_time = armed && armedAt ? Math.trunc((Date.now() - armedAt) / 1000) : 0;
      app.drone.mode_id = msg.customMode;
      // Localized mode NAME — the WS path pushes get_state()'s "mode"
      // (backend _get_vehicle_info: vtype → table → locale) and StatusBar
      // reads it; until 2026-07-14 serial mode left it blank forever.
      app.drone.mode = getModeName(vehicleType(msg.type), msg.customMode, uiLocale());
      // The mode buttons render from this list; the WS path gets it from
      // get_state(), so serial mode had none and modes could not be changed.
      app.drone.mode_btns = getModeButtons(vehicleType(msg.type), uiLocale());
      // Autopilot latch mirrors backend handle_heartbeat
      // (mavlink_handlers.py:49-51): ignore 0 (GENERIC/uninit) and 8
      // (INVALID — GCS/relay heartbeats), latch anything else. transport.ts
      // dispatch() refuses FC-bound serial commands while a non-ArduPilot
      // value (not 0/3) is latched, mirroring commands.execute().
      if (msg.autopilot > 0 && msg.autopilot !== 8 && msg.autopilot !== app.drone.autopilot) {
        app.drone.autopilot = msg.autopilot;
        if (msg.autopilot !== 3 && !warnedUnsupported) {
          warnedUnsupported = true;
          const name = msg.autopilot === 12 ? 'PX4' : `autopilot=${msg.autopilot}`;
          addToast(t('conn.unsupportedFc').replace('{fc}', name), 'error', 10000);
        }
      }
    },
    onGlobalPositionInt: (msg) => {
      app.drone.lat = msg.lat;
      app.drone.lon = msg.lon;
      app.drone.alt_msl = msg.altMsl;
      app.drone.alt_rel = msg.altRel;
      // NED vz is positive-down; the UI (and backend get_state) shows
      // positive-up climb rate.
      app.drone.vz = -msg.vz;
      app.drone.hdg = msg.hdg;
      // Home comes from the first real fix until HOME_POSITION says otherwise,
      // as in backend handle_global_position_int. The threshold skips the (0,0)
      // the FC reports before it has a position.
      if (!homeSet && (Math.abs(msg.lat) > 0.001 || Math.abs(msg.lon) > 0.001)) {
        homeSet = true;
        app.drone.home_lat = msg.lat;
        app.drone.home_lon = msg.lon;
        event(t('evt.homeSet').replace('{lat}', msg.lat.toFixed(5)).replace('{lon}', msg.lon.toFixed(5)), 'home_set');
      }
      if (homeSet) {
        app.drone.dist_home = metersBetween(msg.lat, msg.lon, app.drone.home_lat, app.drone.home_lon);
      }
      if (app.drone.armed) {
        maxAlt = Math.max(maxAlt, msg.altRel);
        maxSpeed = Math.max(maxSpeed, app.drone.gs ?? 0);
        if (prevPos) totalDist += metersBetween(msg.lat, msg.lon, prevPos[0], prevPos[1]);
        prevPos = [msg.lat, msg.lon];
      }
    },
    onExtendedSysState: (msg) => {
      // Twin of backend handle_extended_sys_state, which says what this is for.
      app.drone.vtol_state = msg.vtolState;
    },
    onAttitude: (msg) => {
      app.drone.roll = msg.roll;
      app.drone.pitch = msg.pitch;
      // Backend handle_attitude normalizes yaw to 0..360 for the compass
      // rose; ATTITUDE.yaw is ±π. Mirror it (state-parity finding 2026-07-14:
      // a west-facing vehicle read -90° on the WebSerial path, 270° on WS).
      app.drone.yaw = msg.yaw < 0 ? msg.yaw + 360 : msg.yaw;
    },
    onSysStatus: (msg) => {
      app.drone.voltage = msg.voltage;
      app.drone.current = msg.current;
      app.drone.remaining = msg.remaining;
      // Time left from the last two minutes of drain, as in backend handle_sys_status.
      if (msg.remaining >= 0 && app.drone.armed) {
        const now = Date.now() / 1000;
        batHistory.push([now, msg.remaining]);
        batHistory = batHistory.filter(([at]) => now - at < 120);
        const elapsed = now - batHistory[0][0];
        const used = batHistory[0][1] - msg.remaining;
        if (elapsed > 10 && used > 0) app.drone.bat_time = Math.trunc(msg.remaining / (used / elapsed));
      }
    },
    onGpsRawInt: (msg) => {
      app.drone.gps_fix_raw = msg.fixType;
      app.drone.gps_fix = FIX_NAMES[uiLocale()][msg.fixType] ?? '?';
      app.drone.gps_sats = msg.sats;
    },
    onEkfStatus: (msg) => {
      // Unmapped until 2026-11-05: flags stayed 0 in serial mode, so the
      // preflight EKF row reported OK however unhealthy the EKF was.
      app.drone.ekf_flags = msg.flags;
      app.drone.ekf_vel = msg.velVar;
      app.drone.ekf_pos_h = msg.posHVar;
      app.drone.ekf_pos_v = msg.posVVar;
      app.drone.ekf_compass = msg.compassVar;
    },
    onVfrHud: (msg) => {
      // gs source differs by design: the backend derives it from
      // GLOBAL_POSITION_INT vx/vy (state.py hypot), serial mode uses the
      // FC's own VFR_HUD.groundspeed — same quantity, so it is excluded
      // from the state-parity compare rather than force-aligned.
      app.drone.gs = msg.groundspeed;
      // airspeed/climb/throttle were dropped here until the 2026-07-14
      // state-parity pass — the serial-mode PFD showed 0 for all three
      // while the WS path (get_state) has always pushed them.
      app.drone.airspeed = msg.airspeed;
      app.drone.climb = msg.climb;
      app.drone.throttle = msg.throttle;
    },
    onRcChannels: (msg) => {
      // Backend handle_rc_channels stores 16 channels (mavlink_handlers.py:349)
      // and every RC widget is written against that WS shape — slice the
      // 18-channel wire message to match.
      app.drone.rc = msg.channels.slice(0, 16);
      app.drone.rc_rssi = msg.rssi;
    },
    onVibration: (msg) => {
      app.drone.vibe = [msg.x, msg.y, msg.z];
      app.drone.vibe_clip = [msg.clip0, msg.clip1, msg.clip2];
    },
    onRawImu: (msg) => {
      // RAW_SENSORS stream is already requested at connect — this keeps
      // the compass-cal sphere fed on the WebSerial path too.
      app.drone.mag = [msg.xmag, msg.ymag, msg.zmag];
    },
    onHomePosition: (msg) => {
      homeSet = true;
      app.drone.home_lat = msg.lat;
      app.drone.home_lon = msg.lon;
    },
    onServoOutput: (msg) => {
      app.drone.servo = msg.outputs;
    },
    onMissionCurrent: (msg) => {
      app.drone.wp = msg.seq;
      app.drone.wp_idx = serialWpIndex(msg.seq);
    },
    onMissionItemReached: (msg) => {
      event(t('evt.wpReached').replace('{n}', String(msg.seq)), 'wp_reached');
    },
    onWind: (msg) => {
      app.drone.wind_dir = ((msg.direction % 360) + 360) % 360;
      app.drone.wind_speed = msg.speed;
    },
    onTerrainReport: (msg) => {
      app.drone.terrain_alt = msg.terrainHeight;
    },
    onBatteryStatus: (msg) => {
      app.drone.cells = msg.cells;
    },
    onAutopilotVersion: (msg) => {
      const v = msg.flightSwVersion;
      app.drone.fw_version = `v${(v >>> 24) & 0xff}.${(v >>> 16) & 0xff}.${(v >>> 8) & 0xff}`;
      app.drone.fw_git = msg.gitHash;
      app.drone.board_id = msg.boardVersion;
      event(t('evt.fwInfo').replace('{v}', app.drone.fw_version).replace('{git}', msg.gitHash), 'fw_info');
    },
    onMountStatus: (msg) => {
      app.drone.gimbal_pitch = msg.pitch;
      app.drone.gimbal_yaw = msg.yaw;
    },
    onGimbalDeviceAttitudeStatus: (msg, frame) => {
      if (frame.payloadLen < 20) return;
      app.drone.gimbal_pitch = msg.pitch;
      app.drone.gimbal_yaw = msg.yaw;
    },
    onAdsbVehicle: (msg) => {
      const now = Date.now() / 1000;
      adsb.set(msg.icao, {
        icao: msg.icao,
        lat: msg.lat,
        lon: msg.lon,
        alt: Math.round(msg.alt),
        hdg: Math.round(msg.hdg),
        speed: Math.round(msg.speed * 10) / 10,
        vs: Math.round(msg.vs * 10) / 10,
        callsign: msg.callsign.trim(),
        t: now,
      });
      if (adsb.size > 200) {
        const oldest = [...adsb.values()].reduce((a, b) => ((a.t as number) < (b.t as number) ? a : b));
        adsb.delete(oldest.icao as number);
      }
      app.drone.adsb = [...adsb.values()].filter(
        (a) => now - (a.t as number) < ADSB_MAX_AGE_S,
      ) as typeof app.drone.adsb;
    },
    onCommandAck: (msg, frame) => {
      // Twin of backend handle_command_ack. ArduPilot answers every COMMAND_LONG
      // (libraries/GCS_MAVLink/GCS_Common.cpp:5397) and a refused arm answers
      // MAV_RESULT_FAILED (:5204). Unhandled until now, so on this link a refused
      // command gave no sign at all.
      if (frame.payloadLen < 2) return;
      // MAV_RESULT_IN_PROGRESS reports progress and the final result follows
      // (GCS_Common.cpp:1463 send_in_progress, :1468 conclude).
      if (msg.result === 5) return;
      if (msg.result === 0 && ACK_QUIET_ON_SUCCESS.has(msg.command)) return;
      const cmdKey = ACK_COMMANDS[msg.command];
      const resultKey = ACK_RESULTS[msg.result];
      const text = t('ack.text')
        .replace('{cmd}', cmdKey ? t(cmdKey) : String(msg.command))
        .replace('{result}', resultKey ? t(resultKey) : t('ack.result.unknown').replace('{n}', String(msg.result)));
      const ok = msg.result === 0;
      addEvent({
        type: 'event',
        time: new Date().toLocaleTimeString(),
        text,
        event_type: ok ? 'cmd_ack_ok' : 'cmd_ack_fail',
      });
      if (!ok) addToast(text, 'error', 5000);
    },
    onStatusText: (msg) => {
      // PreArm checks repeat about every 5 s until fixed: one entry per cause,
      // as in backend handle_statustext.
      if (msg.text.startsWith('PreArm:') || msg.text.startsWith('Arm:')) {
        const cause = msg.text.slice(msg.text.indexOf(':') + 1).trim();
        const seen = app.drone.prearm ?? [];
        if (seen.includes(cause)) return;
        const next = [...seen, cause];
        app.drone.prearm = next.length > 20 ? next.slice(-10) : next;
      }
      // Use addEvent so the 200-entry cap in stores.svelte applies; a direct
      // push would let serial-mode events grow unbounded. (Intentionally NOT
      // state-parity-tested: the backend runs statustext filtering + locale.)
      addEvent({ type: 'event', time: new Date().toLocaleTimeString(), text: msg.text, event_type: 'statustext' });
    },
  };
}
