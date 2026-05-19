import type { Waypoint } from './types';

interface SurveyConfig {
  angle: number;
  spacing: number;
  alt: number;
  overshoot: number;
}

interface Point { lat: number; lon: number; }

const M_PER_DEG_LAT = 111320;
function mPerDegLon(lat: number): number {
  return 111320 * Math.cos(lat * Math.PI / 180);
}

function toLocal(p: Point, origin: Point): [number, number] {
  return [
    (p.lon - origin.lon) * mPerDegLon(origin.lat),
    (p.lat - origin.lat) * M_PER_DEG_LAT,
  ];
}

function toGeo(x: number, y: number, origin: Point): Point {
  return {
    lat: origin.lat + y / M_PER_DEG_LAT,
    lon: origin.lon + x / mPerDegLon(origin.lat),
  };
}

function rotatePoint(x: number, y: number, angle: number): [number, number] {
  const c = Math.cos(angle), s = Math.sin(angle);
  return [x * c - y * s, x * s + y * c];
}

function lineSegIntersect(
  ax: number, ay: number, bx: number, by: number,
  cx: number, cy: number, dx: number, dy: number,
): [number, number] | null {
  const denom = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx);
  if (Math.abs(denom) < 1e-10) return null;
  const t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / denom;
  const u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / denom;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return [ax + t * (bx - ax), ay + t * (by - ay)];
}

export function generateSurveyGrid(polygon: Point[], config: SurveyConfig): Waypoint[] {
  if (polygon.length < 3) return [];
  const origin = polygon[0];
  const angleRad = config.angle * Math.PI / 180;

  const local = polygon.map(p => toLocal(p, origin));
  const rotated = local.map(([x, y]) => rotatePoint(x, y, -angleRad));

  let minY = Infinity, maxY = -Infinity;
  for (const [, y] of rotated) {
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }

  const lines: [number, number][][] = [];
  const spacing = config.spacing;
  const overshoot = config.overshoot;

  for (let y = minY + spacing / 2; y < maxY; y += spacing) {
    const intersections: number[] = [];
    for (let i = 0; i < rotated.length; i++) {
      const j = (i + 1) % rotated.length;
      const [x1, y1] = rotated[i];
      const [x2, y2] = rotated[j];
      if ((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) {
        const x = x1 + (y - y1) / (y2 - y1) * (x2 - x1);
        intersections.push(x);
      }
    }
    intersections.sort((a, b) => a - b);
    for (let k = 0; k + 1 < intersections.length; k += 2) {
      lines.push([
        rotatePoint(intersections[k] - overshoot, y, angleRad),
        rotatePoint(intersections[k + 1] + overshoot, y, angleRad),
      ]);
    }
  }

  const waypoints: Waypoint[] = [];
  let reverse = false;
  for (const line of lines) {
    const pts = reverse ? [line[1], line[0]] : [line[0], line[1]];
    for (const [x, y] of pts) {
      const geo = toGeo(x, y, origin);
      waypoints.push({ lat: geo.lat, lon: geo.lon, alt: config.alt, drop: false, delay: 0, speed: 0, type: 'wp' as const, loiter_param: 0 });
    }
    reverse = !reverse;
  }
  return waypoints;
}

export function polygonArea(polygon: Point[]): number {
  if (polygon.length < 3) return 0;
  const origin = polygon[0];
  const local = polygon.map(p => toLocal(p, origin));
  let area = 0;
  for (let i = 0; i < local.length; i++) {
    const j = (i + 1) % local.length;
    area += local[i][0] * local[j][1];
    area -= local[j][0] * local[i][1];
  }
  return Math.abs(area) / 2;
}
