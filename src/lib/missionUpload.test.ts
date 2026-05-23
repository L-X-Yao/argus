import { describe, it, expect } from 'vitest';
import { buildMissionItems, validateMissionWaypoints } from './missionUpload';
import type { Waypoint } from './types';

const baseWp = (over: Partial<Waypoint> = {}): Waypoint => ({
  lat: 30, lon: 120, alt: 50,
  drop: false, delay: 0, speed: 0,
  type: 'wp', loiter_param: 0,
  ...over,
});

describe('buildMissionItems', () => {
  it('produces HOME + TAKEOFF + WP + RTL for a single waypoint', () => {
    const items = buildMissionItems([baseWp()], 30);
    expect(items.length).toBe(4);
    expect(items[0].command).toBe(16);   // HOME (NAV_WAYPOINT, lat=lon=alt=0)
    expect(items[0].current).toBe(1);
    expect(items[0].x).toBe(0);
    expect(items[1].command).toBe(22);   // TAKEOFF
    expect(items[1].z).toBe(30);          // takeoff alt
    expect(items[2].command).toBe(16);   // WP
    expect(items[2].x).toBe(300000000);
    expect(items[2].y).toBe(1200000000);
    expect(items[3].command).toBe(20);   // RTL
  });

  it('inserts DO_CHANGE_SPEED before nav waypoint when speed > 0', () => {
    const items = buildMissionItems([baseWp({ speed: 12 })], 30);
    // [HOME, TAKEOFF, CHANGE_SPEED, NAV_WP, RTL]
    expect(items.length).toBe(5);
    expect(items[2].command).toBe(178);  // DO_CHANGE_SPEED
    expect(items[2].p1).toBe(1);          // groundspeed
    expect(items[2].p2).toBe(12);
    expect(items[3].command).toBe(16);
  });

  it('uses NAV_SPLINE_WAYPOINT cmd=82 for spline type', () => {
    const items = buildMissionItems([baseWp({ type: 'spline', delay: 5 })], 30);
    expect(items[2].command).toBe(82);
    expect(items[2].p1).toBe(5);  // delay (spline takes delay as p1)
  });

  it('uses LOITER_TURNS cmd=18 with loiter_param as p1', () => {
    const items = buildMissionItems([baseWp({ type: 'loiter_turns', loiter_param: 7 })], 30);
    expect(items[2].command).toBe(18);
    expect(items[2].p1).toBe(7);
  });

  it('uses LOITER_TIME cmd=19 with loiter_param as p1', () => {
    const items = buildMissionItems([baseWp({ type: 'loiter_time', loiter_param: 15 })], 30);
    expect(items[2].command).toBe(19);
    expect(items[2].p1).toBe(15);
  });

  it('inserts DO_SET_RELAY (181) after WP when drop=true', () => {
    const items = buildMissionItems([baseWp({ drop: true })], 30);
    // [HOME, TAKEOFF, WP, RELAY, RTL]
    expect(items.length).toBe(5);
    expect(items[3].command).toBe(181);
  });

  it('preserves WP order across multiple waypoints', () => {
    const items = buildMissionItems(
      [baseWp({ lat: 30, lon: 120 }), baseWp({ lat: 31, lon: 121 })],
      30,
    );
    // HOME + TAKEOFF + WP1 + WP2 + RTL
    expect(items.length).toBe(5);
    expect(items[2].x).toBe(300000000);
    expect(items[3].x).toBe(310000000);
  });

  it('NAV cmds use frame=3 (REL_ALT) and DO_* / RTL use frame=2 (MISSION)', () => {
    // Backend rule (send_mission_item_int): frame=3 only for cmd in
    // (16, 18, 19, 21, 22, 82). RTL (20) is NOT in that set — it gets frame=2.
    const items = buildMissionItems([baseWp({ speed: 5, drop: true })], 30);
    // HOME(16)=3, TAKEOFF(22)=3, CHG_SPEED(178)=2, WP(16)=3, RELAY(181)=2, RTL(20)=2
    expect(items[0].frame).toBe(3);
    expect(items[1].frame).toBe(3);
    expect(items[2].frame).toBe(2);   // DO_CHANGE_SPEED
    expect(items[3].frame).toBe(3);
    expect(items[4].frame).toBe(2);   // DO_SET_RELAY
    expect(items[5].frame).toBe(2);   // RTL
  });

  it('seq is contiguous from 0 to N-1', () => {
    const items = buildMissionItems(
      [baseWp({ speed: 3 }), baseWp({ drop: true })],
      30,
    );
    items.forEach((item, idx) => {
      expect(item.seq).toBe(idx);
    });
  });

  it('only seq 0 has current=1', () => {
    const items = buildMissionItems([baseWp(), baseWp({ lat: 31 })], 30);
    expect(items[0].current).toBe(1);
    items.slice(1).forEach((item) => expect(item.current).toBe(0));
  });

  it('handles attachments in the documented order', () => {
    const items = buildMissionItems([baseWp({
      cmd_servo: { num: 5, pwm: 1800 },
      cmd_roi: { lat: 32, lon: 122, alt: 100 },
      cmd_cam_trig: { dist: 50 },
      cmd_yaw: { deg: 90, dir: 1 },
    })], 30);
    // [HOME, TAKEOFF, WP, SERVO, ROI, CAM_TRIG, YAW, RTL]
    expect(items.length).toBe(8);
    expect(items[3].command).toBe(183);  // DO_SET_SERVO
    expect(items[3].p1).toBe(5);
    expect(items[3].p2).toBe(1800);
    expect(items[4].command).toBe(201);  // DO_SET_ROI
    expect(items[4].x).toBe(320000000);
    expect(items[5].command).toBe(206);  // DO_SET_CAM_TRIGG_DIST
    expect(items[6].command).toBe(115);  // CONDITION_YAW
    expect(items[6].p1).toBe(90);
  });
});

describe('validateMissionWaypoints', () => {
  it('rejects empty waypoint list', () => {
    const r = validateMissionWaypoints([]);
    expect(r.ok).toBe(false);
  });

  it('rejects > 500 waypoints', () => {
    const wps = Array.from({ length: 501 }, () => baseWp({ lat: 30, lon: 120 }));
    const r = validateMissionWaypoints(wps);
    expect(r.ok).toBe(false);
  });

  it('rejects coordinates very close to 0/0', () => {
    const r = validateMissionWaypoints([baseWp({ lat: 0.0001, lon: 120 })]);
    expect(r.ok).toBe(false);
  });

  it('rejects out-of-range latitude', () => {
    const r = validateMissionWaypoints([baseWp({ lat: 91, lon: 120 })]);
    expect(r.ok).toBe(false);
  });

  it('rejects out-of-range altitude', () => {
    const r = validateMissionWaypoints([baseWp({ alt: -1000 })]);
    expect(r.ok).toBe(false);
  });

  it('accepts a normal waypoint', () => {
    const r = validateMissionWaypoints([baseWp()]);
    expect(r.ok).toBe(true);
  });
});
