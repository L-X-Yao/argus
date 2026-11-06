import { test, expect, type Locator, type Page } from '@playwright/test';
import { READY, close, dialogOf, label, openSession, readParams, tool } from './panels-sitl-helpers';
import type { Probe } from './sitl-probe';

// The setup panels on real firmware. The FC's own outputs and parameters say what
// happened, and a Probe stands in for the pilot's transmitter where one is needed.
test.skip(!READY, 'run through tests/e2e/run-panels-sitl.sh');

let page: Page;
let probe: Probe;

test.beforeAll(async ({ browser }) => {
  ({ page, probe } = await openSession(browser));
  await readParams(page);
});

test.afterAll(async () => {
  probe?.close();
  await page?.close();
});

// By its place in the grid: a spinning button shows a countdown instead of its name.
const motor = (dialog: Locator, index: number) =>
  dialog.locator('div.grid-cols-4 > div').nth(index).getByRole('button');

test.describe('Motor test', () => {
  test('opening and closing the panel leaves the motors alone', async () => {
    const before = probe.texts.length;
    const dialog = await tool(page, 'tool-motor', label('motor.title'));
    await close(page, dialog);
    await page.waitForTimeout(1500);
    expect(probe.texts.slice(before).filter((t) => t.includes('motor test'))).toEqual([]);
  });

  test('a button spins the motor the firmware numbers that way', async () => {
    // On a quad X the test order runs clockwise from the front right, and each is wired
    // to the output AP_MotorsMatrix.cpp:592 gives it.
    await probe.setParam('FRAME_TYPE', 1);
    await page.waitForTimeout(2000); // the FC picks a new type up within a second, disarmed
    const dialog = await tool(page, 'tool-motor', label('motor.title'));
    await dialog.locator('#motor-throttle').fill('30');
    await dialog.locator('#motor-duration').fill('1.5');
    for (const [button, output] of [
      [0, 0],
      [1, 3],
      [2, 1],
      [3, 2],
    ] as const) {
      await motor(dialog, button).click();
      await expect
        .poll(() => probe.servo[output], { message: `motor ${button + 1} on output ${output + 1}` })
        .toBeGreaterThanOrEqual(1250);
      expect(probe.servo.slice(0, 4).filter((pwm) => pwm > 1100)).toHaveLength(1);
      await expect.poll(() => probe.servo[output], { timeout: 10000 }).toBeLessThanOrEqual(1100);
      await expect(motor(dialog, button)).toHaveText(label('motor.spin'));
    }
    await close(page, dialog);
    await probe.setParam('FRAME_TYPE', 0);
  });

  test('the layout printed in the panel matches the order the motors spin in', async () => {
    const dialog = await tool(page, 'tool-motor', label('motor.title'));
    // AP_MotorsMatrix.cpp:592, by the bearing of each motor and its test order.
    await expect(dialog.getByText(label('motor.fr'))).toContainText('(1)');
    await expect(dialog.getByText(label('motor.br'))).toContainText('(2)');
    await expect(dialog.getByText(label('motor.bl'))).toContainText('(3)');
    await expect(dialog.getByText(label('motor.fl'))).toContainText('(4)');
    await close(page, dialog);
  });

  test('Stop ends a test early', async () => {
    const dialog = await tool(page, 'tool-motor', label('motor.title'));
    await dialog.locator('#motor-throttle').fill('30');
    await dialog.locator('#motor-duration').fill('5');
    const started = probe.texts.length;
    await motor(dialog, 0).click();
    await expect.poll(() => Math.max(...probe.servo.slice(0, 4))).toBeGreaterThanOrEqual(1250);
    await dialog.getByRole('button', { name: label('motor.stop') }).click();
    await expect.poll(() => Math.max(...probe.servo.slice(0, 4)), { timeout: 1500 }).toBeLessThanOrEqual(1100);
    await page.waitForTimeout(1000);
    expect(probe.texts.slice(started).filter((t) => t === 'starting motor test')).toHaveLength(1);
    await close(page, dialog);
    expect(probe.armed).toBe(false);
  });
});

