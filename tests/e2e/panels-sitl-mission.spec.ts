import { test, expect, type Locator, type Page } from '@playwright/test';
import { READY, dialogOf, label, openSession, palette, tool, vehicleOnMap } from './panels-sitl-helpers';
import type { Probe, StoredItem } from './sitl-probe';

// Planning on real firmware: everything is drawn with the mouse, uploaded with the
// button, and judged by what MISSION_REQUEST_LIST gets back from the FC.
test.skip(!READY, 'run through tests/e2e/run-panels-sitl.sh');

// MAV_CMD
const WAYPOINT = 16;
const LOITER_TURNS = 18;
const LOITER_TIME = 19;
const RTL = 20;
const TAKEOFF = 22;
const SPLINE = 82;
const CONDITION_YAW = 115;
const CHANGE_SPEED = 178;
const SET_RELAY = 181;
const SET_SERVO = 183;
const SET_ROI = 201;
const CAM_TRIG_DIST = 206;
const VTOL_TRANSITION = 3000;
const GLOBAL_RELATIVE_ALT = 3;
const RALLY = 2;

let page: Page;
let probe: Probe;

const panel = () =>
  page
    .getByRole('heading', { name: label('wp.title'), exact: true })
    .locator('xpath=ancestor::div[contains(@class,"bg-card")][1]');
const rows = () => panel().locator('div.border-b.flex');
const waypoints = (n: number) => expect(panel().getByText(`(${n})`, { exact: true })).toBeVisible();

/** Metres per screen pixel, from the map's own scale bar. */
async function metersPerPixel(): Promise<number> {
  const [text, width] = await page
    .locator('.leaflet-control-scale-line')
    .first()
    .evaluate((el) => [el.textContent ?? '', parseFloat((el as HTMLElement).style.width)] as const);
  const [, value, unit] = text.match(/(\d+)\s*(k?m)/)!;
  return (Number(value) * (unit === 'km' ? 1000 : 1)) / width;
}

function metersBetween(a: { lat: number; lon: number }, b: { lat: number; lon: number }): [number, number] {
  return [(b.lon - a.lon) * 111320 * Math.cos((a.lat * Math.PI) / 180), (b.lat - a.lat) * 111320];
}

/** Clicks the map at these offsets from the vehicle, in screen pixels. */
async function clickMap(offsets: [number, number][]) {
  // A downloaded mission moves the map off the vehicle, and it stands still here.
  await page.locator('button.map-btn', { hasText: label('map.home') }).click();
  const at = await vehicleOnMap(page);
  for (const [dx, dy] of offsets) await page.mouse.click(at.x + dx, at.y + dy);
}

async function clearList() {
  if (await panel().getByText('(0)', { exact: true }).isVisible()) return;
  await panel().getByRole('button', { name: label('wp.clear'), exact: true }).click();
  const confirm = page.getByRole('alertdialog');
  await expect(confirm).toBeVisible();
  await page.waitForTimeout(350); // resolveConfirm ignores a yes in its first 300 ms
  await confirm.getByRole('button', { name: label('summary.confirm') }).click();
  await waypoints(0);
}

async function upload(expected: number): Promise<StoredItem[]> {
  await panel().getByRole('button', { name: label('wp.upload'), exact: true }).click();
  await expect.poll(async () => (await probe.store()).length, { message: 'mission on the FC' }).toBe(expected);
  await expect(panel().getByRole('button', { name: label('wp.upload'), exact: true })).toBeEnabled();
  return probe.store();
}

const commands = (items: StoredItem[]) => items.map((i) => i.command);

test.beforeAll(async ({ browser }) => {
  ({ page, probe } = await openSession(browser));
  await expect.poll(() => probe.position?.lat ?? 0, { timeout: 120000 }).not.toBe(0);
  await page.locator('nav button', { hasText: label('tab.plan') }).click();
  await expect(page.locator('.drone-icon')).toBeVisible({ timeout: 30000 });
});

test.afterAll(async () => {
  probe?.close();
  await page?.close();
});

test.beforeEach(async () => {
  if (await panel().isVisible()) await clearList();
});

