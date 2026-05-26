import { test, expect } from '@playwright/test';
import { connectSimulator, disconnectIfConnected } from './helpers';

test.describe('Drone control (connected)', () => {
  test.beforeEach(async ({ page }) => {
    await connectSimulator(page);
  });

  test.afterEach(async ({ page }) => {
    await disconnectIfConnected(page);
  });

  test('control panel opens via Controls button', async ({ page }) => {
    const ctrlBtn = page.locator('button', { hasText: /控制|Controls/ }).first();
    if (await ctrlBtn.isVisible()) {
      await ctrlBtn.click();
      await page.waitForTimeout(500);
      await expect(page.locator('body')).toContainText(/Arm|解锁|Stabilize|Loiter/);
    }
  });

  test('arm button visible in control panel', async ({ page }) => {
    const ctrlBtn = page.locator('button', { hasText: /控制|Controls/ }).first();
    if (await ctrlBtn.isVisible()) await ctrlBtn.click();
    await page.waitForTimeout(500);

    await expect(page.locator('button', { hasText: /Arm|解锁/ }).first()).toBeVisible({ timeout: 5000 });
  });

  test('mode buttons displayed', async ({ page }) => {
    const ctrlBtn = page.locator('button', { hasText: /控制|Controls/ }).first();
    if (await ctrlBtn.isVisible()) await ctrlBtn.click();
    await page.waitForTimeout(500);

    await expect(page.locator('body')).toContainText(/Stabilize|Loiter|AltHold|Auto|Guided/);
  });

  test('RTL button visible in nav bar', async ({ page }) => {
    await expect(page.locator('button', { hasText: 'RTL' })).toBeVisible({ timeout: 5000 });
  });

  test('Pause button visible in nav bar', async ({ page }) => {
    await expect(page.locator('button', { hasText: /暂停|Pause/ }).first()).toBeVisible({ timeout: 5000 });
  });

  test('signal strength displayed', async ({ page }) => {
    await expect(page.locator('body')).toContainText(/Hz/, { timeout: 10000 });
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
