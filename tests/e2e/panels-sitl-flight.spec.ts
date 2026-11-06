import { test, expect, type Locator, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { READY, close, label, openSession, palette, tool, vehicleOnMap } from './panels-sitl-helpers';
import type { Probe } from './sitl-probe';

// One flight on real firmware, flown with the mouse alone: connect, slide to arm, slide to
// take off, the mission, a pause, RTL and the landing. What the UI claims is checked
// against the vehicle's own heartbeat, position and mission progress.
test.skip(!READY, 'run through tests/e2e/run-panels-sitl.sh');
test.describe.configure({ mode: 'serial' });

// ArduCopter/mode.h enum class Number
const AUTO = 3;
const GUIDED = 4;
const LOITER = 5;
const RTL = 6;

let page: Page;
let probe: Probe;
let controls: Locator;
let pilot: ReturnType<typeof setInterval> | undefined;
const speed = () => Math.hypot(probe.position?.vx ?? 0, probe.position?.vy ?? 0);

/** Drags the handle across, as a finger does. */
async function slide(to = 1) {
  const handle = page.getByRole('slider');
  await expect(handle).toBeVisible();
  const box = (await handle.boundingBox())!;
  const track = (await page.locator('.slide-track').boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(track.x + track.width * to, box.y + box.height / 2, { steps: 12 });
  await page.mouse.up();
}

const button = (key: string) =>
  controls.getByRole('button', { name: key === 'ctrl.modeStabilize' ? '自稳' : label(key), exact: true });
const nav = (key: string) => page.locator('nav').getByRole('button', { name: label(key), exact: true });

test.beforeAll(async ({ browser }) => {
  ({ page, probe } = await openSession(browser));
  await expect
    .poll(() => (probe.position?.lat ?? 0) !== 0 && probe.position?.hdg !== undefined, { timeout: 120000 })
    .toBe(true);
});

test.afterAll(async () => {
  clearInterval(pilot);
  probe?.close();
  await page?.close();
});

test('plans a route with the mouse', async () => {
  await nav('tab.plan').click();
  const { x, y } = await vehicleOnMap(page);
  const panel = page
    .getByRole('heading', { name: label('wp.title'), exact: true })
    .locator('xpath=ancestor::div[contains(@class,"bg-card")][1]');
  // About 150 m a leg at this zoom: long enough to pause in, short enough to fly in a minute.
  await panel.getByRole('button', { name: '10', exact: true }).click();
  await page.mouse.click(x + 40, y);
  await page.mouse.click(x + 40, y - 40);
  await page.mouse.click(x, y - 40);
  await expect(panel.getByText('(3)', { exact: true })).toBeVisible();
  await panel.getByRole('button', { name: label('wp.upload'), exact: true }).click();
  await expect.poll(async () => (await probe.store()).length).toBe(6);
  await nav('tab.fly').click();
  await page.getByRole('button', { name: label('nav.controls') }).click();
  controls = page.locator('div.w-44');
  await expect(controls).toBeVisible();
});

test('a slide let go too early arms nothing', async () => {
  await button('ctrl.arm').click();
  await slide(0.5);
  await page.waitForTimeout(600);
  expect(probe.armed).toBe(false);
  await expect(page.getByRole('slider')).toHaveAttribute('aria-valuenow', '0');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('slider')).toHaveCount(0);
});

test('the slide arms it', async () => {
  // The FC holds out until the EKF has settled, and says so.
  await expect
    .poll(
      async () => {
        await button('ctrl.arm').click();
        await slide();
        await page.waitForTimeout(1500);
        return probe.armed;
      },
      { message: 'never armed', timeout: 120000, intervals: [500] },
    )
    .toBe(true);
  await expect(button('ctrl.takeoff')).toBeVisible();
});

test('AutoTune refuses on the ground, with the axes written', async () => {
  const dialog = await tool(page, 'tool-autotune', label('autotune.title'));
  await dialog.getByRole('button', { name: label('autotune.rollOnly') }).click();
  await dialog.getByRole('button', { name: label('autotune.start'), exact: true }).click();
  await expect.poll(() => probe.param('AUTOTUNE_AXES')).toBe(1);
  await page.waitForTimeout(1000);
  expect(probe.mode).not.toBe(15); // ArduCopter/mode_autotune.cpp:17: not while landed
  await expect(page.getByText(/模式 — 失败/).first()).toBeVisible();

  await dialog.getByRole('button', { name: label('autotune.all') }).click();
  await dialog.getByRole('button', { name: label('autotune.start'), exact: true }).click();
  await expect.poll(() => probe.param('AUTOTUNE_AXES')).toBe(7);
  await close(page, dialog);
});

test('Takeoff climbs to the height set, from whatever mode it was armed in', async () => {
  await controls.locator('input[type=number]').fill('15');
  await controls.locator('input[type=number]').press('Tab');
  await button('ctrl.takeoff').click();
  await slide();
  await expect.poll(() => probe.mode).toBe(GUIDED);
  await expect.poll(() => probe.altitude, { timeout: 60000 }).toBeGreaterThan(13);
  // A pilot's throttle sits in the middle in the air. SITL's sits at the bottom, which in
  // LOITER, the mode Pause uses, would bring the vehicle down.
  pilot = setInterval(() => probe.sticks([0, 0, 1500, 0, 0, 0, 0, 0]), 100);
});

test('a point of interest turns the vehicle, and clearing it lets go', async () => {
  const start = probe.position!;
  await expect.poll(speed).toBeLessThan(0.5);
  const dialog = await tool(page, 'tool-poi', label('poi.title'));
  // 100 m due east of here.
  await dialog.locator('#poi-lat').fill(String(start.lat));
  await dialog.locator('#poi-lon').fill(String(start.lon + 100 / (111320 * Math.cos((start.lat * Math.PI) / 180))));
  await dialog.locator('#poi-alt').fill('15');
  await dialog.getByRole('button', { name: label('poi.set'), exact: true }).click();
  await expect.poll(() => probe.position!.hdg, { timeout: 30000 }).toBeGreaterThan(80);
  await expect.poll(() => probe.position!.hdg, { timeout: 30000 }).toBeLessThan(100);

  await dialog.getByRole('button', { name: label('poi.clear'), exact: true }).click();
  await close(page, dialog);
});

test('MapControls fly the same as the sidebar', async () => {
  await page.keyboard.press('m');
  const overlay = page.locator('div.min-w-\\[220px\\]');
  await expect(overlay).toBeVisible();
  await expect(overlay.getByRole('button', { name: label('ctrl.rtl'), exact: true })).toBeVisible();

  await overlay.getByRole('button', { name: label('ctrl.pause'), exact: true }).first().click();
  await expect.poll(() => probe.mode).toBe(LOITER);
  await expect(overlay.locator('span.text-primary')).toContainText('悬停');

  await page.keyboard.press('m');
  await expect(overlay).toHaveCount(0);
});

test('Start mission flies it, and MissionProgress keeps up with the FC', async () => {
  await button('ctrl.startMission').click();
  await slide();
  await expect.poll(() => probe.mode).toBe(AUTO);

  const progress = page.locator('div.w-80').filter({ hasText: 'WP' });
  await expect(progress).toBeVisible();
  // seq 0 is home and 1 the takeoff, so waypoint n is seq n + 1.
  await expect.poll(() => probe.missionSeq, { timeout: 30000 }).toBeGreaterThanOrEqual(3);
  await expect
    .poll(async () => {
      const seq = probe.missionSeq;
      const text = (await progress.textContent()) ?? '';
      return text.includes(`#${seq - 1}`) && text.includes(`${seq - 2}/3 WP`);
    })
    .toBe(true);
});

test('a takeoff asked for in the air leaves the mission flying', async () => {
  await palette(page, 'cmd-takeoff');
  await slide();
  // The FC refuses it up there (ArduCopter/takeoff.cpp:23), and GUIDED would stop the mission.
  await page.waitForTimeout(2000);
  expect(probe.mode).toBe(AUTO);
});

test('Pause holds the vehicle where it is, and the mission resumes', async () => {
  const at = probe.missionSeq;
  await button('ctrl.pauseMission').click();
  await expect.poll(() => probe.mode).toBe(LOITER);
  await expect.poll(speed, { timeout: 20000 }).toBeLessThan(0.5);
  await expect(page.locator('div.w-80').filter({ hasText: 'WP' })).toHaveCount(0);

  await button('ctrl.startMission').click();
  await slide();
  await expect.poll(() => probe.mode).toBe(AUTO);
  await expect.poll(() => probe.missionSeq, { timeout: 60000 }).toBeGreaterThan(at);
});

test('RTL brings it home and it lands', async () => {
  await expect.poll(() => probe.reached.length, { timeout: 60000 }).toBeGreaterThan(0);
  await button('ctrl.abortRtl').click();
  await slide();
  await expect.poll(() => probe.mode).toBe(RTL);
  await expect(controls.getByText(label('phase.returning'))).toBeVisible();
  await expect.poll(() => probe.armed, { timeout: 180000 }).toBe(false);
  clearInterval(pilot);
  expect(probe.altitude).toBeLessThan(1);
});

test('the flight summary shows what the FC flew', async () => {
  const summary = page.getByRole('dialog').filter({ hasText: label('summary.title') });
  await expect(summary).toBeVisible();

  const value = async (key: string) => {
    const text = await summary.getByText(label(key), { exact: true }).locator('xpath=following-sibling::div').textContent();
    return text!;
  };
  expect(Math.abs(parseFloat(await value('summary.maxAlt')) - probe.maxAltitude)).toBeLessThan(1);
  expect(parseFloat(await value('summary.dist'))).toBeGreaterThan(50);
  expect(await value('summary.duration')).toMatch(/^\d+:\d\d$/);

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    summary.getByRole('button', { name: label('wp.export') }).click(),
  ]);
  const report = readFileSync(await download.path(), 'utf-8');
  expect(report).toContain(await value('summary.maxAlt'));

  await summary.getByRole('button', { name: label('summary.confirm') }).click();
  await expect(summary).toHaveCount(0);
});

