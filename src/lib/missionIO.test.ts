import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  parseQgcWaypoints,
  parseQgcPlan,
  AltitudeFrameError,
  MissionDataError,
  cleanWaypoints,
  cleanPositions,
  cleanRallyPoints,
  finiteNumber,
  exportKml,
  parseKmlCoords,
  segDist,
  totalDist,
  pointInPoly,
} from './missionIO';

describe('parseQgcWaypoints', () => {
  it('parses valid waypoints', () => {
    const text = `QGC WPL 110
0\t1\t0\t16\t0\t0\t0\t0\t34.258\t108.942\t100\t1
1\t0\t3\t16\t0\t0\t0\t0\t34.259\t108.943\t50\t1
2\t0\t3\t82\t0\t0\t0\t0\t34.260\t108.944\t60\t1`;
    const wps = parseQgcWaypoints(text);
    expect(wps).toHaveLength(2);
    expect(wps[0].lat).toBeCloseTo(34.259);
    expect(wps[1].type).toBe('spline');
  });

  it('skips header and non-nav commands', () => {
    const text = `QGC WPL 110
0\t1\t0\t16\t0\t0\t0\t0\t0\t0\t0\t1
1\t0\t3\t178\t0\t5\t0\t0\t0\t0\t0\t1`;
    const wps = parseQgcWaypoints(text);
    expect(wps).toHaveLength(0);
  });
});

describe('parseQgcPlan', () => {
  it('parses plan JSON', () => {
    const plan = {
      mission: {
        items: [
          { command: 22, params: [0, 0, 0, 0, 0, 0, 30] },
          { command: 16, params: [0, 0, 0, 0, 34.26, 108.94, 50] },
          { command: 82, params: [0, 0, 0, 0, 34.27, 108.95, 60] },
        ],
      },
    };
    const wps = parseQgcPlan(JSON.stringify(plan));
    expect(wps).toHaveLength(2);
    expect(wps[0].alt).toBe(50);
    expect(wps[1].type).toBe('spline');
  });
});

// What a file can hold in place of a number. The map writes these fields into HTML.
const MARKUP = '<img src=x onerror="window.__argus_xss=1">';

describe('parseQgcWaypoints with a file that is not what it says', () => {
  const row = (cols: Record<number, string>) => {
    const base = ['1', '0', '3', '16', '0', '0', '0', '0', '34.259', '108.943', '50', '1'];
    for (const [i, v] of Object.entries(cols)) base[Number(i)] = v;
    return 'QGC WPL 110\n' + base.join('\t');
  };

  it.each([
    ['latitude', 8],
    ['longitude', 9],
    ['altitude', 10],
    ['hold time', 4],
  ])('refuses text for the %s', (_name, col) => {
    expect(() => parseQgcWaypoints(row({ [col]: 'abc' }))).toThrow(MissionDataError);
  });

  it('refuses a number that is not finite, and a position off the globe', () => {
    expect(() => parseQgcWaypoints(row({ 10: '1e999' }))).toThrow(MissionDataError);
    expect(() => parseQgcWaypoints(row({ 8: '95' }))).toThrow(MissionDataError);
  });

  it('reads a file with Windows line ends', () => {
    const wps = parseQgcWaypoints(row({}).replace(/\n/g, '\r\n') + '\r\n');
    expect(wps).toEqual([
      { lat: 34.259, lon: 108.943, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 },
    ]);
  });
});

