import { test, expect, type Page } from '@playwright/test';

// The 3D view has no unit coverage, and maplibre v6 fails quietly when its
// worker is miswired: the canvas still appears, but nothing loads into it.
test.use({ launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] } });

// Starts from a saved 3D preference: the toggle only renders once connected,
// and a saved mode is also what would repeat a boot failure on every load.
async function open3d(page: Page) {
  await page.addInitScript(() => localStorage.setItem('argus_settings', JSON.stringify({ mapMode: '3d' })));
  // What the page's content policy refused: see the first test.
  await page.addInitScript(() => {
    const seen: string[] = [];
    (window as unknown as { __refused: string[] }).__refused = seen;
    document.addEventListener('securitypolicyviolation', (e) => seen.push(`${e.violatedDirective} ${e.blockedURI}`));
  });
  await page.goto('/');
}

function seed(page: Page, key: string, value: unknown) {
  return page.addInitScript(([k, v]) => localStorage.setItem(k, v), [key, JSON.stringify(value)]);
}

async function clickMap(page: Page, fx: number, fy: number) {
  const box = await page.locator('canvas.maplibregl-canvas').boundingBox();
  await page.mouse.click(box!.x + box!.width * fx, box!.y + box!.height * fy);
}

// Overlay edits made before the style loads have nowhere to render yet.
function overlaysReady(page: Page) {
  return expect(page.locator('[data-overlays-ready="true"]')).toBeVisible({ timeout: 30000 });
}

test.describe('3D map', () => {
  test('names the servers its picture and its terrain come from', async ({ page }) => {
    await open3d(page);
    const credit = page.locator('.maplibregl-ctrl-attrib');
    await expect(credit).toContainText('AutoNavi', { timeout: 30000 });
    await expect(credit).toContainText('Terrain');
    await expect(credit).toContainText('MapLibre');
    // Folded behind its button it would not be readable.
    await expect(credit).not.toHaveClass(/maplibregl-compact/);
  });

  test('boots with a running worker and its controls', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));
    // Hosted macOS and Windows runners do not reliably report the worker to Playwright. The
    // tests below still show it working there: GeoJSON overlays draw through it.
    const worker =
      process.platform === 'linux'
        ? page.waitForEvent('worker', { predicate: (w) => w.url().includes('maplibre-gl-worker') })
        : null;

    await open3d(page);

    await expect(page.locator('canvas.maplibregl-canvas')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.maplibregl-ctrl-compass')).toBeVisible();
    await expect(page.locator('.maplibregl-ctrl-scale')).toBeVisible();
    // `self.worker` is set by maplibre's worker entry, so this proves the
    // script executed rather than just that a Worker object was constructed.
    if (worker) {
      await expect
        .poll(async () => (await worker).evaluate(() => typeof (self as { worker?: unknown }).worker))
        .toBe('object');
    }
    expect(pageErrors).toEqual([]);

    // The 3D view is the part of the page that asks the most of the content policy: a worker,
    // WebGL, pictures made from fetched bytes, and the one other server the page reads.
    await overlaysReady(page);
    await page.waitForTimeout(2000);
    expect(await page.evaluate(() => (window as unknown as { __refused: string[] }).__refused)).toEqual([]);
  });

  test('shows saved waypoints and adds new ones', async ({ page }) => {
    const wp = (lat: number, lon: number) => ({
      lat,
      lon,
      alt: 50,
      drop: false,
      delay: 0,
      speed: 0,
      type: 'wp',
      loiter_param: 0,
    });
    await seed(page, 'argus_waypoints', [wp(34.258, 108.942), wp(34.262, 108.95), wp(34.254, 108.955)]);
    await open3d(page);

    const numbered = page.locator('.maplibregl-marker', { hasText: /^\d+$/ });
    await overlaysReady(page);
    await expect(numbered).toHaveCount(3);

    await clickMap(page, 0.5, 0.3);
    await expect(numbered).toHaveCount(4);
  });

  test('shows a saved fence', async ({ page }) => {
    await seed(page, 'argus_fence', [
      { lat: 34.258, lon: 108.942 },
      { lat: 34.262, lon: 108.95 },
      { lat: 34.254, lon: 108.955 },
    ]);
    await open3d(page);

    await overlaysReady(page);
    await expect(page.locator('.maplibregl-marker')).toHaveCount(3);
  });

  test('draws a survey polygon', async ({ page }) => {
    await open3d(page);
    await overlaysReady(page);

    await page.getByTitle(/^(测绘|Survey)$/).click();
    await clickMap(page, 0.4, 0.3);
    await clickMap(page, 0.6, 0.3);
    await clickMap(page, 0.5, 0.5);

    await expect(page.locator('.maplibregl-marker')).toHaveCount(3);
  });

  test('shows the replay position', async ({ page }) => {
    await open3d(page);
    await overlaysReady(page);

    const row = (t: number, lat: number) => `${t},0,0,90,${lat},108.942,50,450,5,0,25,5,90,5,Loiter,1,3,14,0,90,0,-1`;
    const csv = ['header', row(0, 34.258), row(1, 34.2585), row(2, 34.259)].join('\n');
    const chooser = page.waitForEvent('filechooser');
    await page.getByText(/加载飞行日志|Load Flight Log/).click();
    await (await chooser).setFiles({ name: 'flight.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });

    await page.locator('input[type="range"]').first().fill('1');

    await expect(page.locator('.maplibregl-marker')).toHaveCount(1);
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

test.describe('3D map with stalled tiles', () => {
  // A service worker would answer tile requests before page.route() sees them.
  test.use({ serviceWorkers: 'block' });

  test('shows overlays while tiles are still loading', async ({ page }) => {
    // The map's 'load' event waits for every tile, including terrain from a
    // third-party host, so overlays must not depend on it.
    let stalled = 0;
    const stall = () => {
      stalled++;
    };
    await page.route('**/api/tile/**', stall);
    await page.route('**/elevation-tiles-prod/**', stall);
    await seed(page, 'argus_fence', [
      { lat: 34.258, lon: 108.942 },
      { lat: 34.262, lon: 108.95 },
      { lat: 34.254, lon: 108.955 },
    ]);
    await open3d(page);

    await expect(page.locator('.maplibregl-marker')).toHaveCount(3, { timeout: 15000 });
    expect(stalled).toBeGreaterThan(0);
  });
});