test.describe('Waypoints', () => {
  test('clicks on the map reach the FC where they were clicked', async () => {
    await clickMap([
      [120, 0],
      [120, -90],
      [0, -90],
    ]);
    await waypoints(3);
    const items = await upload(6);
    expect(commands(items)).toEqual([WAYPOINT, TAKEOFF, WAYPOINT, WAYPOINT, WAYPOINT, RTL]);

    const scale = await metersPerPixel();
    const origin = { lat: probe.position!.lat, lon: probe.position!.lon };
    for (const [item, east, north] of [
      [items[2], 120, 0],
      [items[3], 120, 90],
      [items[4], 0, 90],
    ] as const) {
      const [e, n] = metersBetween(origin, item);
      expect(Math.abs(e - east * scale)).toBeLessThan(3 * scale);
      expect(Math.abs(n - north * scale)).toBeLessThan(3 * scale);
      expect(item.alt).toBe(30);
      expect(item.frame).toBe(GLOBAL_RELATIVE_ALT);
    }
    expect(items[1].alt).toBe(30);

    // And the row in the list says the same as the FC.
    await expect(rows().nth(0)).toContainText(`${items[2].lat.toFixed(5)},${items[2].lon.toFixed(5)}`);
  });

  test('what is edited in the list is what the FC holds', async () => {
    await clickMap([
      [100, 0],
      [100, -80],
      [0, -80],
      [-100, -80],
    ]);
    await waypoints(4);

    const alt = rows().nth(1).locator('input[type=number]').first();
    await alt.fill('45');
    await alt.press('Tab');
    const speed = rows().nth(0).locator('input[type=number]').nth(1);
    await speed.fill('7');
    await speed.press('Tab');
    await rows().nth(0).getByTitle(label('tip.dropToggle')).click();

    const type = (i: number) => rows().nth(i).getByTitle(label('tip.cycleType'));
    await type(1).click(); // spline
    await type(2).click();
    await type(2).click(); // loiter turns
    await type(3).click();
    await type(3).click();
    await type(3).click(); // loiter time

    const loiterSeconds = rows().nth(3).locator('input[type=number]').first();
    await loiterSeconds.fill('12');
    await loiterSeconds.press('Tab');

    const items = await upload(9);
    expect(commands(items)).toEqual([
      WAYPOINT,
      TAKEOFF,
      CHANGE_SPEED,
      WAYPOINT,
      SET_RELAY,
      SPLINE,
      LOITER_TURNS,
      LOITER_TIME,
      RTL,
    ]);
    expect(items[2].param2).toBe(7);
    expect(items[5].alt).toBe(45);
    expect(items[6].param1).toBe(3);
    expect(items[7].param1).toBe(12);
  });

  test('a mission downloaded from the FC comes back as it was', async () => {
    await clickMap([
      [100, 0],
      [100, -80],
    ]);
    await waypoints(2);
    const alt = rows().nth(1).locator('input[type=number]').first();
    await alt.fill('55');
    await alt.press('Tab');
    const items = await upload(5);
    await clearList();

    await palette(page, 'mission-download');
    await waypoints(2);
    await expect(rows().nth(0)).toContainText(`${items[2].lat.toFixed(5)},${items[2].lon.toFixed(5)}`);
    await expect(rows().nth(1).locator('input[type=number]').first()).toHaveValue('55');

    // The map fits the route once, not at every edit from then on.
    await clickMap([[60, 60]]);
    const before = await vehicleOnMap(page);
    await page.mouse.click(before.x - 60, before.y + 60);
    await waypoints(4);
    expect(await vehicleOnMap(page)).toEqual(before);
  });
});

test.describe('The map', () => {
  test('stays where it is put while planning', async () => {
    await page.locator('button.map-btn', { hasText: label('map.home') }).click();
    const start = await vehicleOnMap(page);
    await page.mouse.move(start.x + 200, start.y + 100);
    await page.mouse.down();
    await page.mouse.move(start.x + 80, start.y + 40, { steps: 8 });
    await page.mouse.up();
    await page.waitForTimeout(1500); // the FC sends a position ten times a second
    const moved = await vehicleOnMap(page);
    expect(moved.x).toBeLessThan(start.x - 100);
  });
});

test.describe('Survey', () => {
  test('a grid covers the area at the spacing and heading asked for', async () => {
    await page.locator('button.map-btn', { hasText: label('map.survey') }).click();
    await page.getByRole('button', { name: label('survey.drawArea') }).click();
    await clickMap([
      [-120, -100],
      [120, -100],
      [120, 60],
      [-120, 60],
    ]);
    await page.getByRole('button', { name: label('survey.finishDraw') }).click();

    await page.locator('#sv-angle').fill('90');
    await page.locator('#sv-spacing').fill('100');
    await page.locator('#sv-over').fill('0');
    const preview = page.getByText(label('survey.previewCount')).locator('b');
    await expect.poll(async () => Number(await preview.textContent())).toBeGreaterThan(4);
    const count = Number(await preview.textContent());
    await page.getByRole('button', { name: label('survey.generate') }).click();
    await waypoints(count);

    const items = await upload(count + 3);
    const nav = items.slice(2, -1);
    expect(new Set(commands(nav))).toEqual(new Set([WAYPOINT]));

    const scale = await metersPerPixel();
    const origin = { lat: probe.position!.lat, lon: probe.position!.lon };
    const pairs = nav.length / 2;
    const east: number[] = [];
    for (let i = 0; i < pairs; i++) {
      const [a, b] = [nav[2 * i], nav[2 * i + 1]];
      const [dx, dy] = metersBetween(a, b);
      expect(Math.abs(dx)).toBeLessThan(1); // 90 degrees: the runs go north and south
      expect(Math.abs(Math.abs(dy) - 160 * scale)).toBeLessThan(5 * scale);
      east.push(metersBetween(origin, a)[0]);
    }
    for (let i = 1; i < east.length; i++) expect(Math.abs(east[i] - east[i - 1])).toBeCloseTo(100, 0);
    // All of it inside the box drawn.
    expect(Math.min(...east)).toBeGreaterThan(-120 * scale - 3 * scale);
    expect(Math.max(...east)).toBeLessThan(120 * scale + 3 * scale);

    await page.getByRole('button', { name: label('survey.clear') }).last().click();
    await page.locator('button.map-btn', { hasText: label('map.survey') }).click();
  });
});