test.describe('Motor test panel', () => {
  test('closing it with a motor running stops the motor', async () => {
    const dialog = await tool(page, 'tool-motor', label('motor.title'));
    await dialog.locator('#motor-throttle').fill('30');
    await dialog.locator('#motor-duration').fill('5');
    await motor(dialog, 0).click();
    await expect.poll(() => Math.max(...probe.servo.slice(0, 4))).toBeGreaterThanOrEqual(1250);
    await close(page, dialog);
    await expect.poll(() => Math.max(...probe.servo.slice(0, 4)), { timeout: 1500 }).toBeLessThanOrEqual(1100);
  });
});

test.describe('Calibration', () => {
  test('opens with the same line twice in the log', async () => {
    // A start and a stop inside one second give two identical answers from the FC, and
    // the panel lists them. A keyed list threw on that and the panel never came up.
    const dialog = await tool(page, 'tool-motor', label('motor.title'));
    await dialog.locator('#motor-duration').fill('5');
    await motor(dialog, 0).click();
    await dialog.getByRole('button', { name: label('motor.stop') }).click();
    await close(page, dialog);
    await page.getByRole('button', { name: label('nav.calibrate') }).click();
    const calibration = dialogOf(page, label('cal.title'));
    await expect(calibration).toBeVisible();
    await close(page, calibration);
  });
});

test.describe('Setup wizard', () => {
  test('reads properly and walks through all six steps', async () => {
    const dialog = await tool(page, 'tool-setup', label('setup.title'));
    for (let step = 1; step <= 6; step++) {
      await expect(dialog.locator('h3')).toContainText(`${step}/6`);
      await expect(dialog).not.toContainText('{');
      await expect(dialog).not.toContainText('.desc');
      await dialog.getByRole('button', { name: label('setup.next') }).click();
    }
    await expect(dialog.getByText(label('setup.done')).first()).toBeVisible();
    await dialog.getByRole('button', { name: label('setup.done') }).click();
    await expect(dialog).toHaveCount(0);
  });

  test('a step opens its tool over the wizard, and what is done there reaches the FC', async () => {
    const wizard = await tool(page, 'tool-setup', label('setup.title'));
    await wizard.locator('button.w-full').click();
    const frame = dialogOf(page, label('frame.title'));
    await expect(frame).toBeVisible();
    await frame.locator('div.grid').nth(1).getByRole('button').filter({ hasText: /=1$/ }).click();
    await frame.getByRole('button', { name: label('frame.write') }).click();
    await expect.poll(() => probe.param('FRAME_TYPE')).toBe(1);
    await frame.locator('div.grid').nth(1).getByRole('button').filter({ hasText: /=0$/ }).click();
    await frame.getByRole('button', { name: label('frame.write') }).click();
    await expect.poll(() => probe.param('FRAME_TYPE')).toBe(0);
    await close(page, frame);

    // Each of the others opens, on top, and hands the wizard back.
    const tools = ['rccal.title', 'motor.title', 'cal.title', 'failsafe.title', 'fltmode.title'];
    for (const title of tools) {
      await wizard.getByRole('button', { name: label('setup.next') }).click();
      await wizard.locator('button.w-full').click();
      const opened = dialogOf(page, label(title));
      await expect(opened).toBeVisible();
      await close(page, opened);
    }
    await wizard.getByRole('button', { name: label('setup.next') }).click();
    await expect(wizard).toContainText('6/6');
    await wizard.getByRole('button', { name: label('setup.done') }).click();
  });
});

