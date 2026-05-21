/**
 * Mission import/export in multiple formats:
 * - .waypoints (Mission Planner)
 * - .plan (QGroundControl JSON)
 * - .gpx (GPS Exchange Format)
 */

import type { Waypoint } from './types';

/* ── Mission Planner .waypoints format ── */

export function exportWaypoints(wps: Waypoint[], homeAlt: number = 0): string {
  const lines = ['QGC WPL 110'];
  lines.push(`0\t1\t0\t16\t0\t0\t0\t0\t0\t0\t${homeAlt}\t1`);
  for (let i = 0; i < wps.length; i++) {
    const w = wps[i];
    const cmd = w.type === 'loiter_turns' ? 18 : w.type === 'loiter_time' ? 19 : w.type === 'spline' ? 82 : 16;
    const p1 = w.delay || 0;
    const p3 = w.loiter_param || 0;
    lines.push(`${i + 1}\t0\t3\t${cmd}\t${p1}\t0\t${p3}\t0\t${w.lat.toFixed(7)}\t${w.lon.toFixed(7)}\t${w.alt.toFixed(1)}\t1`);
  }
  return lines.join('\n') + '\n';
}

export function importWaypoints(text: string): Waypoint[] {
  const wps: Waypoint[] = [];
  for (const line of text.split('\n')) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 12 || parts[0] === 'QGC') continue;
    const seq = parseInt(parts[0]);
    if (seq === 0) continue;
    const cmd = parseInt(parts[3]);
    const lat = parseFloat(parts[8]);
    const lon = parseFloat(parts[9]);
    const alt = parseFloat(parts[10]);
    if (Math.abs(lat) < 0.001 && Math.abs(lon) < 0.001) continue;
    const type = cmd === 18 ? 'loiter_turns' as const :
                 cmd === 19 ? 'loiter_time' as const :
                 cmd === 82 ? 'spline' as const : 'wp' as const;
    wps.push({ lat, lon, alt, drop: false, delay: parseFloat(parts[4]) || 0, speed: 0, type, loiter_param: parseFloat(parts[6]) || 0 });
  }
  return wps;
}

/* ── QGC .plan JSON format ── */

export function exportQgcPlan(wps: Waypoint[], homeAlt: number = 0): string {
  const items = wps.map((w, i) => ({
    autoContinue: true,
    command: w.type === 'loiter_turns' ? 18 : w.type === 'loiter_time' ? 19 : 16,
    doJumpId: i + 1,
    frame: 3,
    params: [w.delay || 0, 0, w.loiter_param || 0, 0, w.lat, w.lon, w.alt],
    type: 'SimpleItem',
  }));

  const plan = {
    fileType: 'Plan',
    geoFence: { circles: [], polygons: [], version: 2 },
    groundStation: 'Argus GCS',
    mission: {
      cruiseSpeed: 15,
      firmwareType: 3,
      hoverSpeed: 5,
      items,
      plannedHomePosition: [wps[0]?.lat || 0, wps[0]?.lon || 0, homeAlt],
      vehicleType: 2,
      version: 2,
    },
    rallyPoints: { points: [], version: 2 },
    version: 1,
  };
  return JSON.stringify(plan, null, 2);
}

export function importQgcPlan(text: string): Waypoint[] {
  try {
    const plan = JSON.parse(text);
    const items = plan?.mission?.items || [];
    return items
      .filter((it: any) => it.type === 'SimpleItem' && it.params?.length >= 7)
      .map((it: any) => {
        const [p1, , p3, , lat, lon, alt] = it.params;
        const cmd = it.command || 16;
        const type = cmd === 18 ? 'loiter_turns' as const :
                     cmd === 19 ? 'loiter_time' as const : 'wp' as const;
        return { lat, lon, alt, drop: false, delay: p1 || 0, speed: 0, type, loiter_param: p3 || 0 } as Waypoint;
      });
  } catch { return []; }
}

/* ── GPX format ── */

export function exportGpx(wps: Waypoint[], name: string = 'Argus Mission'): string {
  const rtePts = wps.map((w, i) =>
    `    <rtept lat="${w.lat.toFixed(7)}" lon="${w.lon.toFixed(7)}"><ele>${w.alt.toFixed(1)}</ele><name>WP${i + 1}</name></rtept>`
  ).join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Argus GCS">
  <rte>
    <name>${name}</name>
${rtePts}
  </rte>
</gpx>`;
}

export function importGpx(text: string): Waypoint[] {
  const wps: Waypoint[] = [];
  const doc = new DOMParser().parseFromString(text, 'text/xml');
  const pts = doc.querySelectorAll('rtept, wpt, trkpt');
  for (const pt of pts) {
    const lat = parseFloat(pt.getAttribute('lat') || '0');
    const lon = parseFloat(pt.getAttribute('lon') || '0');
    const eleEl = pt.querySelector('ele');
    const alt = eleEl ? parseFloat(eleEl.textContent || '30') : 30;
    if (Math.abs(lat) > 0.001) {
      wps.push({ lat, lon, alt, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 });
    }
  }
  return wps;
}

/**
 * Auto-detect file format and import.
 */
export function autoImport(text: string, filename: string): Waypoint[] {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.plan')) return importQgcPlan(text);
  if (lower.endsWith('.gpx')) return importGpx(text);
  if (lower.endsWith('.waypoints') || text.startsWith('QGC WPL')) return importWaypoints(text);
  if (text.trim().startsWith('{')) return importQgcPlan(text);
  if (text.trim().startsWith('<?xml')) {
    if (text.includes('<gpx')) return importGpx(text);
  }
  return importWaypoints(text);
}
