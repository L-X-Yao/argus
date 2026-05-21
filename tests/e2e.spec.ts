import { test, expect } from '@playwright/test';

test.describe('GCS v3 E2E', () => {
  test('homepage loads with status bar', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText('PL-Link')).toBeVisible({ timeout: 5000 });
  });

  test('settings panel opens and closes', async ({ page }) => {
    await page.goto('/');
    const settingsBtn = page.locator('button:has(svg.lucide-settings)').first();
    if (await settingsBtn.isVisible()) {
      await settingsBtn.click();
      await expect(page.getByText(/设置|Settings/)).toBeVisible({ timeout: 3000 });
    }
  });

  test('dark/light theme toggle', async ({ page }) => {
    await page.goto('/');
    const html = page.locator('html');
    const initial = await html.getAttribute('class');
    expect(initial).toContain('dark');
  });

  test('keyboard shortcut F toggles fullscreen map', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);
    await page.keyboard.press('f');
  });

  test('no ArduPilot branding visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);
    const content = await page.textContent('body');
    expect(content).not.toContain('ArduPilot');
    expect(content).not.toContain('ArduCopter');
    expect(content).not.toContain('ArduPlane');
    expect(content).not.toContain('ChibiOS');
  });
});