describe('parseQgcPlan with a file that is not what it says', () => {
  const plan = (params: unknown[], extra: Record<string, unknown> = {}) =>
    JSON.stringify({ mission: { items: [{ command: 16, frame: 3, params, ...extra }] } });

  it.each([
    ['hold time', [MARKUP, 0, 0, null, 34.26, 108.94, 50]],
    ['latitude', [0, 0, 0, null, MARKUP, 108.94, 50]],
    ['longitude', [0, 0, 0, null, 34.26, MARKUP, 50]],
    ['altitude', [0, 0, 0, null, 34.26, 108.94, MARKUP]],
    ['altitude as an object', [0, 0, 0, null, 34.26, 108.94, { toString: MARKUP }]],
  ])('refuses markup as the %s', (_name, params) => {
    expect(() => parseQgcPlan(plan(params))).toThrow(MissionDataError);
  });

  it('refuses a position off the globe', () => {
    expect(() => parseQgcPlan(plan([0, 0, 0, null, 134.26, 108.94, 50]))).toThrow(MissionDataError);
  });

  it('reads null as the parameter QGroundControl did not use', () => {
    const wps = parseQgcPlan(plan([null, null, null, null, 34.26, 108.94, null]));
    expect(wps).toEqual([
      { lat: 34.26, lon: 108.94, alt: 30, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 },
    ]);
  });

  it('gives numbers for numbers written as text', () => {
    const [wp] = parseQgcPlan(plan(['5', 0, 0, null, '34.26', '108.94', '50']));
    expect(wp).toMatchObject({ lat: 34.26, lon: 108.94, alt: 50, delay: 5 });
  });

  it.each([
    ['items that are not a list', { mission: { items: 'x' } }],
    ['an item that is not an object', { mission: { items: [7] } }],
    [
      'a survey whose items are not a list',
      { mission: { items: [{ type: 'ComplexItem', TransectStyleComplexItem: { Items: 7 } }] } },
    ],
  ])('refuses %s', (_name, body) => {
    expect(() => parseQgcPlan(JSON.stringify(body))).toThrow(MissionDataError);
  });

  it('takes a file with no mission as an empty one', () => {
    expect(parseQgcPlan('{}')).toEqual([]);
    expect(parseQgcPlan('null')).toEqual([]);
  });
});

describe('cleanWaypoints', () => {
  const saved = {
    lat: 34.25,
    lon: 108.94,
    alt: 50,
    drop: true,
    delay: 3,
    speed: 7,
    type: 'loiter_time',
    loiter_param: 20,
    cmd_servo: { num: 9, pwm: 1900 },
    cmd_roi: { lat: 34.3, lon: 108.9, alt: 10 },
    cmd_cam_trig: { dist: 25 },
    cmd_yaw: { deg: 90, dir: -1 },
    cmd_vtol: { mode: 4 },
  };

  it('keeps a mission as Argus saved it, field for field', () => {
    expect(cleanWaypoints(JSON.parse(JSON.stringify([saved, saved])), 30)).toEqual([saved, saved]);
  });

  it('fills in what a file may leave out', () => {
    expect(cleanWaypoints([{ lat: 1, lon: 2 }], 45)).toEqual([
      { lat: 1, lon: 2, alt: 45, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 },
    ]);
  });

  it('reads the null of an emptied number box as left out', () => {
    const [wp] = cleanWaypoints([{ lat: 1, lon: 2, alt: null, delay: null, speed: null, loiter_param: null }], 45);
    expect(wp).toMatchObject({ alt: 45, delay: 0, speed: 0, loiter_param: 0 });
    expect(cleanWaypoints([{ lat: 1, lon: 2, cmd_servo: { num: null, pwm: 1500 } }], 45)[0].cmd_servo).toEqual({
      pwm: 1500,
    });
  });

  it('gives numbers for numbers written as text', () => {
    const [wp] = cleanWaypoints([{ lat: '34.25', lon: ' 108.94 ', alt: '50', delay: '3' }], 30);
    expect(wp).toMatchObject({ lat: 34.25, lon: 108.94, alt: 50, delay: 3 });
    expect(typeof wp.alt).toBe('number');
  });

  it.each(['lat', 'lon', 'alt', 'delay', 'speed', 'loiter_param'])('refuses markup in %s', (field) => {
    expect(() => cleanWaypoints([{ ...saved, [field]: MARKUP }], 30)).toThrow(MissionDataError);
  });

  it.each([
    ['cmd_servo', { num: MARKUP, pwm: 1500 }],
    ['cmd_roi', { lat: 1, lon: 2, alt: MARKUP }],
    ['cmd_cam_trig', MARKUP],
    ['cmd_yaw', [90, 1]],
    ['cmd_vtol', { mode: {} }],
  ])('refuses a %s that is not numbers', (field, value) => {
    expect(() => cleanWaypoints([{ ...saved, [field]: value }], 30)).toThrow(MissionDataError);
  });

  it.each([
    ['a list that is not one', { 0: saved, length: 1 }],
    ['text', MARKUP],
    ['nothing', undefined],
    ['an entry that is not an object', [saved, 7]],
    ['an entry that is a list', [[34.25, 108.94]]],
    ['an entry that is null', [null]],
    ['a kind of waypoint it does not know', [{ ...saved, type: 'land' }]],
    ['a kind that is not text', [{ ...saved, type: 3 }]],
    ['a latitude past the pole', [{ ...saved, lat: 90.01 }]],
    ['a longitude past the date line', [{ ...saved, lon: -180.5 }]],
    ['a number that is not finite', [{ ...saved, alt: Infinity }]],
    ['an empty text for a number', [{ ...saved, alt: ' ' }]],
    ['a true or false for a number', [{ ...saved, alt: true }]],
    ['a drop that is not yes or no', [{ ...saved, drop: 'false' }]],
    ['a drop given as a number', [{ ...saved, drop: 1 }]],
  ])('refuses %s', (_name, raw) => {
    expect(() => cleanWaypoints(raw, 30)).toThrow(MissionDataError);
  });

  it('refuses the whole list for one bad point', () => {
    expect(() => cleanWaypoints([saved, { ...saved, lat: 'north' }, saved], 30)).toThrow(MissionDataError);
  });

  it('carries nothing over that it does not know', () => {
    const raw = JSON.parse(`[{"lat":1,"lon":2,"onload":"x","__proto__":{"polluted":1},"altMode":"${'<b>'}"}]`);
    const [wp] = cleanWaypoints(raw, 30);
    expect(Object.keys(wp).sort()).toEqual(['alt', 'delay', 'drop', 'lat', 'loiter_param', 'lon', 'speed', 'type']);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });

  it('keeps an altitude mode it knows', () => {
    expect(cleanWaypoints([{ lat: 1, lon: 2, altMode: 'terrain' }], 30)[0].altMode).toBe('terrain');
  });
});

