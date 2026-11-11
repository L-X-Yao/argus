/**
 * Terrain elevation service.
 *
 * Fetches ground elevation data from the backend SRTM API and provides
 * helpers for terrain-following mission planning.
 */

import { apiUrl } from './backend';

const elevationCache = new Map<string, number>();

// Long enough for the backend to fetch a large tile of ground data over a slow line.
const REQUEST_TIMEOUT_MS = 120000;

// One at a time, like the tiles in sw.js. A request can wait a long time for its file, and each
// edit of a route sends another: over a slow line they took all six connections the browser
// gives this host, and the next panel to open never got its code.
let lastRequest: Promise<unknown> = Promise.resolve();

async function request(url: string): Promise<(number | null)[]> {
  const res = await fetch(url, { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (!res.ok) throw new Error(`Terrain API ${res.status}`);
  const data: { elevations: (number | null)[] } = await res.json();
  return data.elevations;
}

function inTurn(url: string): Promise<(number | null)[]> {
  const turn = lastRequest.then(() => request(url));
  lastRequest = turn.catch(() => undefined);
  return turn;
}

// The backend answers null where it has no data. Reading that as 0 would be sea level, and
// terrain following would then send a route into the ground: callers show "no data" instead.
// The same for an answer that is short of a point or holds something that is no number: a
// waypoint's altitude is worked out from each of these, and NaN would go up with the mission.
function known(elevations: unknown, count: number): number[] {
  const complete =
    Array.isArray(elevations) &&
    elevations.length === count &&
    elevations.every((e) => typeof e === 'number' && Number.isFinite(e));
  if (!complete) throw new Error('No terrain data');
  return elevations as number[];
}

/**
 * Get ground elevation (MSL) for a single point.
 * Results are cached to 4 decimal places (~11 m resolution).
 */
export async function getElevation(lat: number, lon: number): Promise<number> {
  const key = `${lat.toFixed(4)},${lon.toFixed(4)}`;
  if (elevationCache.has(key)) return elevationCache.get(key)!;

  const url = apiUrl(`/api/terrain/elevation?points=${lat.toFixed(6)},${lon.toFixed(6)}`);
  const [elev] = known(await inTurn(url), 1);
  elevationCache.set(key, elev);
  return elev;
}

/**
 * Batch-fetch ground elevations for an array of points.
 * API expects: /api/terrain/elevation?points=lat1,lon1;lat2,lon2;...
 * Returns:     { elevations: [elev1, elev2, ...] }
 */
export async function getElevationProfile(points: { lat: number; lon: number }[]): Promise<number[]> {
  if (points.length === 0) return [];

  // Check cache first — return early if every point is cached
  const keys = points.map((p) => `${p.lat.toFixed(4)},${p.lon.toFixed(4)}`);
  const allCached = keys.every((k) => elevationCache.has(k));
  if (allCached) return keys.map((k) => elevationCache.get(k)!);

  // Build query string (semicolon-separated lat,lon pairs)
  const pairs = points.map((p) => `${p.lat.toFixed(6)},${p.lon.toFixed(6)}`).join(';');
  const url = apiUrl(`/api/terrain/elevation?points=${pairs}`);
  const elevations = known(await inTurn(url), points.length);

  // Populate cache
  for (let i = 0; i < points.length; i++) {
    elevationCache.set(keys[i], elevations[i]);
  }

  return elevations;
}

/**
 * The ground under each point, in metres above home. Mission items use frame=3
 * (GLOBAL_RELATIVE_ALT) so the FC reads alt as metres above home, while SRTM gives
 * metres above sea level: the two only compare once the home ground is taken off.
 *
 * @param home  If unknown, the first point's ground serves as the reference.
 */
export async function groundAboveHome(
  points: { lat: number; lon: number }[],
  home?: { lat: number; lon: number } | null,
): Promise<number[]> {
  const elevations = await getElevationProfile(points);
  const reference = home && (home.lat !== 0 || home.lon !== 0) ? await getElevation(home.lat, home.lon) : elevations[0];
  return elevations.map((e) => e - reference);
}

/**
 * Adjust waypoint altitudes so that every point maintains a constant AGL
 * clearance over the terrain: alt = (groundMSL - homeMSL) + targetAGL.
 *
 * @param homeLatLon  See groundAboveHome.
 * @returns A new array (original waypoints are not mutated).
 */
export async function adjustWaypointsForTerrain(
  waypoints: { lat: number; lon: number; alt: number }[],
  targetAGL: number,
  homeLatLon?: { lat: number; lon: number } | null,
): Promise<{ lat: number; lon: number; alt: number }[]> {
  // A copy: the answer can take a while, and a waypoint added to the caller's list meanwhile
  // would have no ground to go with it, and come back with an altitude of NaN.
  const route = waypoints.map((wp) => ({ ...wp }));
  const ground = await groundAboveHome(route, homeLatLon);
  return route.map((wp, i) => ({
    ...wp,
    alt: Math.round(ground[i] + targetAGL),
  }));
}

/** The same for two lists of waypoints over the same ground, measured from the same home. */
export function routeKey(waypoints: { lat: number; lon: number }[], home?: { lat: number; lon: number }): string {
  const points = home ? [...waypoints, home] : waypoints;
  return points.map((w) => `${w.lat.toFixed(5)},${w.lon.toFixed(5)}`).join(';');
}

/**
 * Interpolate additional points along a route for a denser terrain profile.
 * Returns the original waypoint positions plus evenly-spaced intermediate
 * points (roughly one every `stepMeters`).
 */
export function interpolateRoute(
  waypoints: { lat: number; lon: number }[],
  stepMeters: number = 50,
): { lat: number; lon: number; wpIndex: number }[] {
  if (waypoints.length < 2) {
    return waypoints.map((p, i) => ({ lat: p.lat, lon: p.lon, wpIndex: i }));
  }

  const result: { lat: number; lon: number; wpIndex: number }[] = [];

  for (let i = 0; i < waypoints.length - 1; i++) {
    const a = waypoints[i];
    const b = waypoints[i + 1];
    const dlat = (b.lat - a.lat) * 111320;
    const dlon = (b.lon - a.lon) * 111320 * Math.cos((a.lat * Math.PI) / 180);
    const segLen = Math.sqrt(dlat * dlat + dlon * dlon);
    const steps = Math.max(1, Math.ceil(segLen / stepMeters));

    for (let s = 0; s < steps; s++) {
      const frac = s / steps;
      result.push({
        lat: a.lat + (b.lat - a.lat) * frac,
        lon: a.lon + (b.lon - a.lon) * frac,
        wpIndex: s === 0 ? i : -1,
      });
    }
  }
  // Final waypoint
  const last = waypoints[waypoints.length - 1];
  result.push({ lat: last.lat, lon: last.lon, wpIndex: waypoints.length - 1 });

  return result;
}
