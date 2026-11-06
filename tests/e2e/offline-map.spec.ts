import { test, expect } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';

// A real .mbtiles file in the backend's folder, picked in Settings, showing on the map.
const FOLDER = path.resolve('mbtiles');
const NAME = 'argus-e2e.mbtiles';
const FILE = path.join(FOLDER, NAME);
// 1x1 red PNG. Leaflet stretches it to a whole tile.
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==',
  'base64',
);

test.beforeEach(() => {
  fs.mkdirSync(FOLDER, { recursive: true });
  const db = new DatabaseSync(FILE);
  db.exec('CREATE TABLE tiles (zoom_level INT, tile_column INT, tile_row INT, tile_data BLOB)');
  db.close();
});

test.afterEach(() => {
  fs.rmSync(FILE, { force: true });
});

test('a file in the mbtiles folder can be picked and shows on the map', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  await page.goto('/');
  await page.waitForTimeout(1000);
  await page.keyboard.press('Control+s');
  const picker = page.locator('select').filter({ has: page.locator('option[value="amap"]') });
  await expect(picker.locator(`option[value="mbtiles:${NAME}"]`)).toBeAttached({ timeout: 10000 });

  const asked = new Set<string>();
  page.on('response', (r) => {
    const m = r.url().match(/\/api\/mbtiles\/[^/]+\/(\d+)\/(\d+)\/(\d+)$/);
    if (m) asked.add(`${m[1]}/${m[2]}/${m[3]}`);
  });
  await picker.selectOption(`mbtiles:${NAME}`);
  await expect.poll(() => asked.size, { message: 'no tile asked of the file', timeout: 10000 }).toBeGreaterThan(0);

  // The map asks for what its view needs, so put exactly that in the file.
  const db = new DatabaseSync(FILE);
  const insert = db.prepare('INSERT INTO tiles VALUES (?, ?, ?, ?)');
  for (const tile of asked) {
    const [z, x, y] = tile.split('/').map(Number);
    insert.run(z, x, 2 ** z - 1 - y, PNG); // MBTiles counts rows from the south
  }
  db.close();

  await page.reload();
  await expect
    .poll(
      () =>
        page
          .locator('img.leaflet-tile-loaded')
          .evaluateAll((imgs) => imgs.filter((i) => (i as HTMLImageElement).src.includes('/api/mbtiles/')).length),
      { message: 'no tile from the file on the map', timeout: 15000 },
    )
    .toBeGreaterThan(0);
});
