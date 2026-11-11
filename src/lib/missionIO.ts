import type { AltMode, RallyPoint, Waypoint } from './types';

// MAV_FRAME_GLOBAL_RELATIVE_ALT and its INT twin, the only altitudes Argus uploads. A file above
// sea level or above terrain cannot be turned into those without the home of the day, and read
// as they stand, 1900 m above sea level would fly 1900 m above home.
const RELATIVE_FRAMES = new Set([3, 6]);

export class AltitudeFrameError extends Error {}

/**
 * What a file or browser storage holds is not a mission until it has been checked. The map draws
 * these fields into HTML and the panels call number methods on them, so a field of the wrong
 * type is refused here and not found out there. A file is refused as a whole: a route with one
 * point left out is another route.
 */
export class MissionDataError extends Error {}

const WP_TYPES: ReadonlySet<string> = new Set(['wp', 'loiter_turns', 'loiter_time', 'spline']);
const ALT_MODES: ReadonlySet<string> = new Set(['relative', 'msl', 'terrain']);

type Fields = Record<string, unknown>;

function isFields(v: unknown): v is Fields {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** A finite number, from a number or from text that spells one. null for everything else. */
export function finiteNumber(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function required(v: unknown, field: string): number {
  const n = finiteNumber(v);
  if (n === null) throw new MissionDataError(field);
  return n;
}

/** A field that may be left out, or null: an emptied number box stores null. */
function optional(v: unknown, fallback: number, field: string): number {
  return v === undefined || v === null ? fallback : required(v, field);
}

function position(raw: Fields): { lat: number; lon: number } {
  const lat = required(raw.lat, 'lat');
  const lon = required(raw.lon, 'lon');
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) throw new MissionDataError('position');
  return { lat, lon };
}

/** The numbers of one attached command. A field left out stays out: the upload has the default. */
function command<K extends string>(raw: unknown, keys: readonly K[], field: string): Record<K, number> | undefined {
  if (raw === undefined || raw === null) return undefined;
  if (!isFields(raw)) throw new MissionDataError(field);
  const out = {} as Record<K, number>;
  for (const key of keys) {
    if (raw[key] !== undefined && raw[key] !== null) out[key] = required(raw[key], `${field}.${key}`);
  }
  return out;
}

function list(raw: unknown, field: string): Fields[] {
  if (!Array.isArray(raw)) throw new MissionDataError(field);
  return raw.map((item) => {
    if (!isFields(item)) throw new MissionDataError(field);
    return item;
  });
}

export function cleanWaypoints(raw: unknown, defaultAlt: number): Waypoint[] {
  return list(raw, 'waypoints').map((item) => {
    const type = item.type ?? 'wp';
    if (typeof type !== 'string' || !WP_TYPES.has(type)) throw new MissionDataError('type');
    // A drop opens a relay in flight: a value that is not plainly yes or no is not guessed at.
    if (item.drop !== undefined && item.drop !== null && typeof item.drop !== 'boolean') {
      throw new MissionDataError('drop');
    }
    const wp: Waypoint = {
      ...position(item),
      alt: optional(item.alt, defaultAlt, 'alt'),
      drop: item.drop === true,
      delay: optional(item.delay, 0, 'delay'),
      speed: optional(item.speed, 0, 'speed'),
      type: type as Waypoint['type'],
      loiter_param: optional(item.loiter_param, 0, 'loiter_param'),
    };
    if (typeof item.altMode === 'string' && ALT_MODES.has(item.altMode)) wp.altMode = item.altMode as AltMode;
    const servo = command(item.cmd_servo, ['num', 'pwm'], 'cmd_servo');
    if (servo) wp.cmd_servo = servo;
    const roi = command(item.cmd_roi, ['lat', 'lon', 'alt'], 'cmd_roi');
    if (roi) wp.cmd_roi = roi;
    const cam = command(item.cmd_cam_trig, ['dist'], 'cmd_cam_trig');
    if (cam) wp.cmd_cam_trig = cam;
    const yaw = command(item.cmd_yaw, ['deg', 'dir'], 'cmd_yaw');
    if (yaw) wp.cmd_yaw = yaw;
    const vtol = command(item.cmd_vtol, ['mode'], 'cmd_vtol');
    if (vtol) wp.cmd_vtol = vtol;
    return wp;
  });
}

export function cleanPositions(raw: unknown): { lat: number; lon: number }[] {
  return list(raw, 'positions').map(position);
}

export function cleanRallyPoints(raw: unknown, defaultAlt: number): RallyPoint[] {
  return list(raw, 'rally').map((item) => ({ ...position(item), alt: optional(item.alt, defaultAlt, 'alt') }));
}

export function parseQgcWaypoints(text: string): Waypoint[] {
  const wps: Waypoint[] = [];
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('QGC') || trimmed.startsWith('#')) continue;
    const cols = trimmed.split('\t');
    if (cols.length < 12) continue;
    // Row 0 is the home position in files from Mission Planner and QGroundControl
    // (Tools/autotest/Generic_Missions/CMAC-circuit.txt), not a place to fly to.
    if (parseInt(cols[0]) === 0) continue;
    const cmd = parseInt(cols[3]);
    if (cmd !== 16 && cmd !== 18 && cmd !== 19 && cmd !== 82) continue;
    if (!RELATIVE_FRAMES.has(parseInt(cols[2]))) throw new AltitudeFrameError();
    // Text that is not a number is refused: read as NaN it reached the map, which then drew
    // nothing at all.
    const at = position({ lat: cols[8], lon: cols[9] });
    if (Math.abs(at.lat) < 0.001) continue;
    const p1 = required(cols[4], 'param1');
    const type: Waypoint['type'] =
      cmd === 18 ? 'loiter_turns' : cmd === 19 ? 'loiter_time' : cmd === 82 ? 'spline' : 'wp';
    wps.push({
      ...at,
      alt: required(cols[10], 'alt'),
      drop: false,
      delay: cmd === 16 || cmd === 82 ? p1 : 0,
      speed: 0,
      type,
      loiter_param: cmd === 18 || cmd === 19 ? p1 : 0,
    });
  }
  return wps;
}

