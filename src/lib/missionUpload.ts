/**
 * Mission-item builder shared between WebSocket and WebSerial upload paths.
 *
 * Mirrors backend/commands/_mission.py:_upload_mission so that an upload
 * issued over WebSerial produces an identical mission layout on the FC as
 * one issued via the Python backend.
 *
 * Mission layout:
 *   seq 0  HOME (cmd 16, lat=lon=alt=0)
 *   seq 1  TAKEOFF (cmd 22, alt=takeoff_alt)
 *   seq N+ optional attachments per waypoint, in order:
 *            DO_CHANGE_SPEED (cmd 178, when speed > 0)
 *            NAV waypoint (cmd 16/18/19/82 by type)
 *            DO_SET_SERVO (cmd 183) if cmd_servo
 *            DO_SET_ROI (cmd 201) if cmd_roi
 *            DO_SET_CAM_TRIGG_DIST (cmd 206) if cmd_cam_trig
 *            CONDITION_YAW (cmd 115) if cmd_yaw
 *            DO_VTOL_TRANSITION (cmd 3000) if cmd_vtol
 *            DO_SET_RELAY (cmd 181) if drop
 *   last   RTL (cmd 20)
 */

import type { Waypoint } from './types';

export interface MissionItem {
  seq: number;
  command: number;  // MAV_CMD value
  frame: number;    // MAV_FRAME (3 = GLOBAL_RELATIVE_ALT_INT, 2 = MISSION)
  current: number;  // 1 on seq 0, else 0
  autocontinue: number;
  p1: number;
  p2: number;
  p3: number;
  p4: number;
  x: number;  // lat scaled by 1e7 (int32)
  y: number;  // lon scaled by 1e7 (int32)
  z: number;  // alt (float)
}

const NAV_FRAME_CMDS = new Set([16, 18, 19, 21, 22, 82]);

function navCmdFor(wpType: Waypoint['type']): { cmd: number; p1Source: 'loiter_param' | 'delay' } {
  if (wpType === 'loiter_turns') return { cmd: 18, p1Source: 'loiter_param' };
  if (wpType === 'loiter_time')  return { cmd: 19, p1Source: 'loiter_param' };
  if (wpType === 'spline')       return { cmd: 82, p1Source: 'delay' };
  return { cmd: 16, p1Source: 'delay' };
}

export function buildMissionItems(waypoints: Waypoint[], takeoffAlt: number): MissionItem[] {
  const items: MissionItem[] = [];
  const push = (cmd: number, p1: number, p2: number, p3: number, p4: number, lat: number, lon: number, alt: number) => {
    const seq = items.length;
    const frame = NAV_FRAME_CMDS.has(cmd) ? 3 : 2;
    items.push({
      seq, command: cmd, frame,
      current: seq === 0 ? 1 : 0,
      autocontinue: 1,
      p1, p2, p3, p4,
      // Match backend's int(float(lat) * 1e7) (truncate toward zero) for
      // byte-exact parity with backend/commands/_helpers.py:send_mission_item_int.
      x: Math.trunc(lat * 1e7), y: Math.trunc(lon * 1e7), z: alt,
    });
  };

  push(16, 0, 0, 0, 0, 0, 0, 0);                  // HOME
  push(22, 0, 0, 0, 0, 0, 0, takeoffAlt);         // TAKEOFF

  for (const wp of waypoints) {
    const speed = Number(wp.speed) || 0;
    if (speed > 0) {
      push(178, 1, speed, 0, 0, 0, 0, 0);          // DO_CHANGE_SPEED
    }
    const { cmd: navCmd, p1Source } = navCmdFor(wp.type);
    const navP1 = p1Source === 'loiter_param'
      ? Number(wp.loiter_param ?? 3)
      : Number(wp.delay ?? 0);
    push(navCmd, navP1, 0, 0, 0, wp.lat, wp.lon, wp.alt ?? takeoffAlt);

    if (wp.cmd_servo) {
      push(183, Number(wp.cmd_servo.num ?? 1), Number(wp.cmd_servo.pwm ?? 1500), 0, 0, 0, 0, 0);
    }
    if (wp.cmd_roi) {
      push(201, 0, 0, 0, 0, Number(wp.cmd_roi.lat ?? 0), Number(wp.cmd_roi.lon ?? 0), Number(wp.cmd_roi.alt ?? 0));
    }
    if (wp.cmd_cam_trig) {
      push(206, Number(wp.cmd_cam_trig.dist ?? 0), 0, 0, 0, 0, 0, 0);
    }
    if (wp.cmd_yaw) {
      push(115, Number(wp.cmd_yaw.deg ?? 0), 0, Number(wp.cmd_yaw.dir ?? 1), 0, 0, 0, 0);
    }
    if (wp.cmd_vtol) {
      push(3000, Number(wp.cmd_vtol.mode ?? 4), 0, 0, 0, 0, 0, 0);
    }
    if (wp.drop) {
      push(181, 0, 0, 0, 0, 0, 0, 0);              // DO_SET_RELAY (relay 0 ON)
    }
  }

  push(20, 0, 0, 0, 0, 0, 0, 0);                   // RTL

  return items;
}

export function validateMissionWaypoints(waypoints: Waypoint[]): { ok: true } | { ok: false; error: string } {
  if (waypoints.length === 0) return { ok: false, error: 'No waypoints' };
  if (waypoints.length > 500) return { ok: false, error: 'Mission too large (max 500 WP)' };
  for (const wp of waypoints) {
    const lat = Number(wp.lat), lon = Number(wp.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return { ok: false, error: 'Invalid coordinates' };
    if (Math.abs(lat) < 0.001) return { ok: false, error: 'Invalid coordinates' };
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return { ok: false, error: 'Invalid coordinates' };
    const alt = Number(wp.alt ?? 0);
    if (!Number.isFinite(alt) || alt < -500 || alt > 100000) return { ok: false, error: 'Invalid coordinates' };
  }
  return { ok: true };
}