test.describe('RC calibration', () => {
  const CENTER = [1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500];
  let stick: ReturnType<typeof setInterval>;
  let sticks = CENTER;

  test.beforeAll(() => {
    stick = setInterval(() => probe.sticks(sticks), 100);
  });
  test.afterAll(() => {
    clearInterval(stick);
    probe.sticks([0, 0, 0, 0, 0, 0, 0, 0]);
  });

  /** Moves one stick and waits until the panel has seen it. */
  async function move(dialog: Locator, channel: number, pwm: number) {
    sticks = sticks.map((v, i) => (i === channel ? pwm : v));
    await expect(dialog.locator('div.flex.items-center.text-\\[11px\\]').nth(channel)).toContainText(String(pwm));
  }

  test('a transmitter of four channels calibrates, and leaves the rest alone', async () => {
    const untouched = await probe.param('RC7_MIN');
    sticks = CENTER;
    await expect.poll(() => probe.rc.slice(0, 4)).toEqual([1500, 1500, 1500, 1500]);
    const dialog = await tool(page, 'tool-rccal', label('rccal.title'));
    await dialog.getByRole('button', { name: label('rccal.recordTrim') }).click();

    for (const [channel, low, high] of [
      [0, 1102, 1899],
      [1, 1098, 1903],
      [2, 1104, 1896],
      [3, 1101, 1902],
    ] as const) {
      await move(dialog, channel, low);
      await move(dialog, channel, high);
      await move(dialog, channel, 1500);
    }
    await dialog.getByRole('button', { name: label('rccal.next') }).click();
    await dialog.getByRole('button', { name: label('rccal.write') }).click();

    await expect.poll(() => probe.param('RC1_MIN')).toBe(1102);
    expect(await probe.param('RC1_MAX')).toBe(1899);
    expect(await probe.param('RC1_TRIM')).toBe(1500);
    expect(await probe.param('RC2_MIN')).toBe(1098);
    expect(await probe.param('RC3_MAX')).toBe(1896);
    expect(await probe.param('RC4_MIN')).toBe(1101);
    expect(await probe.param('RC7_MIN')).toBe(untouched);
    await close(page, dialog);
  });

  test('a stick that is not centred between its ends stays the right way round', async () => {
    sticks = CENTER;
    await expect.poll(() => probe.rc.slice(0, 4)).toEqual([1500, 1500, 1500, 1500]);
    const dialog = await tool(page, 'tool-rccal', label('rccal.title'));
    await dialog.getByRole('button', { name: label('rccal.recordTrim') }).click();
    for (const [channel, low, high] of [
      [0, 1000, 2000],
      [1, 1100, 1700], // the middle of this one sits 100 below its trim
      [2, 1000, 2000],
      [3, 1000, 2000],
    ] as const) {
      await move(dialog, channel, low);
      await move(dialog, channel, high);
      await move(dialog, channel, 1500);
    }
    await dialog.getByRole('button', { name: label('rccal.next') }).click();
    await dialog.getByRole('button', { name: label('rccal.write') }).click();

    // RC_Channel::get_control_in works from min < max with the direction in REVERSED,
    // and AP_Arming refuses a trim outside them.
    await expect.poll(() => probe.param('RC2_MIN')).toBe(1100);
    expect(await probe.param('RC2_MAX')).toBe(1700);
    expect(await probe.param('RC2_REVERSED')).toBe(0);
    await close(page, dialog);
  });
});

test.describe('ESC calibration', () => {
  test('arms the calibration the FC runs on its next power-up, and can take it back', async () => {
    const dialog = await tool(page, 'tool-esccal', label('esccal.title'));
    expect(await probe.param('ESC_CALIBRATION')).toBe(0);
    await dialog.getByRole('button', { name: label('esccal.arm') }).click();
    // 3 = start up and calibrate by itself: ArduCopter/esc_calibration.cpp:60.
    await expect.poll(() => probe.param('ESC_CALIBRATION')).toBe(3);
    await expect(dialog.getByText(label('esccal.armed'))).toBeVisible();
    // The firmware takes it for a calibration: it now refuses a soft reboot, the ESCs
    // have to lose power too (GCS_MAVLink_Copter.cpp handle_preflight_reboot).
    probe.command(246, 1);
    await expect.poll(() => probe.texts.join('|')).toContain('Reboot rejected, ESC cal on reboot');

    await dialog.getByRole('button', { name: label('esccal.disarm') }).click();
    await expect.poll(() => probe.param('ESC_CALIBRATION')).toBe(0);
    await expect(dialog.getByText(label('esccal.armed'))).toHaveCount(0);
    await close(page, dialog);
  });
});