export function parseQgcPlan(text: string): Waypoint[] {
  const plan = JSON.parse(text);
  // A survey is one ComplexItem that holds its own list of simple items.
  const items = list(plan?.mission?.items ?? [], 'items').flatMap((item) => {
    if (item.type !== 'ComplexItem') return [item];
    const survey = item.TransectStyleComplexItem;
    return list(isFields(survey) ? (survey.Items ?? []) : [], 'items');
  });
  const wps: Waypoint[] = [];
  for (const item of items) {
    const cmd = item.command;
    if (cmd !== 16 && cmd !== 18 && cmd !== 19 && cmd !== 82) continue;
    if (!RELATIVE_FRAMES.has((item.frame ?? 3) as number)) throw new AltitudeFrameError();
    // QGroundControl writes null for a parameter the command does not use.
    const params = isFields(item.params) || Array.isArray(item.params) ? (item.params as Fields) : {};
    const at = position({ lat: params[4] ?? 0, lon: params[5] ?? 0 });
    if (Math.abs(at.lat) < 0.001) continue;
    const p1 = optional(params[0], 0, 'param1');
    const type: Waypoint['type'] =
      cmd === 18 ? 'loiter_turns' : cmd === 19 ? 'loiter_time' : cmd === 82 ? 'spline' : 'wp';
    wps.push({
      ...at,
      alt: optional(params[6], 30, 'alt'),
      drop: false,
      delay: cmd === 16 || cmd === 82 ? p1 : 0,
      speed: 0,
      type,
      loiter_param: cmd === 18 || cmd === 19 ? p1 : 0,
    });
  }
  return wps;
}

export function exportKml(waypoints: Waypoint[]): string {
  const coords = waypoints.map((w) => `${w.lon},${w.lat},${w.alt}`).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Argus Mission</name>
<Placemark><name>Route</name><LineString><coordinates>${coords}</coordinates></LineString></Placemark>
</Document></kml>`;
}

export function parseKmlCoords(text: string, defaultAlt: number): Waypoint[] {
  const doc = new DOMParser().parseFromString(text, 'text/xml');
  const coords: Waypoint[] = [];
  const els = doc.getElementsByTagName('coordinates');
  for (let i = 0; i < els.length; i++) {
    els[i]
      .textContent!.trim()
      .split(/\s+/)
      .forEach((c: string) => {
        const p = c.split(',');
        if (p.length >= 2) {
          const lon = parseFloat(p[0]),
            lat = parseFloat(p[1]),
            height = parseFloat(p[2]);
          const alt = Number.isFinite(height) && height !== 0 ? height : defaultAlt;
          // Not a number, and not on the globe either: 1e999 reads as Infinity.
          if (Math.abs(lat) > 0.001 && Math.abs(lon) > 0.001 && Math.abs(lat) <= 90 && Math.abs(lon) <= 180)
            coords.push({ lat, lon, alt, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 });
        }
      });
  }
  if (coords.length > 1 && Math.abs(coords[0].lat - coords[coords.length - 1].lat) < 0.00001) coords.pop();
  return coords;
}

export function segDist(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const dlat = (b.lat - a.lat) * 111320;
  const dlon = (b.lon - a.lon) * 111320 * Math.cos((a.lat * Math.PI) / 180);
  return Math.sqrt(dlat * dlat + dlon * dlon);
}

export function totalDist(waypoints: Waypoint[]): string {
  let d = 0;
  for (let i = 1; i < waypoints.length; i++) {
    d += segDist(waypoints[i - 1], waypoints[i]);
  }
  return d < 1000 ? d.toFixed(0) + 'm' : (d / 1000).toFixed(1) + 'km';
}

export function pointInPoly(lat: number, lon: number, poly: { lat: number; lon: number }[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    if (
      poly[i].lon > lon !== poly[j].lon > lon &&
      lat < ((poly[j].lat - poly[i].lat) * (lon - poly[i].lon)) / (poly[j].lon - poly[i].lon) + poly[i].lat
    ) {
      inside = !inside;
    }
  }
  return inside;
}
