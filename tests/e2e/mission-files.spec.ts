import { test, expect, type Page } from '@playwright/test';

// Files as other ground stations write them, through the panel's own buttons.
const WAYPOINTS = [
  'QGC WPL 110',
  '0\t1\t0\t16\t0\t0\t0\t0\t34.2500000\t108.9300000\t400\t1',
  '1\t0\t3\t22\t0\t0\t0\t0\t0\t0\t30\t1',
  '2\t0\t3\t16\t0\t0\t0\t0\t34.2510000\t108.9310000\t40\t1',
  '3\t0\t3\t16\t0\t0\t0\t0\t34.2520000\t108.9320000\t50\t1',
  '4\t0\t3\t19\t20\t0\t0\t0\t34.2530000\t108.9330000\t60\t1',
  '5\t0\t3\t20\t0\t0\t0\t0\t0\t0\t0\t1',
].join('\r\n');

const simple = (command: number, lat: number, alt: number) => ({
  AMSLAltAboveTerrain: null,
  Altitude: alt,
  AltitudeMode: 1,
  autoContinue: true,
  command,
  doJumpId: 1,
  frame: 3,
  params: [0, 0, 0, null, lat, 108.93, alt],
  type: 'SimpleItem',
});
const PLAN = JSON.stringify({
  fileType: 'Plan',
  groundStation: 'QGroundControl',
  mission: {
    firmwareType: 3,
    items: [
      simple(22, 34.25, 30),
      simple(16, 34.251, 40),
      {
        type: 'ComplexItem',
        complexItemType: 'survey',
        TransectStyleComplexItem: { Items: [simple(16, 34.252, 50), simple(16, 34.253, 50)] },
      },
    ],
    plannedHomePosition: [34.25, 108.93, 400],
    vehicleType: 2,
    version: 2,
  },
  version: 1,
});
const KML = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><LineString>
<coordinates>108.931,34.251,40 108.932,34.252,50</coordinates>
</LineString></Placemark></Document></kml>`;

async function openPlan(page: Page) {
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  await page.goto('/');
  await page.waitForTimeout(1000);
  await page.locator('nav button', { hasText: /规划|Plan/ }).first().click();
  await page.waitForTimeout(500);
}

async function pick(page: Page, button: RegExp, name: string, text: string) {
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: button }).first().click();
  await (await chooser).setFiles({ name, mimeType: 'text/plain', buffer: Buffer.from(text) });
}

const rows = (page: Page) => page.getByText(/^\s*\d+\.\d{5},\d+\.\d{5}/);

test('a .waypoints file loads without its home row', async ({ page }) => {
  await openPlan(page);
  await pick(page, /^加载$|^Load$/, 'mission.waypoints', WAYPOINTS);
  await expect(rows(page)).toHaveCount(3);
  await expect(rows(page).first()).toContainText('34.25100,108.93100');
});

test('a .plan file loads, survey included', async ({ page }) => {
  await openPlan(page);
  await pick(page, /^加载$|^Load$/, 'mission.plan', PLAN);
  await expect(rows(page)).toHaveCount(3);
});

test('a .kml file loads, and comes back out with the same points', async ({ page }) => {
  await openPlan(page);
  await pick(page, /^导入$|^Import$/, 'route.kml', KML);
  await expect(rows(page)).toHaveCount(2);

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: /^导出$|^Export$/ }).first().click();
  const file = await (await download).createReadStream();
  const chunks: Buffer[] = [];
  for await (const c of file) chunks.push(c as Buffer);
  const kml = Buffer.concat(chunks).toString();
  expect(kml).toContain('108.931');
  expect(kml).toContain('34.252');
});

// What a file can hold where a number belongs. The map writes these fields into HTML, and a
// picture that cannot load runs its handler at once.
const MARKUP = '<img src=x onerror="window.__argus_xss=1">';

const point = (over: Record<string, unknown> = {}) => ({
  lat: 34.251,
  lon: 108.931,
  alt: 40,
  drop: false,
  delay: 0,
  speed: 0,
  type: 'wp',
  loiter_param: 0,
  ...over,
});

async function nothingInjected(page: Page) {
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => (window as unknown as { __argus_xss?: number }).__argus_xss)).toBeUndefined();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
}

test('a mission saved by Argus loads back, hold times and all', async ({ page }) => {
  await openPlan(page);
  const mission = { waypoints: [point({ delay: 7 }), point({ lat: 34.252, type: 'loiter_time', loiter_param: 20 })], alt: 40 };
  await pick(page, /^加载$|^Load$/, 'mission.json', JSON.stringify(mission));
  await expect(rows(page)).toHaveCount(2);
  await expect(page.locator('.leaflet-marker-icon', { hasText: '+7s' })).toHaveCount(1);
  await expect(page.locator('.leaflet-marker-icon', { hasText: '20s' })).toHaveCount(1);
});

for (const field of ['delay', 'alt', 'loiter_param']) {
  test(`a mission file with markup as its ${field} is refused`, async ({ page }) => {
    await openPlan(page);
    const mission = { waypoints: [point({ type: 'loiter_time', [field]: MARKUP })], alt: 40 };
    await pick(page, /^加载$|^Load$/, 'mission.json', JSON.stringify(mission));
    await expect(page.getByText(/任务加载失败|Mission load failed/)).toBeVisible();
    await expect(rows(page)).toHaveCount(0);
    await nothingInjected(page);
  });
}

test('a mission file that holds no route changes nothing', async ({ page }) => {
  await openPlan(page);
  await pick(page, /^加载$|^Load$/, 'mission.waypoints', WAYPOINTS);
  await expect(rows(page)).toHaveCount(3);
  // A fence file, picked by mistake.
  await pick(page, /^加载$|^Load$/, 'fence.json', JSON.stringify([{ lat: 1, lon: 2 }]));
  await expect(page.getByText(/任务加载失败|Mission load failed/)).toBeVisible();
  await expect(rows(page)).toHaveCount(3);
});

test('a .plan file with markup as a parameter is refused', async ({ page }) => {
  await openPlan(page);
  const item = { ...simple(16, 34.251, 40), params: [MARKUP, 0, 0, null, 34.251, 108.93, 40] };
  await pick(page, /^加载$|^Load$/, 'mission.plan', JSON.stringify({ mission: { items: [item] } }));
  await expect(page.getByText(/任务加载失败|Mission load failed/)).toBeVisible();
  await expect(rows(page)).toHaveCount(0);
  await nothingInjected(page);
});

test('stored waypoints with markup in them are not restored', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(
    (stored) => {
      localStorage.clear();
      localStorage.setItem('argus_waypoints', stored);
    },
    JSON.stringify([point(), point({ delay: MARKUP })]),
  );
  await page.goto('/');
  await page.waitForTimeout(1000);
  await page.locator('nav button', { hasText: /规划|Plan/ }).first().click();
  await page.waitForTimeout(500);
  await expect(rows(page)).toHaveCount(0);
  await nothingInjected(page);
});

test('a KML overlay shows the name of a shape as text', async ({ page }) => {
  const kml = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>
<name>${MARKUP.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</name>
<Polygon><outerBoundaryIs><LinearRing>
<coordinates>106,32 112,32 112,36 106,36 106,32</coordinates>
</LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>`;
  await page.goto('/');
  await page.waitForTimeout(1500);
  const chooser = page.waitForEvent('filechooser');
  await page.locator('button.map-btn', { hasText: /^KML$/ }).click();
  await (await chooser).setFiles({ name: 'area.kml', mimeType: 'text/plain', buffer: Buffer.from(kml) });
  await expect(page.getByText(/已加载 KML|Loaded KML/)).toBeVisible();

  // Leaflet opens the tooltip when the pointer comes over the shape.
  await page.locator('path.leaflet-interactive[stroke="#e040fb"]').dispatchEvent('mouseover');
  await expect(page.locator('.leaflet-tooltip')).toHaveText(MARKUP);
  await nothingInjected(page);
});
