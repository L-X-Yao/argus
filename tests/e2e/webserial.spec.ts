import { test, expect, type Page } from '@playwright/test';

// A real MAVLink 2 HEARTBEAT: quadrotor, ArduPilot, disarmed, sysid 1.
const HEARTBEAT = [253, 9, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 2, 3, 81, 3, 3, 226, 146];

// The WebSerial path never touches the backend, and the simulator can't reach
// it, so nothing exercised it until it met a real FC: there the Disconnect
// button did nothing and link_age stayed at -1. This fake port stands in for
// the hardware so those failures show up in CI.
async function fakeSerialPort(page: Page) {
  await page.addInitScript((frame) => {
    const fake = { closed: false, silent: false, opens: 0 };
    (window as unknown as { __serial: typeof fake }).__serial = fake;
    let timer: ReturnType<typeof setInterval>;
    const newReadable = () =>
      new ReadableStream<Uint8Array>({
        start(controller) {
          timer = setInterval(() => {
            if (!fake.silent) controller.enqueue(new Uint8Array(frame));
          }, 100);
        },
        cancel() {
          clearInterval(timer);
        },
      });
    const port = {
      readable: null as ReadableStream<Uint8Array> | null,
      writable: null as WritableStream<Uint8Array> | null,
      getInfo: () => ({ usbVendorId: 0x1209, usbProductId: 0x5740 }),
      async open() {
        fake.opens += 1;
        fake.closed = false;
        port.readable = newReadable();
        port.writable = new WritableStream<Uint8Array>();
      },
      // Like Chrome: a port cannot close while its stream is locked.
      async close() {
        if (port.readable?.locked) throw new TypeError('Cannot close a locked stream');
        fake.closed = true;
      },
    };
    Object.defineProperty(navigator, 'serial', {
      configurable: true,
      value: { requestPort: async () => port, getPorts: async () => [port] },
    });
  }, HEARTBEAT);
}

const disconnectButton = (page: Page) => page.locator('button', { hasText: /^断开$|^Disconnect$/ });
const usbButton = (page: Page) => page.locator('button', { hasText: /^USB$/ });
const linkIndicator = (page: Page) => page.locator('[title^="Link "]');
const fakeState = (page: Page) =>
  page.evaluate(() => (window as unknown as { __serial: { closed: boolean; opens: number } }).__serial);

test.describe('WebSerial session', () => {
  test.beforeEach(async ({ page }) => {
    await fakeSerialPort(page);
    await page.goto('/');
    await usbButton(page).click();
    await expect(disconnectButton(page)).toBeVisible({ timeout: 10000 });
  });

  test('Disconnect button closes the port', async ({ page }) => {
    await disconnectButton(page).click();
    await expect(page.locator('button', { hasText: /^连接$|^Connect$/ })).toBeVisible();
    await expect(usbButton(page)).toBeVisible();
    await expect.poll(() => fakeState(page).then((f) => f.closed)).toBe(true);
    // Frames still arriving would flip the page back to connected.
    await page.waitForTimeout(1500);
    await expect(disconnectButton(page)).toHaveCount(0);
  });

  test('USB connects again after a disconnect', async ({ page }) => {
    await disconnectButton(page).click();
    await expect(usbButton(page)).toBeVisible();
    await usbButton(page).click();
    await expect(disconnectButton(page)).toBeVisible({ timeout: 10000 });
    expect((await fakeState(page)).opens).toBe(2);
  });

  test('link indicator shows a live link', async ({ page }) => {
    await expect(linkIndicator(page)).toHaveAttribute('title', /^Link 0\.\ds/, { timeout: 5000 });
  });

  test('link age climbs past the alarm threshold when frames stop', async ({ page }) => {
    await expect(linkIndicator(page)).toHaveAttribute('title', /^Link 0\.\ds/, { timeout: 5000 });
    await page.evaluate(() => {
      (window as unknown as { __serial: { silent: boolean } }).__serial.silent = true;
    });
    await expect(linkIndicator(page)).toHaveAttribute('title', /^Link ([3-9]|\d\d)\.\ds/, { timeout: 8000 });
  });
});
