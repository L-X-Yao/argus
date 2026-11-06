import { expect, type Browser, type Locator, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Probe } from './sitl-probe';

// What the panels-sitl specs share. They drive the built app with clicks and typing only,
// and read what happened from the firmware through a Probe. run-panels-sitl.sh boots
// SITL and the backend and exports the two addresses.
export const SITL_TCP = process.env.SITL_TCP ?? '';
export const SITL_PROBE_TCP = process.env.SITL_PROBE_TCP ?? '';
export const SITL_RUN_DIR = process.env.SITL_RUN_DIR ?? '';
export const READY = Boolean(SITL_TCP && SITL_PROBE_TCP && process.env.ARGUS_URL);

const zh = readFileSync(fileURLToPath(new URL('../../src/lib/locales/zh.ts', import.meta.url)), 'utf-8');

/** The Chinese text of a locale key: the UI language in tests. */
export const label = (key: string) => zh.match(new RegExp(`'${key.replace(/\./g, '\\.')}':\\s*'([^']*)'`))?.[1] ?? key;

export async function connect(page: Page) {
  await page.goto('/');
  const disconnect = page.getByRole('button', { name: label('conn.disconnect'), exact: true });
  await page.locator('input.port-input').or(disconnect).first().waitFor();
  if (await disconnect.isVisible()) return;
  await page.locator('input.port-input').fill(`tcp:${SITL_TCP}`);
  await page.getByRole('button', { name: label('conn.connect'), exact: true }).click();
  await expect(disconnect).toBeVisible({ timeout: 30000 });
}

export async function openSession(browser: Browser): Promise<{ page: Page; probe: Probe }> {
  const page = await browser.newPage();
  // Map servers far from a hosted runner hold every connection the browser allows a host,
  // and the panels load behind them. No test here reads a tile.
  await page.route('**/api/tile/**', (route) => route.abort());
  const probe = await Probe.open(SITL_PROBE_TCP);
  await connect(page);
  return { page, probe };
}

/** Palette search also covers ids, and those are unique. */
export async function palette(page: Page, id: string) {
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog', { name: label('cmd.placeholder') });
  await dialog.locator('input').fill(id);
  await expect(dialog.locator(`[data-palette-idx="0"]`)).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(dialog).toHaveCount(0);
}

/** The Params tab and its Read button, until the read has finished. */
export async function readParams(page: Page) {
  await page.locator('nav button', { hasText: label('tab.params') }).click();
  await page.getByRole('button', { name: label('param.readAll'), exact: true }).click();
  await expect(page.getByPlaceholder(label('param.search'))).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('button', { name: label('param.readAll'), exact: true })).toBeEnabled({
    timeout: 60000,
  });
}

/** The dialog with this title. Exact: the setup wizard names the tool of each step too. */
export const dialogOf = (page: Page, title: string) =>
  page.getByRole('dialog').filter({ has: page.getByRole('heading', { name: title, exact: true }) });

/** Opens a tool panel from the palette and hands back its dialog. */
export async function tool(page: Page, id: string, title: string) {
  await palette(page, id);
  const dialog = dialogOf(page, title);
  await expect(dialog).toBeVisible();
  return dialog;
}

/** The vehicle's place on the screen, once the map has finished moving to it. */
export async function vehicleOnMap(page: Page): Promise<{ x: number; y: number }> {
  const marker = page.locator('.drone-icon');
  await expect(marker).toBeVisible({ timeout: 30000 });
  let last = '';
  await expect
    .poll(
      async () => {
        const box = await marker.boundingBox();
        const now = JSON.stringify(box);
        const still = now === last;
        last = now;
        return still;
      },
      { intervals: [400], timeout: 20000 },
    )
    .toBe(true);
  const box = (await marker.boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Closes a dialog through its own X. */
export async function close(page: Page, dialog: Locator) {
  await dialog.getByRole('button', { name: label('error.close') }).click();
  await expect(dialog).toHaveCount(0);
}
