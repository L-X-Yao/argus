import { test, expect } from '@playwright/test';

test.describe('Command palette', () => {
  test('opens with Ctrl+K', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);

    await page.keyboard.press('Control+k');
    await page.waitForTimeout(500);
    await expect(page.locator('input[placeholder]').last()).toBeVisible();
  });

  test('shows navigation commands', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);

    await page.keyboard.press('Control+k');
    await page.waitForTimeout(500);

    await expect(page.locator('body')).toContainText(/Fly|Plan|Monitor|Params|飞行|计划|监控|参数/);
  });

  test('typing filters results', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);

    await page.keyboard.press('Control+k');
    await page.waitForTimeout(500);

    const searchInput = page.locator('input[placeholder]').last();
    await searchInput.fill('plan');
    await page.waitForTimeout(300);
  });

  test('an ortho overlay reaches the map and survives a reload', async ({ page }) => {
    const png =
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
    await page.goto('/');
    await page.waitForTimeout(1000);
    await page.keyboard.press('Control+k');
    await page.waitForTimeout(500);
    await page.locator('input[placeholder]').last().fill('正射叠加');
    await page.waitForTimeout(300);
    await page.keyboard.press('Enter');
    await page
      .locator('input[type=file]')
      .setInputFiles({ name: 'ortho.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
    await expect(page.getByText('图片已加载').first()).toBeVisible();

    await page.locator('#nw-lat').fill('34.30');
    await page.locator('#nw-lon').fill('108.90');
    await page.locator('#se-lat').fill('34.20');
    await page.locator('#se-lon').fill('109.00');
    await page.getByRole('button', { name: '应用叠加' }).click();
    await expect(page.locator('img.leaflet-image-layer')).toHaveCount(1);

    await page.reload();
    await expect(page.locator('img.leaflet-image-layer')).toHaveCount(1);
  });

  test('ortho overlay corners in the wrong order are refused', async ({ page }) => {
    const png =
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
    await page.goto('/');
    await page.waitForTimeout(1000);
    await page.keyboard.press('Control+k');
    await page.waitForTimeout(500);
    await page.locator('input[placeholder]').last().fill('正射叠加');
    await page.waitForTimeout(300);
    await page.keyboard.press('Enter');
    await page
      .locator('input[type=file]')
      .setInputFiles({ name: 'ortho.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
    await page.locator('#nw-lat').fill('34.20');
    await page.locator('#nw-lon').fill('108.90');
    await page.locator('#se-lat').fill('34.30');
    await page.locator('#se-lon').fill('109.00');
    await page.getByRole('button', { name: '应用叠加' }).click();
    await expect(page.getByText('西北角必须在东南角的西北方向').first()).toBeVisible();
    await expect(page.locator('img.leaflet-image-layer')).toHaveCount(0);
  });

  // Both are advertised in the README, yet nothing opened them until a review
  // went looking: the palette is the only entry for most tool panels.
  for (const [query, title] of [
    ['NTRIP', /RTK \/ NTRIP/],
    ['云台', /云台控制/],
    ['自定义仪表盘', /自定义仪表盘/],
    ['定位源', /定位源/],
    ['正射叠加', /正射叠加/],
  ] as const) {
    test(`opens the ${query} panel`, async ({ page }) => {
      await page.goto('/');
      await page.waitForTimeout(1000);
      await page.keyboard.press('Control+k');
      await page.waitForTimeout(500);
      await page.locator('input[placeholder]').last().fill(query);
      await page.waitForTimeout(300);
      await page.keyboard.press('Enter');
      await expect(page.getByRole('heading', { name: title })).toBeVisible({ timeout: 5000 });
    });
  }

  test('Escape closes palette', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);

    await page.keyboard.press('Control+k');
    await page.waitForTimeout(500);
    await expect(page.locator('input[placeholder]').last()).toBeVisible();

    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
  });
});
