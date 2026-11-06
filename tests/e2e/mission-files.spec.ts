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