describe('cleanPositions and cleanRallyPoints', () => {
  it('keep points and nothing else', () => {
    expect(cleanPositions([{ lat: '1.5', lon: 2, alt: 9, name: MARKUP }])).toEqual([{ lat: 1.5, lon: 2 }]);
    expect(
      cleanRallyPoints(
        [
          { lat: 1, lon: 2 },
          { lat: 3, lon: 4, alt: '80' },
        ],
        60,
      ),
    ).toEqual([
      { lat: 1, lon: 2, alt: 60 },
      { lat: 3, lon: 4, alt: 80 },
    ]);
  });

  it('refuse what is not a point', () => {
    expect(() => cleanPositions([{ lat: 1 }])).toThrow(MissionDataError);
    expect(() => cleanPositions({ lat: 1, lon: 2 })).toThrow(MissionDataError);
    expect(() => cleanRallyPoints([{ lat: 1, lon: 2, alt: MARKUP }], 60)).toThrow(MissionDataError);
    expect(() => cleanRallyPoints([{ lat: 91, lon: 2 }], 60)).toThrow(MissionDataError);
  });
});

describe('finiteNumber', () => {
  it.each([
    [5, 5],
    [-0.5, -0.5],
    ['12', 12],
    [' 1e3 ', 1000],
    [0, 0],
  ])('reads %j as %j', (value, n) => {
    expect(finiteNumber(value)).toBe(n);
  });

  it.each([NaN, Infinity, -Infinity, '', '  ', '12m', 'NaN', 'Infinity', null, undefined, true, false, [], [5], {}])(
    'reads %j as no number',
    (value) => {
      expect(finiteNumber(value)).toBeNull();
    },
  );
});

