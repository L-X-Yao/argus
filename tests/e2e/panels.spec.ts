import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { connectSimulator } from './helpers';

// The palette is the only way in to most tool panels, and a panel that throws on
// open looks fine to every other test. Reading the entries from the source means a
// new one is covered without anyone having to remember it.
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), 'utf-8');
const palette = read('../../src/components/shared/CommandPalette.svelte');
const zh = read('../../src/lib/locales/zh.ts');

const label = (key: string) => zh.match(new RegExp(`'${key.replace(/\./g, '\\.')}':\\s*'([^']*)'`))?.[1] ?? key;
const tools = [...palette.matchAll(/id: '(tool-\w+)'/g)].map((m) => m[1]);

// The palette also searches ids, and those are unique.
async function openFromPalette(page: Page, id: string) {
  await page.keyboard.press('Control+k');
  await page
    .getByRole('dialog', { name: label('cmd.placeholder') })
    .locator('input')
    .fill(id);
  await page.waitForTimeout(300);
  await page.keyboard.press('Enter');
  // A navigation closes the palette again a frame later, and would take a new one with it.
  await page.waitForTimeout(300);
}

async function readParams(page: Page) {
  await page
    .locator('nav button', { hasText: /参数|Params/ })
    .first()
    .click();
  await page
    .locator('button', { hasText: /读取|Read/ })
    .first()
    .click();
  // The search box only renders once the list has rows.
  await expect(page.getByPlaceholder(label('param.search'))).toBeVisible({ timeout: 15000 });
}

async function openRallyPanel(page: Page) {
  await page.goto('/');
  await page.waitForTimeout(500);
  await openFromPalette(page, 'nav-plan');
  await page.getByRole('button', { name: '备降点' }).click();
}

test.describe('Tool panels', () => {
  test('the palette lists tools', () => {
    expect(tools.length).toBeGreaterThan(25);
  });

  for (const id of tools) {
    test(`${id} opens without an error`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));
      await connectSimulator(page); // most tools only list with a vehicle connected
      if (id === 'tool-paramdiff') await readParams(page); // and this one with parameters
      await openFromPalette(page, id);
      // The palette is a dialog too, and stays open if the search found nothing.
      await expect(page.getByRole('dialog', { name: label('cmd.placeholder') })).toHaveCount(0);
      // The video panel floats over the map instead of covering it.
      await expect(page.locator('[role="dialog"], [role="region"]').first()).toBeVisible({ timeout: 5000 });
      await page.waitForTimeout(300);
      expect(errors).toEqual([]);
    });
  }
});

test.describe('Flight mode panel', () => {
  test('shows the six slots the FC reports', async ({ page }) => {
    await connectSimulator(page);
    await readParams(page);
    await openFromPalette(page, 'tool-modes');
    const slots = page.getByRole('dialog').locator('select');
    await expect(slots).toHaveCount(6);
    await expect(slots.first()).toHaveValue('5'); // FLTMODE1 in scripts/simulator.py
  });
});

test.describe('Right-to-left layout', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('argus_locale', 'ar'));
    await page.goto('/');
    await page.waitForTimeout(800);
  });

  test('Arabic turns the page around and stays inside it', async ({ page }) => {
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test('a panel opens in Arabic', async ({ page }) => {
    await page.keyboard.press('Control+k');
    await expect(page.locator('input[placeholder]').last()).toBeVisible();
    await expect(page.locator('body')).toContainText(/[؀-ۿ]/);
  });
});

test.describe('Rally points', () => {
  test('clicks on the map add points that survive a reload', async ({ page }) => {
    await openRallyPanel(page);
    await page.getByRole('button', { name: '添加备降点' }).click();

    // Away from the middle: the simulator's vehicle stands there, and its icon takes a click meant
    // for the map (a Leaflet marker does not bubble). The map re-centres when the panel opens, so
    // the icon stays in the middle whatever the panel's width.
    const map = (await page.locator('.leaflet-container').first().boundingBox())!;
    const x = map.x + map.width * 0.3;
    const y = map.y + map.height * 0.65;
    await page.mouse.click(x, y);
    await page.mouse.click(x + 60, y + 40);
    await expect(page.locator('path.rally-point')).toHaveCount(2);

    await page.reload();
    await expect(page.locator('path.rally-point')).toHaveCount(2);
  });

  test('leaving Plan ends the drawing', async ({ page }) => {
    await openRallyPanel(page);
    await page.getByRole('button', { name: '添加备降点' }).click();
    await openFromPalette(page, 'nav-fly');
    await openFromPalette(page, 'nav-plan');

    const map = (await page.locator('.leaflet-container').first().boundingBox())!;
    await page.mouse.click(map.x + map.width * 0.3, map.y + map.height * 0.65);
    await page.waitForTimeout(300);
    await expect(page.locator('path.rally-point')).toHaveCount(0);
  });
});

test.describe('Map layers', () => {
  test('a saved fence is drawn on the map', async ({ page }) => {
    await page.addInitScript(() =>
      localStorage.setItem(
        'argus_fence',
        JSON.stringify([
          { lat: 34.25, lon: 108.93 },
          { lat: 34.26, lon: 108.93 },
          { lat: 34.26, lon: 108.95 },
        ]),
      ),
    );
    await page.goto('/');
    await expect(page.locator('.leaflet-overlay-pane path').first()).toBeAttached({ timeout: 5000 });
  });
});
