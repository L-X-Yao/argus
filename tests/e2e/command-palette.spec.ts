import { test, expect } from '@playwright/test';
import { openPalette, searchPalette } from './helpers';

test.describe('Command palette', () => {
  test('opens with Ctrl+K', async ({ page }) => {
    await page.goto('/');
    await openPalette(page);
  });

  test('shows navigation commands', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);

    // In the palette: the page has these words in its tabs anyway.
    const palette = await openPalette(page);
    await expect(palette).toContainText(/Fly|Plan|Monitor|Params|飞行|计划|监控|参数/);
  });

  test('typing filters results', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);

    const palette = await searchPalette(page, 'plan');
    await expect(palette.getByRole('option').first()).toBeVisible();
  });

  test('an ortho overlay reaches the map and survives a reload', async ({ page }) => {
    const png =
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
    await page.goto('/');
    await searchPalette(page, '正射叠加');
    await page.keyboard.press('Enter');
    await page
      .locator('input[type=file]')
      .setInputFiles({ name: 'ortho.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
    await expect(page.getByText('图片已加载').first()).toBeVisible();

    await page.locator('#nw-lat').fill('34.30');
    await page.locator('#nw-lon').fill('108.90');
    await page.locator('#se-lat').fill('34.20');
    await page.locator('#se-lon').fill('109.00');
    await page.getByRole('button', { name: '应用叠加' }).click();
    await expect(page.locator('img.leaflet-image-layer')).toHaveCount(1);

    await page.reload();
    await expect(page.locator('img.leaflet-image-layer')).toHaveCount(1);
  });

  test('ortho overlay corners in the wrong order are refused', async ({ page }) => {
    const png =
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
    await page.goto('/');
    await searchPalette(page, '正射叠加');
    await page.keyboard.press('Enter');
    await page
      .locator('input[type=file]')
      .setInputFiles({ name: 'ortho.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
    await page.locator('#nw-lat').fill('34.20');
    await page.locator('#nw-lon').fill('108.90');
    await page.locator('#se-lat').fill('34.30');
    await page.locator('#se-lon').fill('109.00');
    await page.getByRole('button', { name: '应用叠加' }).click();
    await expect(page.getByText('西北角必须在东南角的西北方向').first()).toBeVisible();
    await expect(page.locator('img.leaflet-image-layer')).toHaveCount(0);
  });

  // Both are advertised in the README, yet nothing opened them until a review
  // went looking: the palette is the only entry for most tool panels.
  for (const [query, title] of [
    ['NTRIP', /RTK \/ NTRIP/],
    ['云台', /云台控制/],
    ['自定义仪表盘', /自定义仪表盘/],
    ['定位源', /定位源/],
    ['正射叠加', /正射叠加/],
  ] as const) {
    test(`opens the ${query} panel`, async ({ page }) => {
      await page.goto('/');
      await searchPalette(page, query);
      await page.keyboard.press('Enter');
      // The panel is a chunk of its own too.
      await expect(page.getByRole('heading', { name: title })).toBeVisible({ timeout: 15000 });
    });
  }

  test('Escape closes palette', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);

    const palette = await openPalette(page);
    await page.keyboard.press('Escape');
    await expect(palette).toBeHidden();
  });
});

test.describe('Annotations', () => {
  async function openAnnotations(page: import('@playwright/test').Page) {
    await searchPalette(page, '地图标注');
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: '地图标注' })).toBeVisible({ timeout: 15000 });
  }

  test('one stored without a position does not keep the panel shut', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto('/');
    // What v3.7.10 stored when the latitude box had been emptied.
    await page.evaluate(() =>
      localStorage.setItem(
        'argus_annotations',
        JSON.stringify([
          { id: 1, name: 'pad', note: '', lat: 34.25, lon: 108.94 },
          { id: 2, name: 'no place', note: '', lat: null, lon: 108.94 },
        ]),
      ),
    );
    await page.reload();
    await page.waitForTimeout(1000);
    await openAnnotations(page);
    await expect(page.getByText('34.250000, 108.940000')).toBeVisible();
    await expect(page.getByText('no place')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('one without a position is not saved', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.removeItem('argus_annotations'));
    await page.reload();
    await page.waitForTimeout(1000);
    await openAnnotations(page);
    await page.getByRole('button', { name: /添加标注/ }).click();
    await page.locator('#ann-name').fill('gate');
    await page.locator('#ann-lat').fill('');
    await page.getByRole('button', { name: '保存', exact: true }).click();
    await expect(page.getByText('坐标无效')).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('argus_annotations'))).toBeNull();

    await page.locator('#ann-lat').fill('34.26');
    await page.locator('#ann-lon').fill('108.95');
    await page.getByRole('button', { name: '保存', exact: true }).click();
    await expect(page.getByText('34.260000, 108.950000')).toBeVisible();
  });
});

test.describe('Advanced commands', () => {
  test('a command without its number is not attached to a waypoint', async ({ page }) => {
    const stored = () =>
      page.evaluate(() => JSON.parse(localStorage.getItem('argus_waypoints') || '[]')[0] as Record<string, unknown>);
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.clear();
      const wp = { lat: 34.251, lon: 108.931, alt: 40, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 };
      localStorage.setItem('argus_waypoints', JSON.stringify([wp]));
    });
    await page.reload();
    await searchPalette(page, '高级指令');
    await page.keyboard.press('Enter');

    await page.getByRole('button', { name: '相机触发间隔' }).click();
    // An emptied number box holds null, and v3.7.10 stored a trigger with a distance of null.
    await page.locator('#ac-cam-dist').fill('');
    await page.getByRole('button', { name: '在航点后插入' }).click();
    await expect(page.getByText('无效数值')).toBeVisible();
    expect(await stored()).not.toHaveProperty('cmd_cam_trig');

    await page.locator('#ac-cam-dist').fill('25');
    await page.getByRole('button', { name: '在航点后插入' }).click();
    await expect.poll(stored).toHaveProperty('cmd_cam_trig', { dist: 25 });
  });
});
