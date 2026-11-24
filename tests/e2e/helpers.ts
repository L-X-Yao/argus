import { expect, type Page } from '@playwright/test';

export async function connectSimulator(page: Page) {
  await page.goto('/');
  await page.waitForTimeout(1500);

  // Idempotent: the backend link is global, so a prior test (or spec) that
  // failed before its cleanup leaves the UI connected — in that state the
  // port input doesn't render and fill() would burn the whole test timeout.
  const disconnectBtn = page.locator('button', { hasText: /^断开$|^Disconnect$/ });
  if (await disconnectBtn.isVisible({ timeout: 500 }).catch(() => false)) {
    return;
  }

  const portInput = page.locator('input.port-input').first();
  await portInput.fill('tcp:localhost:5770');
  await page.waitForTimeout(300);

  const connectBtn = page.locator('button', { hasText: /^连接$|^Connect$/ }).first();
  await connectBtn.click();

  await expect(page.locator('button', { hasText: /^断开$|^Disconnect$/ })).toBeVisible({ timeout: 15000 });
  // Wait for actual telemetry, not just the Disconnect button: the backend
  // link is global and shared across every spec, so on a busy CI run the
  // heartbeat can lag the button by seconds. Downstream steps (param fetch,
  // mode buttons) silently no-op against a not-yet-live link — the voltage
  // readout in the StatusBar is the first proof the sim is actually pushing.
  await expect(page.locator('body')).toContainText(/\d+\.\d+\s*V/, { timeout: 15000 });
}

/** Whether the shared backend link is up, from the backend itself. The page's button lags
 * behind it, and the backend reconnects a dropped TCP link on its own. */
export async function backendConnected(page: Page): Promise<boolean> {
  return page.evaluate(async () => {
    try {
      const r = await fetch('/api/session', { cache: 'no-store' });
      return r.ok && (await r.json()).connected === true;
    } catch {
      return false;
    }
  });
}

export async function disconnectIfConnected(page: Page) {
  // The backend link is global and shared by every spec of the no-backend
  // group; a prior spec whose cleanup was skipped by a failed assertion
  // leaves the page showing a vehicle. Whoever needs the disconnected
  // welcome flow clears that first.
  //
  // The backend is asked whether a link is up, not the page: probing the
  // DOM for a button that is absent costs its whole timeout on every
  // disconnected test, and 3 s here outlived the 4 s toast that the WebGL2
  // fallback test reads (Windows, where the page mounts slower). The header
  // is still waited for: a cold goto may be mounting. The click is only
  // confirmed done when the button is gone, so the link is truly released.
  await expect(page.locator('header').first()).toBeVisible({ timeout: 15000 });
  if (!(await backendConnected(page))) return;
  const disconnectBtn = page.locator('button', { hasText: /^断开$|^Disconnect$/ });
  await disconnectBtn.waitFor({ state: 'visible', timeout: 10000 });
  await disconnectBtn.click();
  await expect(disconnectBtn).toBeHidden({ timeout: 10000 });
}

/**
 * The command palette, opened and searched. Its keys are App's, attached once the page has
 * mounted, and the palette is a chunk of its own, loaded at the first Ctrl+K. A fixed wait and
 * the last input of the page typed into the connection form whenever that chunk came late, and
 * the panel asked for never opened.
 */
export async function openPalette(page: Page) {
  await expect(page.locator('header').first()).toBeVisible({ timeout: 15000 });
  await page.keyboard.press('Control+k');
  const palette = page.getByRole('dialog', { name: /搜索命令|Search commands/ });
  await expect(palette.locator('input')).toBeVisible({ timeout: 15000 });
  return palette;
}

export async function searchPalette(page: Page, query: string) {
  const palette = await openPalette(page);
  await palette.locator('input').fill(query);
  await page.waitForTimeout(300);
  return palette;
}
