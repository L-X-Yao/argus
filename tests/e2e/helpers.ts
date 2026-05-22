import { expect, type Page } from '@playwright/test';

export async function connectSimulator(page: Page) {
  await page.goto('/');
  await page.waitForTimeout(1500);

  const portInput = page.locator('input.port-input').first();
  await portInput.fill('tcp:localhost:5770');
  await page.waitForTimeout(300);

  const connectBtn = page.locator('button', { hasText: /^连接$|^Connect$/ }).first();
  await connectBtn.click();

  await expect(page.locator('button', { hasText: /^断开$|^Disconnect$/ })).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(2000);
}

export async function disconnectIfConnected(page: Page) {
  const disconnectBtn = page.locator('button', { hasText: /^断开$|^Disconnect$/ });
  if (await disconnectBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await disconnectBtn.click();
    await page.waitForTimeout(2000);
  }
}
