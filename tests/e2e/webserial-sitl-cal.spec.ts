import { test, expect, type Page } from '@playwright/test';
import net from 'node:net';
import { encodeCommandLong, encodeFrame } from '../../src/lib/mavlink';
import { openBridge, connectUsb, droneField, dispatchCmd, type Bridge } from './sitl-bridge';

// The two interactive calibrations over WebSerial, on real firmware. Needs SITL
// running the `calibration` model (libraries/SITL/SIM_Calibration.cpp), SITL_TCP
// on SERIAL0 and SITL_DRIVER_TCP on SERIAL1, which turns the simulated vehicle.
const SITL = process.env.SITL_TCP;
const DRIVER = process.env.SITL_DRIVER_TCP;
test.skip(!SITL || !DRIVER, 'SITL_TCP and SITL_DRIVER_TCP are not set');
test.use({ baseURL: process.env.VITE_URL ?? 'http://localhost:5173' });
test.describe.configure({ mode: 'serial', timeout: 300000, retries: 0 });

const MAV_CMD_DO_SET_SERVO = 183;
const ACCEPTED = 0;

// Tools/mavproxy_modules/sitl_calibration.py AccelcalController.state_data,
// keyed by the word AP_AccelCal prints in "Place vehicle %s and press any key."
const POSES: [string, number, number][] = [
  ['LEFT', -Math.PI / 2, 0],
  ['RIGHT', Math.PI / 2, 0],
  ['DOWN', 0, -Math.PI / 2],
  ['UP', 0, Math.PI / 2],
  ['BACK', Math.PI, 0],
  ['level', 0, 0],
];

let page: Page;
let sitl: Bridge;
let driver: net.Socket;
let driverSeq = 0;

// Servo semantics per SIM_Calibration.cpp update(): servo5 <1100 stop, 1100-1199
// attitude from servos 6-8, 1200-1299 autonomous calibration poses.
function servo(channel: number, pwm: number) {
  const payload = encodeCommandLong(1, 1, MAV_CMD_DO_SET_SERVO, 0, channel, pwm, 0, 0, 0, 0, 0);
  driver.write(encodeFrame(76, payload, 250, 190, driverSeq++ & 0xff));
}

// PWM encoding per sitl_calibration.py set_attitute().
function setAttitude(roll: number, pitch: number) {
  const pwm = (angle: number) => 1500 + Math.trunc(angle * (500 / Math.PI));
  servo(5, 1150);
  servo(6, pwm(roll));
  servo(7, pwm(pitch));
  servo(8, 1500);
}

async function ackOf(command: number, name: string): Promise<number | undefined> {
  const mark = sitl.acks.length;
  await dispatchCmd(page, name);
  const answer = () => sitl.acks.slice(mark).find((a) => a.command === command && a.result !== 5)?.result;
  await expect.poll(answer, { message: `no COMMAND_ACK ${command} after ${name}`, timeout: 20000 }).not.toBeUndefined();
  return answer();
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(240000);
  const [host, port] = DRIVER!.split(':');
  driver = net.connect(Number(port), host);
  await new Promise((ok, fail) => driver.once('connect', ok).once('error', fail));
  page = await browser.newPage();
  sitl = await openBridge(page, SITL!);
  await connectUsb(page);
  await expect.poll(() => droneField(page, 'connected'), { timeout: 30000 }).toBe(true);
});

test.afterAll(async () => {
  driver?.destroy();
  sitl?.close();
  await page?.close();
});

test('compass calibration runs to the end and is accepted', async () => {
  test.setTimeout(600000);
  const events = () =>
    page.evaluate(async () => {
      const url = '/src/lib/stores.svelte.ts';
      const { app } = await import(/* @vite-ignore */ url);
      return app.events.map((e: { event_type: string; text: string }) => `${e.event_type}|${e.text}`);
    });
  const results = async () =>
    (await events()).filter((e: string) => /^cal_compass\|.*(完成|complete|失败|FAILED)/.test(e));
  const forget = () =>
    page.evaluate(async () => {
      const url = '/src/lib/stores.svelte.ts';
      const { app } = await import(/* @vite-ignore */ url);
      app.events.length = 0;
    });
  // The firmware's own fit on simulated samples can fail on a busy runner. MAG_CAL_REPORT says
  // so, Argus is right to show it, and a user would run it again.
  for (let run = 1; ; run++) {
    await forget();
    expect(await ackOf(42424, 'cal_compass')).toBe(ACCEPTED);
    servo(5, 1250);
    await expect
      .poll(async () => (await results()).length, {
        message: 'no MAG_CAL_REPORT result',
        timeout: 240000,
        intervals: [2000],
      })
      .toBeGreaterThan(0);
    const result = (await results()).join(' ');
    if (/完成|complete/.test(result)) break;
    console.log(`compass run ${run}: ${result} after: ${sitl.texts.slice(-8).join(' / ')}`);
    servo(5, 1000);
    expect(run, 'the FC failed the fit on both runs').toBeLessThan(2);
  }
  // The link accepts by itself, and the FC answers ACCEPTED only if every compass had
  // finished: one still running fails the command (AP_Compass_Calibration.cpp:233).
  const accepted = () => sitl.acks.find((a) => a.command === 42425)?.result;
  await expect.poll(accepted, { message: 'no COMMAND_ACK 42425', timeout: 20000 }).toBe(ACCEPTED);
  servo(5, 1000);
});

test('accelerometer calibration goes through all six poses', async () => {
  await dispatchCmd(page, 'cal_accel');
  const done = new Set<string>();
  let read = sitl.texts.length;
  await expect
    .poll(
      async () => {
        for (; read < sitl.texts.length; read++) {
          const text = sitl.texts[read];
          if (text.includes('successful') || text.includes('FAILED')) return text;
          if (!text.includes('Place vehicle')) continue;
          const pose = POSES.find(([word]) => text.includes(word));
          if (!pose || done.has(pose[0])) continue;
          done.add(pose[0]);
          setAttitude(pose[1], pose[2]);
          await page.waitForTimeout(3000);
          await dispatchCmd(page, 'cal_accel_next');
        }
        return '';
      },
      { message: `accel cal stopped after ${[...done]}`, timeout: 240000, intervals: [500] },
    )
    .toMatch(/successful/);
  expect(done.size).toBe(6);
  servo(5, 1000);
});

test('reboot to bootloader is accepted', async () => {
  expect(await ackOf(246, 'reboot_bootloader')).toBe(ACCEPTED);
});
