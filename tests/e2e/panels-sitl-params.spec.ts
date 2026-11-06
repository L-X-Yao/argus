import { test, expect, type Locator, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { READY, close, connect, label, openSession, palette, readParams, tool } from './panels-sitl-helpers';
import type { Probe } from './sitl-probe';

// The panels that edit parameters, on real firmware: every value is read back from the
// FC over a link of its own. Boots through run-panels-sitl.sh.
test.skip(!READY, 'run through tests/e2e/run-panels-sitl.sh');

let page: Page;
let probe: Probe;

const onFc = (name: string) => expect.poll(() => probe.param(name), { message: name });

test.beforeAll(async ({ browser }) => {
  ({ page, probe } = await openSession(browser));
  await readParams(page);
});

test.afterAll(async () => {
  probe?.close();
  await page?.close();
});

test('the list holds every parameter the FC has', async () => {
  const count = await probe.paramCount();
  expect(count).toBeGreaterThan(1000);
  await expect(page.getByText(`${count} ${label('param.params')}`)).toBeVisible();
});

test('a row edited in the list reaches the FC', async () => {
  await page.locator('nav button', { hasText: label('tab.params') }).click();
  const value = (await probe.param('WP_YAW_BEHAVIOR')) === 1 ? 2 : 1;
  await page.getByPlaceholder(label('param.search')).fill('WP_YAW_BEHAVIOR');
  const row = page.locator('div.font-mono.cursor-pointer');
  await expect(row).toHaveCount(1);
  await row.click();
  await page.locator('input.font-mono').fill(String(value));
  await page.getByRole('button', { name: label('param.write'), exact: true }).click();
  await onFc('WP_YAW_BEHAVIOR').toBe(value);
  await expect(row).toHaveText(String(value));
  await page.getByPlaceholder(label('param.search')).fill('');
  // Shortcuts stay out of a text box, so the palette needs the focus out of it.
  await page.getByRole('heading', { name: label('param.title'), exact: true }).click();
});

test.describe('Flight modes', () => {
  test('shows the six slots the FC holds', async () => {
    const dialog = await tool(page, 'tool-modes', label('fltmode.title'));
    const slots = dialog.locator('select');
    await expect(slots).toHaveCount(6);
    for (let i = 0; i < 6; i++) {
      await expect(slots.nth(i)).toHaveValue(String(await probe.param(`FLTMODE${i + 1}`)));
    }
    await close(page, dialog);
  });

  test('a mode picked by name is the one the FC flies on that switch position', async () => {
    const dialog = await tool(page, 'tool-modes', label('fltmode.title'));
    const slots = dialog.locator('select');
    await slots.nth(1).selectOption({ label: 'Drift' });
    await slots.nth(3).selectOption({ label: 'PosHold' });
    await dialog.getByRole('button', { name: label('fltmode.save') }).click();
    await onFc('FLTMODE2').toBe(11);
    await onFc('FLTMODE4').toBe(16);
    await close(page, dialog);

    // The bands printed beside each slot, as RC_Channel::read_6pos_switch cuts them.
    await holdSticks(1300, async () => expect.poll(() => probe.mode).toBe(11));
    await holdSticks(1560, async () => expect.poll(() => probe.mode).toBe(16));
    await holdSticks(1000, async () => expect.poll(() => probe.mode).toBe(await probe.param('FLTMODE1')));
  });
});

/** Holds the flight mode switch: an override lapses unless it keeps coming. */
async function holdSticks(ch5: number, check: () => Promise<void>) {
  const stick = setInterval(() => probe.sticks([0, 0, 0, 0, ch5, 0, 0, 0]), 200);
  try {
    await check();
  } finally {
    clearInterval(stick);
  }
}

test.describe('Failsafe', () => {
  const section = (page: Page, key: string) =>
    page.locator('div.rounded-lg.border-l-\\[3px\\]').filter({ hasText: label(key) });

  test('each section writes what it shows', async () => {
    const dialog = await tool(page, 'tool-failsafe', label('failsafe.title'));

    const battery = section(page, 'failsafe.battery');
    if ((await battery.getByRole('switch').getAttribute('aria-checked')) === 'false') {
      await battery.getByRole('switch').click();
    }
    await battery.locator('#fs-batt-action').selectOption({ label: label('failsafe.actionRtl') });
    await battery.locator('#fs-batt-volt').fill('10.6');
    await battery.locator('#fs-batt-mah').fill('1200');
    await battery.getByRole('button', { name: label('failsafe.save') }).click();
    await onFc('BATT_FS_LOW_ACT').toBe(2);
    await expect.poll(() => probe.param('BATT_LOW_VOLT')).toBeCloseTo(10.6, 4);
    await onFc('BATT_LOW_MAH').toBe(1200);

    const rc = section(page, 'failsafe.rcLoss');
    await rc.locator('#fs-rc-action').selectOption({ label: label('failsafe.actionLand') });
    await rc.locator('#fs-rc-pwm').fill('950');
    await rc.getByRole('button', { name: label('failsafe.save') }).click();
    await onFc('FS_THR_ENABLE').toBe(3);
    await onFc('FS_THR_VALUE').toBe(950);

    const gcs = section(page, 'failsafe.gcsLoss');
    if ((await gcs.getByRole('switch').getAttribute('aria-checked')) === 'false') {
      await gcs.getByRole('switch').click();
    }
    await gcs.locator('#fs-gcs-action').selectOption({ label: label('failsafe.actionLand') });
    await gcs.getByRole('button', { name: label('failsafe.save') }).click();
    await onFc('FS_GCS_ENABLE').toBe(5);

    const ekf = section(page, 'failsafe.ekf');
    await ekf.locator('#fs-ekf-action').selectOption({ label: label('failsafe.actionAltHold') });
    await ekf.locator('#fs-ekf-thresh').fill('0.7');
    await ekf.getByRole('button', { name: label('failsafe.save') }).click();
    await onFc('FS_EKF_ACTION').toBe(2);
    await expect.poll(() => probe.param('FS_EKF_THRESH')).toBeCloseTo(0.7, 4);

    await close(page, dialog);
  });

  test('a switch turned off writes 0', async () => {
    const dialog = await tool(page, 'tool-failsafe', label('failsafe.title'));
    const gcs = section(page, 'failsafe.gcsLoss');
    await expect(gcs.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
    await gcs.getByRole('switch').click();
    await gcs.getByRole('button', { name: label('failsafe.save') }).click();
    await onFc('FS_GCS_ENABLE').toBe(0);
    await close(page, dialog);
  });

  test('every action on offer is one the firmware has', async () => {
    const dialog = await tool(page, 'tool-failsafe', label('failsafe.title'));
    const values = (id: string) =>
      dialog
        .locator(`${id} option`)
        .evaluateAll((options) => options.map((o) => Number((o as HTMLOptionElement).value)));
    // @Values of each parameter: ArduCopter/Parameters.cpp and AP_BattMonitor_Params.cpp.
    // 2 on the two loss failsafes is "removed in 4.0+": the FC takes it for an RTL on RC
    // loss (events.cpp:24) and refuses to arm on it for GCS loss (AP_Arming_Copter.cpp:216).
    expect(await values('#fs-batt-action')).toEqual([0, 1, 2, 3, 4, 5, 6, 7]);
    expect(await values('#fs-rc-action')).toEqual([0, 1, 3, 4, 5, 6, 7]);
    expect(await values('#fs-gcs-action')).toEqual([0, 1, 3, 4, 5, 6, 7]);
    expect(await values('#fs-ekf-action')).toEqual([0, 1, 2, 3]);
    await close(page, dialog);
  });
});

test.describe('PID', () => {
  test('a typed gain and a moved slider both land on the FC', async () => {
    const dialog = await tool(page, 'tool-pid', label('pid.title'));
    const row = (name: string) => dialog.locator('div.rounded-lg').filter({ hasText: name });

    const rollP = row('ATC_RAT_RLL_P').locator('input[type=number]');
    expect(Number(await rollP.inputValue())).toBeCloseTo(await probe.param('ATC_RAT_RLL_P'), 5);
    await rollP.fill('0.142');
    await rollP.press('Tab');
    await expect.poll(() => probe.param('ATC_RAT_RLL_P')).toBeCloseTo(0.142, 4);

    await dialog.getByRole('button', { name: label('pid.yaw') }).click();
    const yawD = await probe.param('ATC_RAT_YAW_D');
    const slider = row('ATC_RAT_YAW_D').locator('input[type=range]');
    await slider.focus();
    for (let i = 0; i < 3; i++) await slider.press('ArrowRight');
    await expect.poll(() => probe.param('ATC_RAT_YAW_D')).toBeCloseTo(yawD + 0.0003, 5);
    await close(page, dialog);
  });

  test('a gain may go as high as the firmware lets it', async () => {
    const dialog = await tool(page, 'tool-pid', label('pid.title'));
    const row = (name: string) => dialog.locator('div.rounded-lg').filter({ hasText: name });
    // @Range in libraries/AC_AttitudeControl/AC_AttitudeControl_Multi.cpp.
    const rollI = row('ATC_RAT_RLL_I').locator('input[type=number]');
    await rollI.fill('1.2');
    await rollI.press('Tab');
    await expect.poll(() => probe.param('ATC_RAT_RLL_I')).toBeCloseTo(1.2, 4);
    await dialog.getByRole('button', { name: label('pid.yaw') }).click();
    const yawP = row('ATC_RAT_YAW_P').locator('input[type=number]');
    await yawP.fill('0.9');
    await yawP.press('Tab');
    await expect.poll(() => probe.param('ATC_RAT_YAW_P')).toBeCloseTo(0.9, 4);
    await close(page, dialog);
  });
});

test.describe('Power', () => {
  test('a measured voltage corrects the FC reading', async () => {
    const dialog = await tool(page, 'tool-power', label('power.title'));
    const before = await probe.param('BATT_VOLT_MULT');
    await expect(dialog.getByText(before.toFixed(4))).toBeVisible();
    const reading = dialog.locator('p.text-lg').first();
    await expect.poll(async () => Number(await reading.textContent())).toBeGreaterThan(10);
    const shown = Number(await reading.textContent());
    const measured = Number((shown * 0.9).toFixed(2));
    await dialog.locator('#power-measured-volt').fill(String(measured));
    await dialog.getByRole('button', { name: label('power.calculate') }).click();
    await dialog.getByRole('button', { name: new RegExp(label('power.write')) }).first().click();
    await expect.poll(() => probe.param('BATT_VOLT_MULT')).toBeCloseTo((before * measured) / shown, 3);
    // The firmware now reads what the meter did.
    await expect.poll(async () => Number(await reading.textContent())).toBeCloseTo(measured, 1);
    await close(page, dialog);
  });

  test('offers nothing the firmware does not have', async () => {
    // BATT_N_CELLS is no parameter of any ArduPilot: the write went nowhere.
    await expect(probe.param('BATT_N_CELLS')).rejects.toThrow(/no answer/);
    const dialog = await tool(page, 'tool-power', label('power.title'));
    await expect(dialog.getByText('BATT_N_CELLS')).toHaveCount(0);
    await close(page, dialog);
  });

  test('a current scale is written', async () => {
    const dialog = await tool(page, 'tool-power', label('power.title'));
    await dialog.locator('#power-amp-pervlt').fill('21.5');
    await dialog.locator('#power-amp-pervlt').press('Tab');
    await dialog.locator('div.rounded-lg').filter({ hasText: 'BATT_AMP_PERVLT' }).getByRole('button').click();
    await expect.poll(() => probe.param('BATT_AMP_PERVLT')).toBeCloseTo(21.5, 3);
    await close(page, dialog);
  });
});

test.describe('Frame', () => {
  const pick = (dialog: Locator, value: number, grid: 'class' | 'type') =>
    dialog
      .locator('div.grid')
      .nth(grid === 'class' ? 0 : 1)
      .getByRole('button')
      .filter({ hasText: new RegExp(`=${value}$`) })
      .click();

  test('writes the class and layout picked', async () => {
    const dialog = await tool(page, 'tool-frame', label('frame.title'));
    await expect(dialog.getByText('FRAME_CLASS=1', { exact: true })).toBeVisible();
    await pick(dialog, 2, 'class');
    await pick(dialog, 1, 'type');
    await dialog.getByRole('button', { name: label('frame.write') }).click();
    await onFc('FRAME_CLASS').toBe(2);
    await onFc('FRAME_TYPE').toBe(1);
    await expect(dialog.getByText('FRAME_CLASS=2', { exact: true })).toBeVisible();

    await pick(dialog, 1, 'class');
    await pick(dialog, 0, 'type');
    await dialog.getByRole('button', { name: label('frame.write') }).click();
    await onFc('FRAME_CLASS').toBe(1);
    await onFc('FRAME_TYPE').toBe(0);
    await close(page, dialog);
  });

  test('a class on the FC is the one the firmware calls by that number', async () => {
    const dialog = await tool(page, 'tool-frame', label('frame.title'));
    // @Values of FRAME_CLASS, ArduCopter/Parameters.cpp:689.
    for (const [value, key] of [
      [1, 'frame.quad'],
      [2, 'frame.hexa'],
      [3, 'frame.octa'],
      [4, 'frame.octaQuad'],
      [5, 'frame.y6'],
      [7, 'frame.tri'],
      [8, 'frame.single'],
      [9, 'frame.coax'],
    ] as const) {
      const button = dialog
        .locator('div.grid')
        .first()
        .getByRole('button')
        .filter({ hasText: new RegExp(`=${value}$`) });
      await expect(button).toContainText(label(key));
    }
    await close(page, dialog);
  });

  test('a class only offers the layouts its motor matrix has', async () => {
    const dialog = await tool(page, 'tool-frame', label('frame.title'));
    const layouts = () => dialog.locator('div.grid').nth(1).getByRole('button').allTextContents();
    // FRAME_TYPE @Values, ArduCopter/Parameters.cpp:233.
    expect((await layouts()).map((l) => l.replace(/\s+/g, ' ').trim())).toEqual([
      '+ =0',
      'X =1',
      'V =2',
      'H =3',
      'V-Tail =4',
      'A-Tail =5',
      'BetaFlight X =12',
      'DJI X =13',
      'CW X =14',
      'Y4 =19',
    ]);
    await pick(dialog, 5, 'class');
    expect((await layouts()).map((l) => l.replace(/\s+/g, ' ').trim())).toEqual(['Y6B =10', 'Y6F =11']);

    // The layout follows: X on a Y6 would leave the FC refusing to arm.
    await dialog.getByRole('button', { name: label('frame.write') }).click();
    await onFc('FRAME_CLASS').toBe(5);
    await onFc('FRAME_TYPE').toBe(10);

    await pick(dialog, 7, 'class');
    await expect(dialog.locator('div.grid')).toHaveCount(1);

    await pick(dialog, 1, 'class');
    await pick(dialog, 0, 'type');
    await dialog.getByRole('button', { name: label('frame.write') }).click();
    await onFc('FRAME_CLASS').toBe(1);
    await onFc('FRAME_TYPE').toBe(0);
    await close(page, dialog);
  });
});

test.describe('Parameter file', () => {
  const file = path.join(tmpdir(), `argus-diff-${process.pid}.param`);

  test('export, edit, compare and apply', async () => {
    await page.locator('nav button', { hasText: label('tab.params') }).click();
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: label('param.export'), exact: true }).click(),
    ]);
    const exported = readFileSync(await download.path(), 'utf-8');
    const lines = exported.split('\n');
    expect(lines).toHaveLength(await probe.paramCount());

    // Relative to what the FC holds, so that the spec can run twice on one SITL.
    const set = async (name: string, change: number) => {
      const at = lines.findIndex((l) => l.startsWith(`${name}\t`));
      expect(at).toBeGreaterThanOrEqual(0);
      const value = (await probe.param(name)) + change;
      lines[at] = `${name}\t${value}`;
      return value;
    };
    const speed = await set('WPNAV_SPEED', 50);
    const rtlAlt = await set('RTL_ALT', 100);
    const angle = await set('ANGLE_MAX', 100);
    lines.push('NOT_ON_THIS_FC\t1');
    writeFileSync(file, lines.join('\n'));

    const dialog = await tool(page, 'tool-paramdiff', label('paramdiff.title'));
    const [chooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      dialog.getByRole('button', { name: label('paramdiff.loadFile') }).click(),
    ]);
    await chooser.setFiles(file);
    await expect(dialog.getByText(label('paramdiff.count').replace('{n}', '3'))).toBeVisible();

    const row = (name: string) => dialog.locator('div.flex.items-center').filter({ hasText: name }).last();
    await expect(row('WPNAV_SPEED')).toContainText(String(speed));
    await expect(row('RTL_ALT')).toContainText(String(rtlAlt));

    // One on its own, the rest together, and nothing else moves.
    await row('WPNAV_SPEED').getByRole('button', { name: label('paramdiff.apply') }).click();
    await onFc('WPNAV_SPEED').toBe(speed);
    expect(await probe.param('RTL_ALT')).toBe(rtlAlt - 100);
    expect(await probe.param('ANGLE_MAX')).toBe(angle - 100);

    await dialog.getByRole('button', { name: label('paramdiff.applyAll') }).click();
    await onFc('RTL_ALT').toBe(rtlAlt);
    await onFc('ANGLE_MAX').toBe(angle);

    await dialog.locator('button', { hasText: label('paramdiff.onlyFile') }).click();
    await expect(dialog.getByText('NOT_ON_THIS_FC')).toBeVisible();
    await dialog.getByRole('button').first().click();
  });
});

test.describe('AutoTune', () => {
  test('stays shut while disarmed', async () => {
    const dialog = await tool(page, 'tool-autotune', label('autotune.title'));
    await expect(dialog.getByText('AUTOTUNE_AXES').locator('xpath=following-sibling::span')).toHaveText(
      String(await probe.param('AUTOTUNE_AXES')),
    );
    await expect(dialog.getByRole('button', { name: label('autotune.start') })).toBeDisabled();
    await close(page, dialog);
  });
});

test.describe('Before the parameters are read', () => {
  test('an open panel picks the values up when they arrive', async ({ browser }) => {
    await page.close();
    page = await browser.newPage(); // has read nothing, as after a reload
    await connect(page);
    const mult = await probe.param('BATT_VOLT_MULT');
    const power = await tool(page, 'tool-power', label('power.title'));
    await expect(power.getByText(mult.toFixed(4))).toHaveCount(0);
    await palette(page, 'param-read');
    await expect(power.getByText(mult.toFixed(4))).toBeVisible();
    await close(page, power);
  });
});
