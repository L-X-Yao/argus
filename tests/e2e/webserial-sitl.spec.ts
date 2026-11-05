import { test, expect, type Page } from '@playwright/test';
import { openBridge, connectUsb, droneField, dispatchCmd, type Bridge } from './sitl-bridge';

// The WebSerial stack against real ArduPilot firmware, one session end to end.
// Needs SITL_TCP (a running ArduCopter SITL) and the Vite dev server.
const SITL = process.env.SITL_TCP;
test.skip(!SITL, 'SITL_TCP is not set');
test.use({ baseURL: process.env.VITE_URL ?? 'http://localhost:5173' });
test.describe.configure({ mode: 'serial', timeout: 180000, retries: 0 });

const MODE = { guided: 4, auto: 3, rtl: 6, land: 9 };
const ACCEPTED = 0;
const FAILED = 4;

let page: Page;
let sitl: Bridge;

const drone = <T = number>(key: string) => droneField<T>(page, key);
const send = (name: string, param?: number, data?: Record<string, unknown>) => dispatchCmd(page, name, param, data);

/** Sends a command and waits for the firmware's final answer to it. */
async function ackOf(
  command: number,
  name: string,
  data?: Record<string, unknown>,
  param?: number,
): Promise<number | undefined> {
  const mark = sitl.acks.length;
  await send(name, param, data);
  await expect
    .poll(() => sitl.acks.slice(mark).find((a) => a.command === command && a.result !== 5)?.result, {
      message: `no COMMAND_ACK ${command} after ${name}`,
      timeout: 20000,
    })
    .not.toBeUndefined();
  return sitl.acks.slice(mark).find((a) => a.command === command && a.result !== 5)?.result;
}

async function setMode(id: number) {
  await send('mode', id);
  await expect.poll(() => drone('mode_id'), { message: `mode ${id}`, timeout: 15000 }).toBe(id);
}

async function armWhenReady() {
  await expect
    .poll(
      async () => {
        await send('arm');
        await page.waitForTimeout(1500);
        return drone<boolean>('armed');
      },
      { message: 'arm', timeout: 90000, intervals: [500] },
    )
    .toBe(true);
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  sitl = await openBridge(page, SITL!);
  await connectUsb(page);
  await expect.poll(() => drone<boolean>('connected'), { timeout: 30000 }).toBe(true);
  await expect.poll(() => drone('gps_fix_raw'), { timeout: 120000 }).toBeGreaterThanOrEqual(3);
});

test.afterAll(async () => {
  sitl?.close();
  await page?.close();
});

async function openFromPalette(title: string) {
  await page.keyboard.press('Control+k');
  await page.locator('input[placeholder]').last().fill(title);
  await page.waitForTimeout(300);
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: title })).toBeVisible({ timeout: 5000 });
}

test('the position source panel shows a healthy GPS and EKF', async () => {
  await expect.poll(() => drone('ekf_flags'), { timeout: 60000 }).toBeGreaterThan(0);
  await openFromPalette('定位源');
  await expect(page.getByText(/\| \d+ sats/)).toBeVisible();
  await expect(page.getByText(/flags: 0x[0-9a-f]+/)).toBeVisible();
  await page.keyboard.press('Escape');
  await page.mouse.click(5, 5);
});

test('the custom dashboard shows live values', async () => {
  await openFromPalette('自定义仪表盘');
  const dashboard = page.getByRole('dialog').filter({ hasText: '自定义仪表盘' });
  // A live tile: the satellite count stays 0 unless telemetry reaches the panel.
  const sats = dashboard.getByText('卫星数', { exact: true }).locator('xpath=following-sibling::div[1]');
  await expect.poll(async () => Number(await sats.textContent())).toBeGreaterThan(0);
  await page.mouse.click(5, 5);
});

