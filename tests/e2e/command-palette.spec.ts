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

  // Both are advertised in the README, yet nothing opened them until a review
  // went looking: the palette is the only entry for most tool panels.
  for (const [query, title] of [
    ['NTRIP', /RTK \/ NTRIP/],
    ['云台', /云台控制/],
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
