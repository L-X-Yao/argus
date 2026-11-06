import { test, expect, type Page } from '@playwright/test';
import { READY, close, label, openSession, readParams, tool } from './panels-sitl-helpers';
import type { Probe } from './sitl-probe';

// The compass view on the `calibration` vehicle model (libraries/SITL/SIM_Calibration.cpp),
// which turns the vehicle the way a person would. Needs that model: see run-panels-sitl.sh.
test.skip(!READY, 'run through tests/e2e/run-panels-sitl.sh');
test.describe.configure({ mode: 'serial', timeout: 300000 });

const MAV_CMD_DO_SET_SERVO = 183;
const OFFSETS = ['COMPASS_OFS_X', 'COMPASS_OFS2_X', 'COMPASS_OFS3_X']; // SITL has three

let page: Page;
let probe: Probe;

// Servo 5: below 1100 the model stops, and 1200-1299 runs it through calibration poses
// by itself (SIM_Calibration.cpp update()).
const poses = (pwm: number) => probe.command(MAV_CMD_DO_SET_SERVO, 5, pwm);

test.beforeAll(async ({ browser }) => {
  ({ page, probe } = await openSession(browser));
  await readParams(page);
});

test.afterAll(async () => {
  probe?.close();
  await page?.close();
});

test('draws the field as the vehicle turns, and the FC keeps what each compass found', async () => {
  const before = await Promise.all(OFFSETS.map((name) => probe.param(name)));
  const dialog = await tool(page, 'tool-compass3d', label('compass3d.title'));
  const samples = async () =>
    Number(
      (await dialog.getByText(new RegExp(`^${label('compass3d.samples')}: \\d+$`)).textContent())?.match(/\d+$/)?.[0],
    );

  await dialog.getByRole('button', { name: label('cal.start') }).click();
  await expect.poll(() => probe.magCal, { message: 'no MAG_CAL_PROGRESS' }).toBeGreaterThanOrEqual(0);
  poses(1250);
  await expect.poll(samples, { timeout: 30000 }).toBeGreaterThan(20);

  // Accepted, or the FC drops the results: it was started with autosave 0. They finish one
  // after the other, and an accept at the first would stop the rest with nothing saved.
  for (const [i, name] of OFFSETS.entries()) {
    await expect.poll(() => probe.param(name), { message: name, timeout: 240000, intervals: [2000] }).not.toBe(before[i]);
  }
  poses(1000);
  await close(page, dialog);
});
