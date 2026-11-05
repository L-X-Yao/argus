import { test, expect, type Page } from '@playwright/test';

// The 3D view has no unit coverage, and maplibre v6 fails quietly when its
// worker is miswired: the canvas still appears, but nothing loads into it.
test.use({ launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] } });

// Starts from a saved 3D preference: the toggle only renders once connected,
// and a saved mode is also what would repeat a boot failure on every load.
async function open3d(page: Page) {
  await page.addInitScript(() => localStorage.setItem('argus_settings', JSON.stringify({ mapMode: '3d' })));
  await page.goto('/');
}

test.describe('3D map', () => {
  test('boots with a running worker and its controls', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));
    const worker = page.waitForEvent('worker', { predicate: (w) => w.url().includes('maplibre-gl-worker') });

    await open3d(page);

    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.maplibregl-ctrl-compass')).toBeVisible();
    await expect(page.locator('.maplibregl-ctrl-scale')).toBeVisible();
    // `self.worker` is set by maplibre's worker entry, so this proves the
    // script executed rather than just that a Worker object was constructed.
    await expect
      .poll(async () => (await worker).evaluate(() => typeof (self as { worker?: unknown }).worker))
      .toBe('object');
    expect(pageErrors).toEqual([]);
  });

  test('falls back to the 2D map without WebGL2', async ({ page }) => {
    await page.addInitScript(() => {
      const real = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, ...rest: unknown[]) {
        return type === 'webgl2' ? null : (real as (...a: unknown[]) => unknown).call(this, type, ...rest);
      } as typeof real;
    });

    await open3d(page);

    await expect(page.locator('body')).toContainText('WebGL2', { timeout: 15000 });
    await expect(page.locator('.leaflet-container')).toBeVisible();
    await expect(page.locator('canvas.maplibregl-canvas')).toHaveCount(0);
  });
});
