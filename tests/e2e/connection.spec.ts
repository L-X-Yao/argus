import { test, expect } from '@playwright/test';
import { connectSimulator, disconnectIfConnected } from './helpers';

test.describe.configure({ mode: 'serial' });

test.describe('Connection flow', () => {
  test.afterEach(async ({ page }) => {
    await disconnectIfConnected(page);
  });

  test('connect to simulator via default port', async ({ page }) => {
    await connectSimulator(page);
    await expect(page.locator('body')).toContainText(
      /Stabilize|Loiter|Guided|Auto|Manual|AltHold|自稳|悬停|引导|自动|手动|定高/,
      { timeout: 10000 },
    );
  });

  test('shows telemetry after connection', async ({ page }) => {
    await connectSimulator(page);
    await expect(page.locator('body')).toContainText(/\d+\.\d+\s*V/, { timeout: 10000 });
  });

  test('SIM start disables the other connect shortcuts until it answers', async ({ page }) => {
    await page.route('**/api/simulator/start', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true,"started":false}' });
    });
    await page.goto('/');
    await page.getByRole('button', { name: 'SIM', exact: true }).click();
    await expect(page.getByRole('button', { name: 'SITL', exact: true })).toBeDisabled();
    await expect(page.locator('input.port-input')).toHaveValue('tcp:localhost:5770');
    await expect(page.getByRole('button', { name: /^断开$|^Disconnect$/ })).toBeVisible({ timeout: 15000 });
  });

  test('disconnect button appears when connected', async ({ page }) => {
    await connectSimulator(page);
    await expect(page.locator('button', { hasText: /^断开$|^Disconnect$/ })).toBeVisible();
  });

  test('disconnect returns to welcome state', async ({ page }) => {
    await connectSimulator(page);
    await page.locator('button', { hasText: /^断开$|^Disconnect$/ }).click();
    await page.waitForTimeout(3000);
    await expect(page.locator('kbd', { hasText: 'Ctrl+K' })).toBeVisible({ timeout: 10000 });
  });
});