test.describe('Corridor', () => {
  test('flies parallel lines either side of the line drawn, and only those', async () => {
    await clickMap([
      [-100, -60],
      [100, -60],
    ]);
    await waypoints(2);
    const [a, b] = await rowsCoordinates();

    const dialog = await tool(page, 'tool-corridor', label('corridor.title'));
    await dialog.locator('#cor-width').fill('100');
    await dialog.locator('#cor-spacing').fill('50');
    await dialog.locator('#cor-alt').fill('40');
    const generate = dialog.getByRole('button', { name: label('corridor.generate') });
    await generate.click();
    await generate.click(); // the second press has to change nothing
    await dialog.getByRole('button', { name: label('error.close') }).click();
    await waypoints(6);

    const items = await upload(9);
    const nav = items.slice(2, -1);
    expect(nav.every((i) => i.alt === 40)).toBe(true);
    // A line east to west, so the offsets go north and south of it.
    const north = nav.map((i) => metersBetween(a, i)[1]);
    // Within the slant the map datum gives a straight screen line over 800 m.
    expect(Math.abs(north[0] - north[1])).toBeLessThan(3);
    expect(Math.abs(north[2] - north[3])).toBeLessThan(3);
    expect(Math.abs(north[4] - north[5])).toBeLessThan(3);
    expect(north.map((n) => Math.round(n / 10) * 10).sort((x, y) => x - y)).toEqual([-50, -50, 0, 0, 50, 50]);
    // Ends of the drawn line, serpentine: there and back.
    expect(metersBetween(a, nav[0])[0]).toBeCloseTo(0, -1);
    expect(metersBetween(b, nav[1])[0]).toBeCloseTo(0, -1);
    expect(metersBetween(b, nav[2])[0]).toBeCloseTo(0, -1);
  });
});

/** Latitude and longitude of each row, as the list shows them. */
async function rowsCoordinates(): Promise<{ lat: number; lon: number }[]> {
  const texts = await rows().allTextContents();
  return texts.map((t) => {
    const [, lat, lon] = t.match(/(-?\d+\.\d{5}),(-?\d+\.\d{5})/)!;
    return { lat: Number(lat), lon: Number(lon) };
  });
}

test.describe('Advanced commands', () => {
  const pick = (dialog: Locator, key: string) => dialog.getByRole('button', { name: label(key), exact: true }).click();

  test('each lands after its waypoint with what was typed', async () => {
    await clickMap([
      [100, 0],
      [100, -80],
    ]);
    await waypoints(2);
    const dialog = await tool(page, 'tool-advcmd', label('advcmd.title'));
    const insert = () => dialog.getByRole('button', { name: label('advcmd.insert'), exact: true }).click();

    await dialog.locator('#ac-insert-after').selectOption({ index: 0 });
    await pick(dialog, 'advcmd.servo');
    await dialog.locator('#ac-servo-num').fill('9');
    await dialog.locator('#ac-servo-pwm').fill('1700');
    await insert();

    await pick(dialog, 'advcmd.roi');
    await dialog.locator('#ac-roi-lat').fill('-35.3621');
    await dialog.locator('#ac-roi-lon').fill('149.1662');
    await dialog.locator('#ac-roi-alt').fill('12');
    await insert();

    await pick(dialog, 'advcmd.delay');
    await dialog.locator('#ac-delay').fill('7');
    await insert();

    await dialog.locator('#ac-insert-after').selectOption({ index: 1 });
    await pick(dialog, 'advcmd.camTrig');
    await dialog.locator('#ac-cam-dist').fill('25');
    await insert();

    await pick(dialog, 'advcmd.yaw');
    await dialog.locator('#ac-yaw-deg').fill('90');
    await dialog.getByRole('button', { name: label('label.ccw') }).click();
    await insert();

    await pick(dialog, 'advcmd.vtolTransition');
    await dialog.getByRole('button', { name: label('label.hover') }).click();
    await insert();
    await dialog.getByRole('button', { name: label('error.close') }).click();

    const items = await upload(10);
    expect(commands(items)).toEqual([
      WAYPOINT,
      TAKEOFF,
      WAYPOINT,
      SET_SERVO,
      SET_ROI,
      WAYPOINT,
      CAM_TRIG_DIST,
      CONDITION_YAW,
      VTOL_TRANSITION,
      RTL,
    ]);
    expect(items[2].param1).toBe(7);
    expect(items[3].param1).toBe(9);
    expect(items[3].param2).toBe(1700);
    expect(items[4].lat).toBeCloseTo(-35.3621, 5);
    expect(items[4].lon).toBeCloseTo(149.1662, 5);
    // The field reads as height above home, like every other altitude here. In a mission
    // frame the FC would take it as metres above sea level (AP_Mission.cpp:1496).
    expect(items[4].alt).toBe(12);
    expect(items[4].frame).toBe(GLOBAL_RELATIVE_ALT);
    expect(items[6].param1).toBe(25);
    expect(items[7].param1).toBe(90);
    expect(items[7].param3).toBe(-1);
    expect(items[8].param1).toBe(4);
  });
});

