export interface DroneState {
  type: 'state';
  connected: boolean;
  frames: number;
  mode: string;
  mode_id: number;
  armed: boolean;
  roll: number;
  pitch: number;
  yaw: number;
  lat: number;
  lon: number;
  alt_rel: number;
  alt_msl: number;
  gs: number;
  vz: number;
  hdg: number;
  dist_home: number;
  flight_time: number;
  voltage: number;
  current: number;
  remaining: number;
  gps_fix: string;
  gps_sats: number;
  wp: number;
  vtype: string;
  vtype_raw: number;
  mode_btns: [number, string][];
  link_age: number;
  bat_time: number;
  home_lat: number;
  home_lon: number;
  parse_errors: number;
  flight_summary: FlightSummary | null;
  log_active: boolean;
}

export interface FlightSummary {
  duration: number;
  max_alt: number;
  max_speed: number;
  total_dist: number;
  bat_used: number;
}

export interface DroneEvent {
  type: 'event';
  time: string;
  text: string;
}

export interface ConnectResult {
  type: 'connect_result';
  ok: boolean;
  error: string;
}

export interface Waypoint {
  lat: number;
  lon: number;
  alt: number;
  drop: boolean;
  delay: number;
}

export type WSMessage = DroneState | DroneEvent | ConnectResult;

export const defaultState: DroneState = {
  type: 'state',
  connected: false, frames: 0,
  mode: '---', mode_id: 0, armed: false,
  roll: 0, pitch: 0, yaw: 0,
  lat: 0, lon: 0, alt_rel: 0, alt_msl: 0,
  gs: 0, vz: 0, hdg: 0, dist_home: 0, flight_time: 0,
  voltage: 0, current: 0, remaining: -1,
  gps_fix: '---', gps_sats: 0, wp: 0,
  vtype: '', vtype_raw: 0, mode_btns: [],
  link_age: -1, bat_time: -1,
  home_lat: 0, home_lon: 0, parse_errors: 0,
  flight_summary: null, log_active: false,
};