test('the FC sends what rides no stream once asked', async () => {
  expect(sitl.acks.find((a) => a.command === 511)?.result).toBe(ACCEPTED);
  expect(sitl.acks.filter((a) => a.command === 512).map((a) => a.result)).toEqual([ACCEPTED, ACCEPTED]);
  await expect.poll(() => sitl.seen(245), { timeout: 10000 }).toBe(true);
  await expect.poll(() => drone('vtol_state'), { timeout: 5000 }).toBe(3); // MC, on any Copter
});

test('a refused mode change shows an error', async () => {
  // Copter has no mode 8 (ArduCopter/mode.h). Disarmed it takes every mode it has
  // (ArduCopter/mode.cpp set_mode, ignore_checks), so an unknown one is the refusal to test.
  expect(await ackOf(176, 'mode', undefined, 8)).toBe(FAILED);
  await expect(page.getByText(/模式 — 失败|Mode — failed/).first()).toBeVisible();
});

test('a refused arm shows an error', async () => {
  // LAND cannot be armed in: ArduCopter/mode.h ModeLand::allows_arming.
  await setMode(MODE.land);
  expect(await ackOf(400, 'arm')).toBe(FAILED);
  await expect(page.getByText(/解锁\/锁定 — 失败|Arm\/Disarm — failed/).first()).toBeVisible();
});

test('arms, takes off and flies to a point', async () => {
  await setMode(MODE.guided);
  await armWhenReady();
  expect(await ackOf(22, 'takeoff', { alt: 20 })).toBe(ACCEPTED);
  await expect.poll(() => drone('alt_rel'), { timeout: 60000 }).toBeGreaterThan(15);

  const lat = await drone('lat');
  const lon = await drone('lon');
  await send('guided_goto', undefined, { lat: lat + 0.0008, lon, alt: 20 });
  await expect.poll(() => drone('lat'), { timeout: 60000 }).toBeGreaterThan(lat + 0.0004);
});

test('the flight fills in the derived fields', async () => {
  await expect.poll(() => drone('dist_home'), { timeout: 15000 }).toBeGreaterThan(30);
  await expect.poll(() => drone('flight_time'), { timeout: 15000 }).toBeGreaterThan(0);
  expect((await drone<number[]>('servo'))[0]).toBeGreaterThan(1000);
  expect(await drone<string>('fw_version')).toMatch(/^v\d+\.\d+\.\d+$/);
  expect((await drone<number[]>('cells'))[0]).toBeGreaterThan(0);
  // The wording varies by firmware version: LAND on 4.6, Land on 4.7.
  expect((await drone<string[]>('prearm')).join(' ')).toMatch(/not armable/i);
  expect(Math.abs((await drone<number[]>('mag'))[2])).toBeGreaterThan(0);
  expect((await drone<number[]>('vibe')).some((v) => v > 0)).toBe(true);
  await expect.poll(() => drone('gimbal_pitch'), { timeout: 10000 }).not.toBe(0);
});

test('a right click on the map sends the vehicle there and marks the target', async () => {
  const map = (await page.locator('.leaflet-container').first().boundingBox())!;
  await page.mouse.click(map.x + map.width / 2 + 120, map.y + map.height / 2 + 80, { button: 'right' });
  const dialog = page.getByRole('alertdialog');
  await expect(dialog).toBeVisible();
  await page.waitForTimeout(350); // resolveConfirm ignores a yes in the first 300 ms
  await dialog.getByRole('button', { name: /确认|Confirm/ }).click();
  await expect(page.locator('path.guided-pulse')).toBeAttached({ timeout: 5000 });
  await expect.poll(() => drone('mode_id'), { timeout: 15000 }).toBe(MODE.guided);
  // The takeoff already left it in GUIDED and the marker is local, so only the vehicle
  // moving shows that the FC took the target.
  await expect.poll(() => drone('gs'), { timeout: 20000 }).toBeGreaterThan(1);
});

