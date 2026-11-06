import { test, expect } from '@playwright/test';

// A second tab is an observer, and the backend refuses its clear_summary, so the summary
// stays in every state push. Its close button still has to close it.
test('an observer can close the flight summary', async ({ page }) => {
  const pilot = new WebSocket('ws://127.0.0.1:8100/ws');
  await new Promise((ok) => (pilot.onopen = ok));
  const send = (msg: object) => pilot.send(JSON.stringify(msg));
  const command = (cmd: string) => send({ type: 'command', cmd });
  send({ type: 'set_role', role: 'pilot' });
  send({ type: 'connect', port: 'tcp:localhost:5770' });

  await page.goto('/');
  await expect(page.locator('button', { hasText: /^断开$|^Disconnect$/ })).toBeVisible({ timeout: 15000 });
  await expect(page.locator('body')).toContainText(/\d+\.\d+\s*V/, { timeout: 15000 });

  try {
    await expect
      .poll(
        async () => {
          // Off the ground: an arm and disarm alone reports no flight, and the simulator
          // only climbs on a mission.
          send({
            type: 'command',
            cmd: 'mission_upload',
            waypoints: [{ lat: 34.26, lon: 108.95, alt: 30, speed: 0, type: 'wp', drop: false, delay: 0 }],
          });
          await page.waitForTimeout(1000);
          command('arm');
          await page.waitForTimeout(1000);
          command('mission_start');
          await page.waitForTimeout(5000);
          command('force_disarm');
          await page.waitForTimeout(1000);
          return page.getByRole('heading', { name: /飞行完成|Flight Complete/ }).isVisible();
        },
        { message: 'no flight summary', timeout: 40000 },
      )
      .toBe(true);

    const close = page.getByRole('dialog').filter({ hasText: /飞行完成|Flight Complete/ });
    await close.getByRole('button', { name: /关闭|Close/ }).click();
    await expect(page.getByRole('heading', { name: /飞行完成|Flight Complete/ })).toBeHidden();
    await page.waitForTimeout(1500); // a few state pushes
    await expect(page.getByRole('heading', { name: /飞行完成|Flight Complete/ })).toBeHidden();
  } finally {
    command('clear_summary');
    send({ type: 'disconnect' });
    pilot.close();
  }
});
