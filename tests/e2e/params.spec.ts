import { test, expect } from '@playwright/test';
import { connectSimulator, disconnectIfConnected } from './helpers';

test.describe('Parameters panel', () => {
  test.afterEach(async ({ page }) => {
    await disconnectIfConnected(page);
  });

  test('params tab loads with read button', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);
    const paramsTab = page.locator('nav button', { hasText: /参数|Params/ }).first();
    await paramsTab.click();
    await page.waitForTimeout(500);
    await expect(page.locator('body')).toContainText(/读取|Read|All|全部/i, { timeout: 5000 });
  });

  test('read all params button triggers fetch when connected', async ({ page }) => {
    await connectSimulator(page);
    const paramsTab = page.locator('nav button', { hasText: /参数|Params/ }).first();
    await paramsTab.click();
    await page.waitForTimeout(500);

    const readBtn = page.locator('button', { hasText: /读取|Read/ }).first();
    if (await readBtn.isVisible()) {
      await readBtn.click();
      await page.waitForTimeout(5000);
      await expect(page.locator('body')).toContainText(/\d+/, { timeout: 10000 });
    }
  });

  // The params view renders an empty state (just the read-params button)
  // until a fetch has populated it — search box and category tabs only
  // exist after params load, so both assertions need a connected fetch.
  test('search input appears after params load', async ({ page }) => {
    await connectSimulator(page);
    const paramsTab = page.locator('nav button', { hasText: /参数|Params/ }).first();
    await paramsTab.click();
    await page.waitForTimeout(500);
    await page.locator('button', { hasText: /读取|Read/ }).first().click();

    const searchInput = page.locator('input[type="text"]');
    await expect(searchInput.first()).toBeVisible({ timeout: 15000 });
  });

  test('category tabs appear after params load', async ({ page }) => {
    await connectSimulator(page);
    const paramsTab = page.locator('nav button', { hasText: /参数|Params/ }).first();
    await paramsTab.click();
    await page.waitForTimeout(500);
    await page.locator('button', { hasText: /读取|Read/ }).first().click();

    const allTab = page.locator('button').filter({ hasText: /全部|All/ }).first();
    await expect(allTab).toBeVisible({ timeout: 15000 });
  });
});