test.describe('Rally points', () => {
  test('clicks on the map reach the FC, and the button clears them there', async () => {
    await page.locator('button.map-btn', { hasText: label('rally.title') }).click();
    const rally = page.locator('div.bg-card').filter({ has: page.getByRole('heading', { name: label('rally.title') }) });
    await rally.getByRole('button', { name: label('rally.add') }).click();
    await clickMap([
      [80, 40],
      [-60, 40],
    ]);
    await rally.getByRole('button', { name: label('fence.finish') }).click();
    await rally.getByRole('button', { name: label('rally.upload'), exact: true }).click();
    await expect.poll(async () => (await probe.store(RALLY)).length, { message: 'rally points on the FC' }).toBe(2);
    await expect(rally.getByText(label('fence.uploaded'))).toBeVisible();

    const scale = await metersPerPixel();
    const points = await probe.store(RALLY);
    const [east, south] = metersBetween(probe.position!, points[0]);
    expect(Math.abs(east - 80 * scale)).toBeLessThan(3 * scale);
    expect(Math.abs(south + 40 * scale)).toBeLessThan(3 * scale);
    expect(points[0].alt).toBe(30);
    expect(points[0].frame).toBe(GLOBAL_RELATIVE_ALT);

    await rally.getByRole('button', { name: label('rally.clearFc'), exact: true }).click();
    const confirm = page.getByRole('alertdialog');
    await page.waitForTimeout(350);
    await confirm.getByRole('button', { name: label('summary.confirm') }).click();
    await expect.poll(async () => (await probe.store(RALLY)).length).toBe(0);

    await rally.getByRole('button', { name: label('rally.clear'), exact: true }).last().click();
    await page.locator('button.map-btn', { hasText: label('rally.title') }).click();
  });
});

test.describe('Terrain profile', () => {
  test('measures clearance from home, not from sea level', async () => {
    await clickMap([
      [120, 0],
      [120, -90],
    ]);
    await waypoints(2);
    await panel().getByRole('button', { name: label('terrain.profile') }).click();
    const dialog = dialogOf(page, label('terrain.profileTitle'));
    await expect(dialog).toBeVisible();

    // The ground along the route and at home, straight from the terrain service.
    const [a, b] = await rowsCoordinates();
    const route = Array.from({ length: 21 }, (_, i) => ({
      lat: a.lat + ((b.lat - a.lat) * i) / 20,
      lon: a.lon + ((b.lon - a.lon) * i) / 20,
    }));
    const points = [probe.position!, ...route].map((p) => `${p.lat},${p.lon}`).join(';');
    const answer = await page.request.get(`/api/terrain/elevation?points=${points}`);
    const { elevations } = (await answer.json()) as { elevations: number[] };
    test.skip(
      elevations.every((e) => e === 0),
      'no terrain data on this machine',
    );
    const [home, ...ground] = elevations;
    const lowest = 30 - (Math.max(...ground) - home);

    // Waypoints at 30 m above home over ground near the height of home, which is 584 m
    // above the sea: a figure anywhere near -550 would mean the two were compared raw.
    const shown = dialog.getByTestId('terrain-lowest-clearance');
    await expect(shown).toBeVisible({ timeout: 30000 });
    const value = Number((await shown.textContent())!.match(/(-?\d+)m$/)![1]);
    expect(Math.abs(value - lowest)).toBeLessThan(5);
    await dialog.getByRole('button', { name: label('error.close') }).click();
  });
});