describe('exportKml', () => {
  it('generates valid KML', () => {
    const wps = [
      { lat: 34.25, lon: 108.94, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp' as const, loiter_param: 0 },
      { lat: 34.26, lon: 108.95, alt: 60, drop: false, delay: 0, speed: 0, type: 'wp' as const, loiter_param: 0 },
    ];
    const kml = exportKml(wps);
    expect(kml).toContain('<?xml');
    expect(kml).toContain('108.94,34.25,50');
    expect(kml).toContain('108.95,34.26,60');
  });
});

describe('parseKmlCoords', () => {
  beforeEach(() => {
    // Mock DOMParser for node environment
    const mockDOMParser = class {
      parseFromString(text: string, _type: string) {
        // Minimal XML parser for test KML docs
        const coordsMatches = [...text.matchAll(/<coordinates>([\s\S]*?)<\/coordinates>/g)];
        const elements: { textContent: string }[] = coordsMatches.map((m) => ({
          textContent: m[1],
        }));
        return {
          getElementsByTagName: (tag: string) => {
            if (tag === 'coordinates') return elements;
            return [];
          },
        };
      }
    };
    vi.stubGlobal('DOMParser', mockDOMParser);
  });

  it('parses KML with valid coordinates', () => {
    const kml = `<?xml version="1.0"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><LineString><coordinates>108.942,34.258,50
108.943,34.259,60</coordinates></LineString></Placemark>
</Document></kml>`;
    const wps = parseKmlCoords(kml, 30);
    expect(wps).toHaveLength(2);
    expect(wps[0].lat).toBeCloseTo(34.258);
    expect(wps[0].lon).toBeCloseTo(108.942);
    expect(wps[0].alt).toBe(50);
    expect(wps[1].alt).toBe(60);
    expect(wps[0].type).toBe('wp');
  });

  it('uses defaultAlt when altitude is missing', () => {
    const kml = `<kml><Document><Placemark><LineString>
<coordinates>108.942,34.258</coordinates>
</LineString></Placemark></Document></kml>`;
    const wps = parseKmlCoords(kml, 75);
    expect(wps).toHaveLength(1);
    expect(wps[0].alt).toBe(75);
  });

  it('skips a point that is not on the globe', () => {
    const kml = `<kml><Document><Placemark><LineString>
<coordinates>108.942,34.258,50 1e999,34.2,50 108.9,1e999,50 108.9,500,50 108.944,34.26,1e999</coordinates>
</LineString></Placemark></Document></kml>`;
    const wps = parseKmlCoords(kml, 75);
    expect(wps.map((w) => [w.lat, w.lon, w.alt])).toEqual([
      [34.258, 108.942, 50],
      [34.26, 108.944, 75],
    ]);
  });

  it('skips coordinates near zero lat/lon', () => {
    const kml = `<kml><Document><Placemark><LineString>
<coordinates>0.0001,0.0001,50
108.943,34.259,60</coordinates>
</LineString></Placemark></Document></kml>`;
    const wps = parseKmlCoords(kml, 30);
    expect(wps).toHaveLength(1);
    expect(wps[0].lat).toBeCloseTo(34.259);
  });

  it('removes duplicate closing point in closed polygon', () => {
    const kml = `<kml><Document><Placemark><LineString>
<coordinates>108.942,34.258,50
108.943,34.259,50
108.944,34.260,50
108.942,34.258,50</coordinates>
</LineString></Placemark></Document></kml>`;
    const wps = parseKmlCoords(kml, 30);
    expect(wps).toHaveLength(3); // last point removed (duplicate of first)
  });

  it('returns empty for KML with no coordinates element', () => {
    const kml = `<kml><Document><Placemark><name>Test</name></Placemark></Document></kml>`;
    const wps = parseKmlCoords(kml, 30);
    expect(wps).toHaveLength(0);
  });

  it('handles multiple coordinate elements', () => {
    const kml = `<kml><Document>
<Placemark><LineString><coordinates>108.942,34.258,50</coordinates></LineString></Placemark>
<Placemark><LineString><coordinates>108.943,34.259,60</coordinates></LineString></Placemark>
</Document></kml>`;
    const wps = parseKmlCoords(kml, 30);
    expect(wps).toHaveLength(2);
  });

  it('skips entries with fewer than 2 comma-separated values', () => {
    const kml = `<kml><Document><Placemark><LineString>
<coordinates>108.942
108.943,34.259,60</coordinates>
</LineString></Placemark></Document></kml>`;
    const wps = parseKmlCoords(kml, 30);
    expect(wps).toHaveLength(1);
    expect(wps[0].lon).toBeCloseTo(108.943);
  });
});

describe('segDist', () => {
  it('computes distance between two points', () => {
    const d = segDist({ lat: 0, lon: 0 }, { lat: 0, lon: 1 });
    expect(d).toBeGreaterThan(100000);
    expect(d).toBeLessThan(120000);
  });

  it('returns 0 for same point', () => {
    expect(segDist({ lat: 34, lon: 108 }, { lat: 34, lon: 108 })).toBe(0);
  });
});

describe('totalDist', () => {
  it('formats distance in meters', () => {
    const wps = [
      { lat: 34.258, lon: 108.942, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp' as const, loiter_param: 0 },
      { lat: 34.259, lon: 108.942, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp' as const, loiter_param: 0 },
    ];
    const d = totalDist(wps);
    expect(d).toMatch(/^\d+m$/);
  });

  it('formats distance in km for long routes', () => {
    const wps = [
      { lat: 34.0, lon: 108.0, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp' as const, loiter_param: 0 },
      { lat: 35.0, lon: 109.0, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp' as const, loiter_param: 0 },
    ];
    const d = totalDist(wps);
    expect(d).toMatch(/km$/);
  });
});

describe('pointInPoly', () => {
  const square = [
    { lat: 0, lon: 0 },
    { lat: 0, lon: 10 },
    { lat: 10, lon: 10 },
    { lat: 10, lon: 0 },
  ];

  it('returns true for point inside', () => {
    expect(pointInPoly(5, 5, square)).toBe(true);
  });

  it('returns false for point outside', () => {
    expect(pointInPoly(15, 5, square)).toBe(false);
  });

  it('returns false for empty polygon', () => {
    expect(pointInPoly(5, 5, [])).toBe(false);
  });
});

describe('files from other ground stations', () => {
  it('takes row 0 of a .waypoints file for home, not for a waypoint', () => {
    const file = [
      'QGC WPL 110',
      '0\t1\t0\t16\t0\t0\t0\t0\t-35.363\t149.165\t584\t1',
      '1\t0\t3\t22\t0\t0\t0\t0\t0\t0\t30\t1',
      '2\t0\t3\t16\t0\t0\t0\t0\t-35.36\t149.16\t30\t1',
    ].join('\r\n');
    expect(parseQgcWaypoints(file).map((w) => w.lat)).toEqual([-35.36]);
  });

  it('reads the waypoints inside a survey in a .plan file', () => {
    const wp = (lat: number) => ({ command: 16, type: 'SimpleItem', params: [0, 0, 0, null, lat, 8.5, 50] });
    const plan = {
      mission: {
        items: [
          wp(47.1),
          { type: 'ComplexItem', complexItemType: 'survey', TransectStyleComplexItem: { Items: [wp(47.2), wp(47.3)] } },
        ],
      },
    };
    expect(parseQgcPlan(JSON.stringify(plan)).map((w) => w.lat)).toEqual([47.1, 47.2, 47.3]);
  });
});

describe('altitudes in other frames', () => {
  it('refuses a .waypoints file above sea level', () => {
    const file = [
      'QGC WPL 110',
      '0\t1\t0\t16\t0\t0\t0\t0\t-35.363\t149.165\t584\t1',
      '1\t0\t0\t16\t0\t0\t0\t0\t-35.36\t149.16\t634\t1',
    ].join('\n');
    expect(() => parseQgcWaypoints(file)).toThrow(AltitudeFrameError);
  });

  it('refuses a .plan file above terrain', () => {
    const plan = {
      mission: { items: [{ command: 16, frame: 10, type: 'SimpleItem', params: [0, 0, 0, null, 47.2, 8.5, 450] }] },
    };
    expect(() => parseQgcPlan(JSON.stringify(plan))).toThrow(AltitudeFrameError);
  });

  it('takes the INT twin of the relative frame', () => {
    const file = ['QGC WPL 110', '1\t0\t6\t16\t0\t0\t0\t0\t-35.36\t149.16\t50\t1'].join('\n');
    expect(parseQgcWaypoints(file)[0].alt).toBe(50);
  });
});
