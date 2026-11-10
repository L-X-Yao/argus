import { test, expect, type Page } from '@playwright/test';
import { openBridge, connectUsb, droneField, dispatchCmd, type Bridge } from './sitl-bridge';

// Two links unit tests can only imitate, on real ArduPilot firmware: a vehicle that is
// not system 1 (tests/e2e/sitl-sysid.parm), and a USB cable that goes away in the air.
// Needs SITL_TCP and the Vite dev server, like webserial-sitl.spec.ts.
const SITL = process.env.SITL_TCP;
test.skip(!SITL, 'SITL_TCP is not set');
test.use({ baseURL: process.env.VITE_URL ?? 'http://localhost:5173' });
test.describe.configure({ mode: 'serial', timeout: 180000, retries: 0 });

const SYSID = 7;
const GUIDED = 4;
const RTL = 6;
const ACCEPTED = 0;
const MISSION = 0; // MAV_MISSION_TYPE_MISSION

let page: Page;
let sitl: Bridge;

const drone = <T = number>(key: string) => droneField<T>(page, key);
const send = (name: string, param?: number, data?: Record<string, unknown>) => dispatchCmd(page, name, param, data);

const eventCount = (type: string) =>
  page.evaluate(async (t) => {
    const url = '/src/lib/stores.svelte.ts';
    const { app } = await import(/* @vite-ignore */ url);
    return app.events.filter((e: { event_type: string }) => e.event_type === t).length;
  }, type);

const linkLost = () =>
  page.evaluate(async () => {
    const url = '/src/lib/stores.svelte.ts';
    const { app } = await import(/* @vite-ignore */ url);
    return app.serialLinkLost as boolean;
  });

const store = <T>(body: string) =>
  page.evaluate(async (code) => {
    const url = '/src/lib/stores.svelte.ts';
    const { app } = await import(/* @vite-ignore */ url);
    return new Function('app', code)(app) as T;
  }, body);

test.beforeAll(async ({ browser }) => {
  test.setTimeout(240000);
  page = await browser.newPage();
  sitl = await openBridge(page, SITL!, SYSID);
  // Voice and a gamepad, as far as a headless browser has them: what the app says, and
  // a stick it can read. What they do with them is the app's own code.
  await page.addInitScript(() => {
    const w = window as unknown as { __spoken: string[]; __axes: number[] };
    w.__spoken = [];
    w.__axes = [0, 0, 0, 0];
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      value: { pending: false, cancel() {}, speak: (u: { text: string }) => w.__spoken.push(u.text) },
    });
    (window as unknown as { SpeechSynthesisUtterance: unknown }).SpeechSynthesisUtterance = class {
      lang = '';
      rate = 1;
      volume = 1;
      constructor(public text: string) {}
    };
    navigator.getGamepads = () =>
      [{ id: 'test pad', index: 0, connected: true, axes: w.__axes, buttons: [] }] as unknown as Gamepad[];
  });
  await connectUsb(page);
  await expect.poll(() => drone<boolean>('connected'), { timeout: 30000 }).toBe(true);
  await expect.poll(() => drone('gps_fix_raw'), { timeout: 120000 }).toBeGreaterThanOrEqual(3);
});

test.afterAll(async () => {
  sitl?.close();
  await page?.close();
});

test('voice alerts are on', async () => {
  await store<void>('app.voiceEnabled = true');
});

test('a vehicle that is not system 1 answers what connecting asks of it', async () => {
  // These ride no stream, so they only arrive if the requests reached system 7.
  await expect.poll(() => sitl.acks.find((a) => a.command === 511)?.result, { timeout: 10000 }).toBe(ACCEPTED);
  await expect.poll(() => drone('vtol_state'), { timeout: 10000 }).toBe(3);
  await expect.poll(() => drone<string>('fw_version'), { timeout: 10000 }).toMatch(/^v\d+\.\d+\.\d+$/);
  await expect.poll(() => drone('home_lat'), { timeout: 60000 }).not.toBe(0);
});

