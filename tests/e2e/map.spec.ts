import { test, expect, type Locator } from '@playwright/test';

// True when nothing lies over the right end of the element, where its text ends.
function uncovered(locator: Locator): Promise<boolean> {
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const top = document.elementFromPoint(r.right - 4, r.top + r.height / 2);
    return !!top && (el === top || el.contains(top));
  });
}

test.describe('Map interactions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1500);
  });

  test('map container renders', async ({ page }) => {
    await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: 5000 });
  });

  test('map zoom controls work', async ({ page }) => {
    const map = page.locator('.leaflet-container').first();
    const box = await map.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.wheel(0, -300);
      await page.waitForTimeout(500);
      await page.mouse.wheel(0, 300);
      await page.waitForTimeout(500);
    }
  });

  test('layer toggle button exists', async ({ page }) => {
    const buttons = page.locator('.leaflet-container button, [class*="absolute"] button');
    expect(await buttons.count()).toBeGreaterThan(0);
  });

  test('follow button exists', async ({ page }) => {
    const buttons = page.locator('.leaflet-container ~ div button, .absolute button');
    expect(await buttons.count()).toBeGreaterThan(0);
  });

  test('coordinates display on mouse move', async ({ page }) => {
    const map = page.locator('.leaflet-container').first();
    const box = await map.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.waitForTimeout(500);
      await expect(page.locator('body')).toContainText(/\d+\.\d+/);
    }
  });
});

// The map servers' terms want their credit on the map, readable and not under other parts of
// the page: for OpenStreetMap, https://operations.osmfoundation.org/policies/tiles/ section 2.
test.describe('Map credit', () => {
  test('the default map names its server, clear of the events bar', async ({ page }) => {
    await page.goto('/');
    const credit = page.locator('.leaflet-control-attribution');
    await expect(credit).toContainText('AutoNavi');
    expect(await uncovered(credit)).toBe(true);
  });

  test('a source without a label layer shows its street layer, and that layer its credit', async ({ page }) => {
    // Handing Leaflet the missing label layer threw, and left the map blank until v3.7.9.
    const pageErrors: string[] = [];
    page.on('pageerror', (e) => pageErrors.push(e.message));
    await page.addInitScript(() => localStorage.setItem('argus_settings', JSON.stringify({ tileSource: 'osm' })));
    await page.goto('/');
    const credit = page.locator('.leaflet-control-attribution');
    await expect(credit).toContainText('Powered by Esri');

    await page.locator('button.map-btn').first().click();
    await expect(credit).toContainText('© OpenStreetMap contributors');
    await expect(credit).not.toContainText('Esri');
    await expect(page.locator('.leaflet-tile-pane img[src*="/api/tile/osm/"]').first()).toBeAttached();
    const link = credit.locator('a');
    await expect(link).toHaveAttribute('href', 'https://www.openstreetmap.org/copyright');
    await expect(link).toHaveAttribute('target', '_blank');
    expect(await uncovered(credit)).toBe(true);

    await page.locator('button.map-btn').first().click();
    await expect(credit).toContainText('Powered by Esri');
    await expect(page.locator('.leaflet-tile-pane img[src*="/api/tile/osm_sat/"]').first()).toBeAttached();
    expect(pageErrors).toEqual([]);
  });
});