test('survey and replay layers draw from their state', async () => {
  const shapes = () => page.locator('.leaflet-overlay-pane path').count();
  const arrows = () => page.locator('.drone-arrow').count();
  const [shapesBefore, arrowsBefore] = [await shapes(), await arrows()];
  await page.evaluate(async () => {
    const url = '/src/lib/stores.svelte.ts';
    const { app } = await import(/* @vite-ignore */ url);
    app.surveyPolygon = [
      { lat: 34.25, lon: 108.93 },
      { lat: 34.26, lon: 108.93 },
      { lat: 34.26, lon: 108.95 },
    ];
    app.replayPos = { lat: 34.25, lon: 108.93, yaw: 90 };
  });
  await expect.poll(shapes).toBeGreaterThan(shapesBefore);
  await expect.poll(arrows).toBe(arrowsBefore + 1);
  await page.evaluate(async () => {
    const url = '/src/lib/stores.svelte.ts';
    const { app } = await import(/* @vite-ignore */ url);
    app.surveyPolygon = [];
    app.replayPos = null;
  });
  await expect.poll(arrows).toBe(arrowsBefore);
});

test('flies an uploaded mission and jumps to a waypoint', async () => {
  const lat = await drone('lat');
  const lon = await drone('lon');
  const wp = (dLat: number, dLon: number) => ({
    lat: lat + dLat,
    lon: lon + dLon,
    alt: 20,
    drop: false,
    delay: 0,
    speed: 0,
    type: 'wp',
    loiter_param: 0,
  });
  const result = await page.evaluate(
    async (wps) => {
      const url = '/src/lib/transport.ts';
      const { serialUploadMission } = await import(/* @vite-ignore */ url);
      return serialUploadMission(wps, 20);
    },
    [wp(0.002, 0), wp(0.002, 0.002), wp(0, 0.002)],
  );
  expect(result).toEqual({ ok: true });

  await send('mission_start');
  await expect.poll(() => drone('mode_id'), { timeout: 15000 }).toBe(MODE.auto);

  await send('mission_set_current', undefined, { wp_index: 2 });
  await expect.poll(() => sitl.missionSeq(), { timeout: 15000 }).toBe(4);
  await expect.poll(() => drone('wp'), { timeout: 15000 }).toBe(4);
  expect(await drone('wp_idx')).toBe(2);
  await expect
    .poll(
      () =>
        page.evaluate(async () => {
          const url = '/src/lib/stores.svelte.ts';
          const { app } = await import(/* @vite-ignore */ url);
          return app.events.some((e: { event_type: string }) => e.event_type === 'wp_reached');
        }),
      { message: 'no waypoint reached', timeout: 60000 },
    )
    .toBe(true);
});

test('rally points reach the FC and clear again', async () => {
  const rally = 2; // MAV_MISSION_TYPE_RALLY
  const lat = await drone('lat');
  const lon = await drone('lon');
  const result = await page.evaluate(
    async (points) => {
      const url = '/src/lib/transport.ts';
      const { serialUploadRally } = await import(/* @vite-ignore */ url);
      return serialUploadRally(points);
    },
    [
      { lat: lat + 0.001, lon, alt: 50 },
      { lat, lon: lon + 0.001, alt: 40 },
    ],
  );
  expect(result).toEqual({ ok: true });
  expect(await sitl.storeCount(rally)).toBe(2);
  const first = await sitl.storeItem(rally, 0);
  expect(first?.lat).toBeCloseTo(lat + 0.001, 5);
  expect(first?.lon).toBeCloseTo(lon, 5);
  expect(first?.alt).toBe(50);
  const second = await sitl.storeItem(rally, 1);
  expect(second?.lon).toBeCloseTo(lon + 0.001, 5);
  expect(second?.alt).toBe(40);

  const cleared = await page.evaluate(async () => {
    const url = '/src/lib/transport.ts';
    const { serialClearRally } = await import(/* @vite-ignore */ url);
    return serialClearRally();
  });
  expect(cleared).toEqual({ ok: true });
  expect(await sitl.storeCount(rally)).toBe(0);
});

