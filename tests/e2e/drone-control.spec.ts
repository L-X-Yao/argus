import { test, expect } from '@playwright/test';
import { connectSimulator, disconnectIfConnected } from './helpers';

test.describe('Drone control (connected)', () => {
  test.beforeEach(async ({ page }) => {
    await connectSimulator(page);
  });

  test.afterEach(async ({ page }) => {
    await disconnectIfConnected(page);
  });

  test('the vehicle marker opens a popup, and a click on the position copies it', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    const marker = page.locator('.drone-icon');
    await expect(marker).toBeVisible({ timeout: 15000 });
    await marker.click();

    const position = page.locator('.leaflet-popup-content .drone-coord');
    await expect(position).toHaveText(/^-?\d+\.\d{6}, -?\d+\.\d{6}$/);
    const shown = await position.innerText();
    // The page's content policy runs no onclick attribute: this is a listener.
    await position.click();
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(shown);
  });

  test('control panel opens via Controls button', async ({ page }) => {
    const ctrlBtn = page.locator('button', { hasText: /操控|控制|Controls/ }).first();
    if (await ctrlBtn.isVisible()) {
      await ctrlBtn.click();
      await page.waitForTimeout(500);
      await expect(page.locator('body')).toContainText(/Arm|解锁|Stabilize|Loiter/);
    }
  });

  test('arm button visible in control panel', async ({ page }) => {
    const ctrlBtn = page.locator('button', { hasText: /操控|控制|Controls/ }).first();
    if (await ctrlBtn.isVisible()) await ctrlBtn.click();
    await page.waitForTimeout(500);

    await expect(page.locator('button', { hasText: /Arm|解锁/ }).first()).toBeVisible({ timeout: 5000 });
  });

  test('mode buttons displayed', async ({ page }) => {
    const ctrlBtn = page.locator('button', { hasText: /操控|控制|Controls/ }).first();
    if (await ctrlBtn.isVisible()) await ctrlBtn.click();
    await page.waitForTimeout(500);

    await expect(page.locator('body')).toContainText(
      /Stabilize|Loiter|AltHold|Auto|Guided|自稳|悬停|定高|自动|引导/,
    );
  });

  test('RTL button visible in nav bar', async ({ page }) => {
    await expect(page.locator('button', { hasText: /RTL|返航/ }).first()).toBeVisible({ timeout: 5000 });
  });

  test('Pause button visible in nav bar', async ({ page }) => {
    // The nav quick-action pauses by switching to Loiter, so its zh label
    // is 悬停 (MapControls pause() → mode 5).
    await expect(page.locator('button', { hasText: /暂停|悬停|Pause/ }).first()).toBeVisible({ timeout: 5000 });
  });

  test('signal strength displayed', async ({ page }) => {
    // The Hz figure lives in the link-quality indicator's title attribute
    // (StatusBar), not in visible text — the visible part is the bare rate.
    await expect(page.locator('[title*="Hz"]').first()).toBeVisible({ timeout: 10000 });
  });

  test('GPS status displayed', async ({ page }) => {
    await expect(page.locator('body')).toContainText(/GPS|3D|2D|No.*Fix/, { timeout: 15000 });
  });

  test('battery voltage displayed', async ({ page }) => {
    await expect(page.locator('body')).toContainText(/\d+\.\d+\s*V/, { timeout: 10000 });
  });

  test('event log shows events', async ({ page }) => {
    await page.waitForTimeout(3000);
    await expect(page.locator('body')).toContainText(/事件|Event/i);
  });
});

test.describe('On a phone, upright (connected)', () => {
  // Pixel 7. Under 768 px the bar under the status bar is hidden (max-md), RTL and Hold with it.
  test.use({ viewport: { width: 412, height: 915 } });

  test.afterEach(async ({ page }) => {
    await disconnectIfConnected(page);
  });

  test('return, hold and the controls sit above the tabs, and nothing lies over the events bar', async ({ page }) => {
    // Hold is a mode change, and every spec after this one shares the simulator: the command is
    // noted here and never reaches it.
    const held: string[] = [];
    await page.routeWebSocket(/\/ws/, (ws) => {
      const server = ws.connectToServer();
      ws.onMessage((message) => {
        const text = String(message);
        if (text.includes('"cmd":"mode"')) held.push(text);
        else server.send(message);
      });
    });
    await connectSimulator(page);

    // The tabs were fixed over the bottom of every view, the events bar of the fly view among it.
    const events = page.getByRole('button', { name: /^(事件|Events) \(\d+\)/ });
    await expect(events).toBeVisible();
    const covered = await events.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return !top || !el.contains(top);
    });
    expect(covered).toBe(false);

    const bar = page.getByRole('toolbar', { name: /飞行控制|Flight Control/ });
    await expect(bar).toBeVisible();
    const tabs = page.locator('nav.md\\:hidden');
    const barBox = (await bar.boundingBox())!;
    const tabsBox = (await tabs.boundingBox())!;
    expect(barBox.y + barBox.height).toBeLessThanOrEqual(tabsBox.y + 1);
    expect(tabsBox.y + tabsBox.height).toBeLessThanOrEqual(915 + 1);

    // RTL asks for the slide, as it does on a wide screen. Not slid: the slide is SlideConfirm's.
    await bar.getByRole('button', { name: /返航|RTL/ }).click();
    const slide = page.getByRole('slider', { name: /滑动切换返航|Slide to return home/ });
    await expect(slide).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(slide).toBeHidden();

    await bar.getByRole('button', { name: /悬停|Hold/ }).click();
    await expect.poll(() => held.length).toBe(1);
    expect(JSON.parse(held[0])).toMatchObject({ type: 'command', cmd: 'mode' });

    await bar.getByRole('button', { name: /操控|Controls/ }).click();
    const arm = page.getByRole('button', { name: /解锁电机|Arm Motors/ });
    await expect(arm).toBeVisible();
    await bar.getByRole('button', { name: /收起|Collapse/ }).click();
    await expect(arm).toBeHidden();

    // The controls belong to the fly view; return and hold go along to every view.
    await tabs.getByRole('button', { name: /参数|Params/ }).click();
    await expect(bar.getByRole('button')).toHaveCount(2);

    // On a wide screen the bar under the status bar has them again.
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(bar).toBeHidden();
    await expect(page.locator('nav.max-md\\:hidden').getByRole('button', { name: /返航|RTL/ })).toBeVisible();
  });
});
