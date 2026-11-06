import { test, expect, type Locator, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { READY, SITL_RUN_DIR, close, label, openSession, palette, tool } from './panels-sitl-helpers';
import type { Probe } from './sitl-probe';

// The tools that read what a flight left behind. Runs after panels-sitl-flight.spec.ts on
// the same SITL, whose working directory holds the log. pymavlink reads the same file for
// comparison, and SIM_VIB_FREQ_X in sitl-panels.parm puts a known tone on the gyros.
test.skip(!READY, 'run through tests/e2e/run-panels-sitl.sh');

// A copy, as the FC goes on writing to the original.
const LOG = path.join(mkdtempSync(path.join(tmpdir(), 'argus-log-')), 'flight.BIN');
const TRUTH_SCRIPT = fileURLToPath(new URL('./dflog_truth.py', import.meta.url));
const TONE_HZ = 35;

interface Truth {
  counts: Record<string, number>;
  stats: Record<string, { min: number; max: number; avg: number; n: number }>;
  roi: number[][];
}

let page: Page;
let probe: Probe;
let truth: Truth;

test.beforeAll(async ({ browser }) => {
  ({ page, probe } = await openSession(browser));
  copyFileSync(path.join(SITL_RUN_DIR, 'logs', '00000001.BIN'), LOG);
  truth = JSON.parse(execFileSync('python3', [TRUTH_SCRIPT, LOG], { maxBuffer: 1 << 26, encoding: 'utf-8' }));
});

test.afterAll(async () => {
  probe?.close();
  await page?.close();
});

async function openLog(dialog: Locator) {
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    dialog.getByRole('button', { name: label('logview.open') }).click(),
  ]);
  await chooser.setFiles(LOG);
}

test.describe('Log viewer', () => {
  test('reads the whole log, and what it plots is what pymavlink finds', async () => {
    const dialog = await tool(page, 'tool-logviewer', label('logview.title'));
    await openLog(dialog);

    // FMT describes the others and is not listed as a message.
    const { FMT: _formats, ...rest } = truth.counts;
    const total = Object.values(rest).reduce((a, b) => a + b, 0);
    await expect(dialog.getByText(label('logview.messages').replace('{n}', String(total)))).toBeVisible({
      timeout: 60000,
    });
    await expect(dialog.getByText(new RegExp(`^${Object.keys(rest).length} `))).toBeVisible();

    await dialog.getByRole('button', { name: label('logview.stats') }).click();
    const sidebar = dialog.locator('div.w-44');
    for (const [channel, expected] of Object.entries(truth.stats)) {
      const block = sidebar.locator('div.space-y-0\\.5').filter({ hasText: channel });
      await expect(block, channel).toBeVisible();
      const cells = (await block.locator('span.font-mono').allTextContents()).map(Number);
      expect(cells[0], `${channel} min`).toBeCloseTo(expected.min, 2);
      expect(cells[1], `${channel} max`).toBeCloseTo(expected.max, 2);
      expect(cells[2], `${channel} mean`).toBeCloseTo(expected.avg, 2);
    }
    await close(page, dialog);
  });

  test('the table lists every row of the types picked, and a drag zooms the chart', async () => {
    const dialog = await tool(page, 'tool-logviewer', label('logview.title'));
    await openLog(dialog);
    await expect(dialog.locator('canvas')).toBeVisible({ timeout: 60000 });

    const box = (await dialog.locator('canvas').boundingBox())!;
    await page.mouse.move(box.x + 200, box.y + 100);
    await page.mouse.down();
    await page.mouse.move(box.x + 400, box.y + 100, { steps: 5 });
    await page.mouse.up();
    await expect(dialog.getByText(label('logview.zoomHint'))).toBeVisible();
    await dialog.locator('canvas').dblclick();
    await expect(dialog.getByText(label('logview.zoomHint'))).toHaveCount(0);

    await dialog.getByRole('button', { name: label('logview.table') }).click();
    const rows = ['ATT', 'BARO', 'BAT', 'GPS', 'VIBE'].reduce((sum, t) => sum + truth.counts[t], 0);
    await expect(dialog.getByText(label('logview.rows').replace('{n}', String(rows)))).toBeVisible();
    await close(page, dialog);
  });
});

test.describe('FFT', () => {
  test('finds the tone the simulator put on the gyros', async () => {
    const dialog = await tool(page, 'tool-fft', label('fft.title'));
    await openLog(dialog);
    const notch = dialog.locator('div.bg-warning\\/10');
    await expect(notch).toBeVisible({ timeout: 60000 });
    const peaks = (await notch.locator('span.font-mono').allTextContents())
      .filter((t) => t.endsWith('Hz'))
      .map((t) => parseFloat(t));
    expect(peaks.some((hz) => Math.abs(hz - TONE_HZ) < 1.5)).toBe(true);
    await close(page, dialog);
  });
});

test.describe('Point of interest', () => {
  test('the set and the clear both reached the FC, by its own log', async () => {
    expect(truth.roi.length).toBeGreaterThanOrEqual(2);
    expect(truth.roi[0][0]).not.toBe(0);
    // X, Y, result: all zero turns the ROI off, and 0 is MAV_RESULT_ACCEPTED.
    expect(truth.roi[truth.roi.length - 1]).toEqual([0, 0, 0]);
  });
});

test.describe('3D preview', () => {
  test('draws the mission the FC holds', async () => {
    const onFc = (await probe.store()).length - 3; // home, takeoff and the closing RTL
    expect(onFc).toBeGreaterThan(0);
    await palette(page, 'mission-download');
    const dialog = await tool(page, 'tool-mission3d', label('panel.mission3d'));
    await expect(dialog.getByText(`${onFc} WP`, { exact: true })).toBeVisible();

    const canvas = dialog.locator('canvas');
    const picture = () => canvas.evaluate((c) => (c as HTMLCanvasElement).toDataURL());
    const before = await picture();
    await canvas.hover();
    await page.mouse.wheel(0, -300);
    await expect(dialog.getByText(/Zoom: 1\.[1-9]x/)).toBeVisible();
    await expect.poll(picture).not.toBe(before);
    await close(page, dialog);
  });
});

test.describe('Remote', () => {
  test('counts the browsers on this backend', async ({ browser }) => {
    const dialog = await tool(page, 'tool-remote', label('remote.title'));
    const clients = dialog.getByText(label('remote.clients')).locator('xpath=following-sibling::div').locator('span');
    await expect.poll(async () => Number(await clients.textContent())).toBe(1);

    const other = await browser.newPage();
    await other.goto('/');
    await expect.poll(async () => (await (await page.request.get('/api/session')).json()).clients).toBe(2);
    await expect.poll(async () => Number(await clients.textContent()), { timeout: 10000 }).toBe(2);
    await other.close();
    await expect.poll(async () => Number(await clients.textContent()), { timeout: 10000 }).toBe(1);
    await close(page, dialog);
  });
});