test('the flight report keeps the flight after the summary is gone', async () => {
  await palette(page, 'tool-report');
  const dialog = page.getByRole('dialog', { name: label('report.title') }); // the inner of two
  await expect(dialog).toBeVisible();
  await dialog.getByPlaceholder(label('report.pilot')).fill('Li Si');
  await dialog.getByPlaceholder(label('report.weather')).fill('Clear');
  await dialog.getByPlaceholder(label('report.notes')).fill('SITL run');
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    dialog.getByRole('button', { name: label('report.export') }).click(),
  ]);
  const report = readFileSync(await download.path(), 'utf-8');
  expect(report).toContain('Pilot: Li Si');
  expect(report).toContain('Weather: Clear');
  expect(report).toContain('SITL run');
  expect(report).toMatch(/Vehicle: .*v4\.\d+\.\d+/);
  const reported = parseFloat(report.match(/Max Altitude: ([\d.]+) m/)![1]);
  expect(Math.abs(reported - probe.maxAltitude)).toBeLessThan(1);
  expect(report).toMatch(/--- Event Log ---\n.+/);
  await close(page, dialog);
});

test('an arm and disarm with no flight reports none', async () => {
  // Landed in RTL, which the FC will not arm in: ArduCopter/mode.h ModeRTL::allows_arming.
  await button('ctrl.modeStabilize').click();
  await expect.poll(() => probe.mode).toBe(0);
  await expect
    .poll(
      async () => {
        await button('ctrl.arm').click();
        await slide();
        await page.waitForTimeout(1000);
        return probe.armed;
      },
      { timeout: 30000, intervals: [500] },
    )
    .toBe(true);
  await button('ctrl.disarm').click();
  await expect.poll(() => probe.armed).toBe(false);
  await page.waitForTimeout(1000);
  await expect(page.getByRole('dialog').filter({ hasText: label('summary.title') })).toHaveCount(0);
});

