import { test, expect, type Locator, type Page } from '@playwright/test';
import { READY, label, openSession } from './panels-sitl-helpers';
import type { Probe } from './sitl-probe';
import { McpClient } from './mcp-client';

// The AI assistant's flight commands on real firmware: an MCP client proposes, the operator
// approves in the page and slides, and the vehicle's own heartbeat says what it did.
test.skip(!READY, 'run through tests/e2e/run-panels-sitl.sh');
test.describe.configure({ mode: 'serial' });

// ArduCopter/mode.h enum class Number
const GUIDED = 4;
const LOITER = 5;
const RTL = 6;
const LAND = 9;

let page: Page;
let probe: Probe;
let controls: Locator;
let mcp: McpClient;
let pilot: ReturnType<typeof setInterval> | undefined;
let home: { lat: number; lon: number };

/** Metres from where it took off. */
function fromHome(): number {
  const at = probe.position!;
  const north = (at.lat - home.lat) * 111320;
  const east = (at.lon - home.lon) * 111320 * Math.cos((home.lat * Math.PI) / 180);
  return Math.hypot(north, east);
}

/** The pilot's sticks, held: throttle in the middle, and pitch as given (0 lets it go). */
function hold(pitch = 0) {
  clearInterval(pilot);
  pilot = setInterval(() => probe.sticks([0, pitch, 1500, 0, 0, 0, 0, 0]), 100);
}

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

const button = (key: string) => controls.getByRole('button', { name: label(key), exact: true });

/** A flight command proposed, as the page puts it before the operator. */
async function propose(command: string): Promise<string> {
  const result = await mcp.call('propose_flight_command', { command, reason: `Test: ${command}` });
  expect(result.isError).toBe(false);
  expect(result.structuredContent.state).toBe('waiting');
  const box = page.getByTestId('assistant-dialog');
  await expect(box).toBeVisible();
  await expect(box.getByTestId('assistant-command')).toBeVisible();
  return result.structuredContent.proposal;
}

const check = async (proposal: string) =>
  (await mcp.call('check_proposal', { proposal, wait_seconds: 30 })).structuredContent;

/** Approve, once the button takes a click (the dialog waits a moment before it does). */
async function approve() {
  const approveButton = page.getByTestId('assistant-approve');
  await expect(approveButton).toBeEnabled();
  await approveButton.click();
}

test.beforeAll(async ({ browser }) => {
  ({ page, probe } = await openSession(browser));
  mcp = new McpClient(process.env.ARGUS_URL);
  await mcp.start();
  await expect
    .poll(() => (probe.position?.lat ?? 0) !== 0 && probe.position?.hdg !== undefined, { timeout: 120000 })
    .toBe(true);
  await page.getByRole('button', { name: label('nav.controls') }).click();
  controls = page.locator('div.w-44');
  await expect(controls).toBeVisible();
});

test.afterAll(async () => {
  clearInterval(pilot);
  mcp?.close();
  probe?.close();
  await page?.close();
});

test('on the ground and disarmed, a flight command is refused at once', async () => {
  const result = await mcp.call('propose_flight_command', { command: 'rtl' });
  expect(result.isError).toBe(true);
  expect(result.content[0].text).toContain('not armed');
  await expect(page.getByTestId('assistant-dialog')).toHaveCount(0);
});

test('armed and in the air', async () => {
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
  await controls.locator('input[type=number]').fill('15');
  await controls.locator('input[type=number]').press('Tab');
  await button('ctrl.takeoff').click();
  await slide();
  await expect.poll(() => probe.mode).toBe(GUIDED);
  await expect.poll(() => probe.altitude, { timeout: 60000 }).toBeGreaterThan(13);
  home = { lat: probe.position!.lat, lon: probe.position!.lon };
  // The pilot's throttle in the middle, or LOITER brings the vehicle down (see the flight spec).
  hold();
});

test('hold: approved, but a slide let go sends nothing, and a whole one does', async () => {
  const proposal = await propose('hold');
  await approve();
  await slide(0.5);
  await page.waitForTimeout(1500);
  expect(probe.mode).toBe(GUIDED);
  await page.keyboard.press('Escape');
  expect((await mcp.call('check_proposal', { proposal, wait_seconds: 0 })).structuredContent.state).toBe('waiting');

  await approve();
  await slide();
  await expect.poll(() => probe.mode).toBe(LOITER);
  expect(await check(proposal)).toMatchObject({ proposal, state: 'done', result: { mode: expect.any(String) } });
  await expect(page.getByTestId('assistant-dialog')).toHaveCount(0);
});

test('a declined command leaves the vehicle as it is', async () => {
  const proposal = await propose('land');
  await page.getByTestId('assistant-decline').click();
  expect(await check(proposal)).toMatchObject({ proposal, state: 'declined' });
  await page.waitForTimeout(1000);
  expect(probe.mode).toBe(LOITER);
});

test('the pilot flies it away, so that the way back takes a while', async () => {
  hold(1200); // pitch forward
  await expect.poll(fromHome, { timeout: 120000 }).toBeGreaterThan(300);
  hold();
});

test('rtl brings it back', async () => {
  const proposal = await propose('rtl');
  await approve();
  await slide();
  await expect.poll(() => probe.mode).toBe(RTL);
  expect(await check(proposal)).toMatchObject({ proposal, state: 'done' });
});

test('land puts it down where it is, on its way back, and it disarms', async () => {
  const proposal = await propose('land');
  await approve();
  await slide();
  await expect.poll(() => probe.mode).toBe(LAND);
  expect(await check(proposal)).toMatchObject({ proposal, state: 'done' });
  await expect.poll(() => probe.armed, { timeout: 180000 }).toBe(false);
  clearInterval(pilot);
  expect(probe.altitude).toBeLessThan(1);
  expect(fromHome()).toBeGreaterThan(20);
});
