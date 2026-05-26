import { test, expect } from '@playwright/test';

test.describe('PWA offline capabilities', () => {
  test('service worker registers successfully', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    const swRegistered = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return false;
      const reg = await navigator.serviceWorker.getRegistration('/');
      return !!reg;
    });
    expect(swRegistered).toBe(true);
  });

  test('service worker becomes active', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    const swState = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return null;
      const reg = await navigator.serviceWorker.getRegistration('/');
      if (!reg) return null;
      const sw = reg.active || reg.waiting || reg.installing;
      return sw ? sw.state : null;
    });
    expect(swState).toBe('activated');
  });

  test('manifest.json is accessible and valid', async ({ request }) => {
    const res = await request.get('/manifest.json');
    expect(res.ok()).toBeTruthy();

    const manifest = await res.json();
    expect(manifest.name).toBe('Argus Ground Control Station');
    expect(manifest.short_name).toBe('Argus');
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url).toBe('/');
    expect(manifest.icons).toHaveLength(2);
    expect(manifest.icons[0].sizes).toBe('192x192');
    expect(manifest.icons[1].sizes).toBe('512x512');
  });

  test('app shell is served from cache when offline', async ({ page }) => {
    // First load to populate the cache
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Verify the page loaded successfully
    await expect(page.locator('body')).toBeVisible();

    // Simulate offline by blocking all network requests
    await page.route('**/*', (route) => {
      route.abort('connectionfailed');
    });

    // Navigate again - should be served from service worker cache
    await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 10000 });
    await expect(page.locator('body')).toBeVisible();
  });

  test('cached static assets load offline', async ({ page }) => {
    // Load page to cache assets
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Collect asset URLs that were loaded
    const cachedAssets = await page.evaluate(async () => {
      const cache = await caches.open('argus-gcs-v3.3');
      const keys = await cache.keys();
      return keys.map((r) => new URL(r.url).pathname);
    });

    // Verify core app shell items are cached
    expect(cachedAssets).toContain('/');
    expect(cachedAssets).toContain('/manifest.json');
  });
});