test('returns and lands, and reports the flight', async () => {
  await send('rtl');
  await expect.poll(() => drone('mode_id'), { timeout: 15000 }).toBe(MODE.rtl);
  await expect.poll(() => drone<boolean>('armed'), { timeout: 150000 }).toBe(false);
  const summary = await drone<{ max_alt: number; total_dist: number }>('flight_summary');
  expect(summary.max_alt).toBeGreaterThan(15);
  expect(summary.total_dist).toBeGreaterThan(50);
});

test('disarms, and force disarms', async () => {
  await setMode(MODE.guided);
  await armWhenReady();
  expect(await ackOf(400, 'disarm')).toBe(ACCEPTED);
  await expect.poll(() => drone<boolean>('armed'), { timeout: 15000 }).toBe(false);

  await armWhenReady();
  expect(await ackOf(400, 'force_disarm')).toBe(ACCEPTED);
  await expect.poll(() => drone<boolean>('armed'), { timeout: 15000 }).toBe(false);
});

test('RC override reaches the channels', async () => {
  const channels = [1500, 1500, 1000, 1500, 1800, 1500, 1500, 1500];
  await expect
    .poll(
      async () => {
        await send('rc_override', undefined, { channels });
        return (await drone<number[]>('rc'))[4];
      },
      { timeout: 15000 },
    )
    .toBe(1800);
  await send('rc_override', undefined, { channels: [0, 0, 0, 0, 0, 0, 0, 0] });
});

for (const [name, command, data] of [
  ['motor_test', 209, { motor: 0, throttle: 5, duration: 1 }],
  ['motor_test_stop', 209, undefined],
  ['drop', 181, undefined],
  ['drop_stop', 181, undefined],
  ['do_set_roi', 201, { lat: -35.36, lon: 149.16, alt: 10 }],
  ['camera_trigger', 203, undefined],
  ['cal_gyro', 241, undefined],
  ['cal_level', 241, undefined],
  ['cal_baro', 241, undefined],
  ['cal_compass', 42424, undefined],
  ['cal_cancel', 42426, undefined],
] as const) {
  test(`${name} is accepted`, async () => {
    expect(await ackOf(command, name, data)).toBe(ACCEPTED);
  });
}

// tests/e2e/sitl-gimbal.parm gives SITL a servo gimbal.
for (const [name, command, data] of [
  ['gimbal_angle', 205, { pitch: -10, yaw: 0 }],
  ['gimbal_pitchyaw', 1000, { pitch: -20, yaw: 10 }],
] as const) {
  test(`${name} is accepted`, async () => {
    expect(await ackOf(command, name, data)).toBe(ACCEPTED);
  });
}

// No camera is simulated, so the firmware refuses these. An answer still shows
// the frame reached it and was understood.
for (const [name, command, data] of [
  ['camera_video_start', 2500, undefined],
  ['camera_video_stop', 2501, undefined],
  ['camera_zoom', 531, { zoom: 2 }],
] as const) {
  test(`${name} gets an answer`, async () => {
    expect(await ackOf(command, name, data)).not.toBeUndefined();
  });
}

test('log_cancel stops a download', async () => {
  const listed = await page.evaluate(async () => {
    const url = '/src/lib/transport.ts';
    const { serialLogList } = await import(/* @vite-ignore */ url);
    return serialLogList();
  });
  expect(listed).toEqual({ ok: true });
  expect(sitl.logIds.length).toBeGreaterThan(0);

  const id = sitl.logIds[sitl.logIds.length - 1];
  await page.evaluate(async (log) => {
    const url = '/src/lib/transport.ts';
    const { serialLogDownload } = await import(/* @vite-ignore */ url);
    void serialLogDownload(log);
  }, id);
  await expect.poll(() => sitl.logDataFrames(), { timeout: 15000 }).toBeGreaterThan(0);

  await send('log_cancel');
  await page.waitForTimeout(1500);
  const settled = sitl.logDataFrames();
  await page.waitForTimeout(1500);
  expect(sitl.logDataFrames()).toBe(settled);
});

test('reboot is accepted', async () => {
  expect(await ackOf(246, 'reboot')).toBe(ACCEPTED);
});
