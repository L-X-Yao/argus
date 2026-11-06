import { test, expect } from '@playwright/test';
import fs from 'node:fs';

// Hours of flying in minutes of real firmware, watching for leaks in the browser and the
// backend. Not part of CI: see tests/e2e/run-soak.sh, which sets all of this up.
const MINUTES = Number(process.env.SOAK_MINUTES ?? 0);
const BACKEND = process.env.SOAK_BACKEND ?? '';
const BACKEND_PID = Number(process.env.SOAK_BACKEND_PID ?? 0);
const FC = process.env.SOAK_FC ?? '';
const OUT = process.env.SOAK_OUT ?? 'soak.csv';
test.skip(!MINUTES, 'SOAK_MINUTES is not set');
test.use({
  baseURL: `http://${BACKEND}`,
  launchOptions: { args: ['--enable-precise-memory-info', '--js-flags=--expose-gc'] },
});

const rssMb = () => {
  const status = fs.readFileSync(`/proc/${BACKEND_PID}/status`, 'utf8');
  return Number(status.match(/VmRSS:\s+(\d+)/)![1]) / 1024;
};

/** Slope in MB per hour of a least-squares line through the samples. */
function slope(points: [number, number][]): number {
  const n = points.length;
  const mx = points.reduce((a, p) => a + p[0], 0) / n;
  const my = points.reduce((a, p) => a + p[1], 0) / n;
  const num = points.reduce((a, p) => a + (p[0] - mx) * (p[1] - my), 0);
  const den = points.reduce((a, p) => a + (p[0] - mx) ** 2, 0);
  return (num / den) * 60;
}

test('a long session does not leak', async ({ page }) => {
  test.setTimeout((MINUTES + 10) * 60000);

  const state: Record<string, unknown> = {};
  const pilot = new WebSocket(`ws://${BACKEND}/ws`);
  await new Promise((ok) => (pilot.onopen = ok));
  pilot.onmessage = (e) => {
    const m = JSON.parse(e.data as string);
    if (m.type === 'state') Object.assign(state, m);
  };
  const send = (msg: object) => pilot.send(JSON.stringify(msg));
  const command = (cmd: string, param?: number, data: object = {}) => send({ type: 'command', cmd, param, ...data });
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  const until = async (ok: () => boolean, ms: number) => {
    const end = Date.now() + ms;
    while (Date.now() < end && !ok()) await sleep(200);
    return ok();
  };

  send({ type: 'set_role', role: 'pilot' });
  send({ type: 'connect', port: `tcp:${FC}` });
  await page.goto('/');
  await expect(page.locator('button', { hasText: /^断开$|^Disconnect$/ })).toBeVisible({ timeout: 30000 });
  await until(() => Number(state.gps_fix_raw) >= 3 && (Number(state.ekf_flags) & 0x10) !== 0, 180000);

  let flights = 0;
  let flying = true;
  const fly = async () => {
    while (flying) {
      command('mode', 4);
      await sleep(1000);
      command('arm');
      if (!(await until(() => state.armed === true, 10000))) continue;
      command('takeoff', undefined, { alt: 20 });
      await until(() => Number(state.alt_rel) > 15, 60000);
      await sleep(10000);
      command('rtl');
      await until(() => state.armed === false, 120000);
      flights += 1;
      command('clear_summary');
    }
  };
  const flown = fly();

  const start = Date.now();
  const heap: [number, number][] = [];
  const rss: [number, number][] = [];
  fs.writeFileSync(OUT, 'minute,heap_mb,dom_nodes,backend_rss_mb,flights,frames\n');
  while (Date.now() - start < MINUTES * 60000) {
    await sleep(60000);
    const minute = (Date.now() - start) / 60000;
    const [heapMb, nodes] = await page.evaluate(() => {
      (window as unknown as { gc: () => void }).gc();
      const memory = (performance as unknown as { memory: { usedJSHeapSize: number } }).memory;
      return [memory.usedJSHeapSize / 1048576, document.getElementsByTagName('*').length];
    });
    const backendMb = rssMb();
    heap.push([minute, heapMb]);
    rss.push([minute, backendMb]);
    fs.appendFileSync(
      OUT,
      `${minute.toFixed(1)},${heapMb.toFixed(1)},${nodes},${backendMb.toFixed(1)},${flights},${state.frames}\n`,
    );
  }
  flying = false;
  await flown;
  pilot.close();

  // The first third is the app filling its caches and histories up to their limits.
  const settled = (points: [number, number][]) => points.slice(Math.floor(points.length / 3));
  const heapSlope = slope(settled(heap));
  const rssSlope = slope(settled(rss));
  console.log(`flights ${flights}, heap ${heapSlope.toFixed(1)} MB/h, backend ${rssSlope.toFixed(1)} MB/h`);
  expect(flights).toBeGreaterThan(0);
  expect(heapSlope).toBeLessThan(5);
  expect(rssSlope).toBeLessThan(5);
});