test('its mission store takes an upload', async () => {
  const lat = await drone('lat');
  const lon = await drone('lon');
  const wp = (dLat: number) => ({
    lat: lat + dLat,
    lon,
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
    [wp(0.001), wp(0.002)],
  );
  expect(result).toEqual({ ok: true });
  expect(await sitl.storeCount(MISSION)).toBeGreaterThanOrEqual(3);
});

test('a link that loses one frame in ten still moves a mission and a mode change', async () => {
  const lat = await drone('lat');
  const lon = await drone('lon');
  const wps = Array.from({ length: 20 }, (_, i) => ({
    lat: lat + 0.0002 * (i + 1),
    lon,
    alt: 20,
    drop: false,
    delay: 0,
    speed: 0,
    type: 'wp',
    loiter_param: 0,
  }));
  sitl.setLoss(0.1);
  try {
    const uploaded = await page.evaluate(async (w) => {
      const url = '/src/lib/transport.ts';
      const { serialUploadMission } = await import(/* @vite-ignore */ url);
      return serialUploadMission(w, 20);
    }, wps);
    expect(uploaded).toEqual({ ok: true });

    const downloaded = await page.evaluate(async () => {
      const url = '/src/lib/transport.ts';
      const { serialDownloadMission } = await import(/* @vite-ignore */ url);
      return serialDownloadMission();
    });
    expect(downloaded.ok).toBe(true);
    expect(downloaded.waypoints.length).toBe(wps.length);

    // Loiter is refused until the estimator has a position (ArduCopter/mode.cpp:398
    // "requires position"), which comes some seconds after the GPS fix beforeAll waits for:
    // on a runner that reached this line sooner, the mode stayed where it was.
    await expect.poll(async () => (await drone('ekf_flags')) & 0x10, { timeout: 60000 }).toBeTruthy();
    await send('mode', 5);
    await expect.poll(() => drone('mode_id'), { timeout: 15000 }).toBe(5);
  } finally {
    sitl.setLoss(0);
  }
});

test('it arms and takes off', async () => {
  await send('mode', GUIDED);
  await expect.poll(() => drone('mode_id'), { timeout: 15000 }).toBe(GUIDED);
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
  await send('takeoff', undefined, { alt: 20 });
  await expect.poll(() => drone('alt_rel'), { timeout: 60000 }).toBeGreaterThan(15);
});

test('the voice says the vehicle armed', async () => {
  const spoken = () => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);
  expect(await spoken()).toContain('已解锁');
});

test('a gamepad moves the channels on the FC', async () => {
  const startGamepad = () =>
    page.evaluate(async () => {
      const url = '/src/lib/gamepad.svelte.ts';
      const { startGamepad: start } = await import(/* @vite-ignore */ url);
      (window as unknown as { __axes: number[] }).__axes = [0.5, 0, 0, 0];
      start();
    });
  const stopGamepad = () =>
    page.evaluate(async () => {
      const url = '/src/lib/gamepad.svelte.ts';
      const { stopGamepad: stop } = await import(/* @vite-ignore */ url);
      stop();
    });
  await startGamepad();
  // Half a stick to the right, less the deadzone, as the firmware reads channel 1 back.
  await expect.poll(async () => (await drone<number[]>('rc'))[0], { timeout: 15000 }).toBeGreaterThan(1700);
  await stopGamepad();
  await send('rc_override', undefined, { channels: [0, 0, 0, 0, 0, 0, 0, 0] });
});

test('a USB drop in the air keeps the flight on screen and in the books', async () => {
  const homeLat = await drone('home_lat');
  const lat = await drone('lat');
  const flown = await drone('flight_time');
  expect(flown).toBeGreaterThan(0);

  await sitl.dropPort();
  await expect.poll(() => drone<boolean>('connected'), { timeout: 5000 }).toBe(false);
  expect(await linkLost()).toBe(true);
  await expect(page.getByText(/串口连接丢失|Serial connection lost/).first()).toBeVisible();

  // The backend beside it is idle and keeps pushing an empty state, which must not land.
  await page.waitForTimeout(3000);
  expect(await drone<boolean>('armed')).toBe(true);
  expect(await drone('home_lat')).toBe(homeLat);
  expect(await drone('lat')).toBe(lat);
  expect(await drone('flight_summary')).toBeNull();

  const acks = sitl.acks.length;
  await page.locator('button', { hasText: /^USB$/ }).click();
  await expect.poll(() => drone<boolean>('connected'), { timeout: 15000 }).toBe(true);
  expect(await linkLost()).toBe(false);
  // Back on the same flight: no new takeoff in the books, and the requests reached it again.
  await expect
    .poll(() => sitl.acks.slice(acks).find((a) => a.command === 511)?.result, { timeout: 10000 })
    .toBe(ACCEPTED);
  await expect.poll(() => drone('flight_time'), { timeout: 10000 }).toBeGreaterThan(flown);
  expect(await drone<boolean>('armed')).toBe(true);
  expect(await drone('alt_rel')).toBeGreaterThan(15);
  expect(await drone('flight_summary')).toBeNull();
  expect(await eventCount('armed')).toBe(1);
  expect(await eventCount('disarmed')).toBe(0);
});

test('the flight report counts the time before the drop', async () => {
  const flown = await drone('flight_time');
  await send('rtl');
  await expect.poll(() => drone('mode_id'), { timeout: 15000 }).toBe(RTL);
  await expect.poll(() => drone<boolean>('armed'), { timeout: 150000 }).toBe(false);
  const summary = await drone<{ duration: number; max_alt: number }>('flight_summary');
  expect(summary.max_alt).toBeGreaterThan(15);
  expect(summary.duration).toBeGreaterThanOrEqual(flown);
  expect(await eventCount('armed')).toBe(1);
});
