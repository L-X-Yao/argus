import { test, expect, type Page } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const PORT = 8131;
const TOKEN = 'e2e-access-token-1234567890';

let server: ChildProcess;

/** Collects 401 responses, leaving out the login call a wrong token is meant to fail. */
function trackDenied(page: Page): string[] {
  const denied: string[] = [];
  page.on('response', (r) => {
    if (r.status() === 401 && !r.url().includes('/api/auth/')) denied.push(r.url());
  });
  return denied;
}

async function signIn(page: Page, token = TOKEN) {
  const input = page.locator('#auth-token-input');
  await input.fill(token);
  await input.press('Enter');
}

function restStatus(page: Page, route: string) {
  return page.evaluate((url) => fetch(url).then((r) => r.status), route);
}

test.describe('Token authentication', () => {
  test.use({ baseURL: `http://localhost:${PORT}` });

  test.beforeAll(async () => {
    server = spawn('python', ['run.py', '--port', String(PORT)], {
      cwd: repoRoot,
      env: { ...process.env, ARGUS_NO_BROWSER: '1', GCS_AUTH_TOKEN: TOKEN },
      stdio: 'ignore',
    });
    await expect
      .poll(
        () =>
          fetch(`http://127.0.0.1:${PORT}/health`).then(
            (r) => r.status,
            () => 0,
          ),
        { timeout: 15000 },
      )
      .toBe(200);
  });

  test.afterAll(() => {
    server.kill();
  });

  test('keeps the views closed until the token is accepted', async ({ page }) => {
    const denied = trackDenied(page);
    await page.goto('/');
    await expect(page.locator('#auth-token-input')).toBeVisible();
    await expect(page.locator('.leaflet-container')).toHaveCount(0);

    await signIn(page, 'wrong-token');
    await expect(page.getByRole('dialog')).toContainText(/令牌无效|Invalid token/i);
    await expect(page.locator('.leaflet-container')).toHaveCount(0);

    await signIn(page);
    await expect(page.locator('#auth-token-input')).toHaveCount(0);
    await expect(page.locator('.leaflet-container')).toBeVisible();
    // A style that does not exist gets past the token and no further: a real tile would wait on
    // a map server, which has gone silent for minutes on end from CI. Asked beside the page,
    // with its cookie: inside it the service worker puts every tile request in one queue, and
    // this one then waits behind the map's own tiles for that same server.
    expect((await page.request.get('/api/tile/none/0/0/0')).status()).toBe(404);
    expect(await restStatus(page, '/api/ports')).toBe(200);
    expect(denied).toEqual([]);
  });

  test('opens the websocket with the accepted token', async ({ page }) => {
    await page.goto('/');
    await signIn(page);
    await expect
      .poll(() =>
        page.evaluate(() =>
          fetch('/api/session')
            .then((r) => r.json())
            .then((d) => d.clients),
        ),
      )
      .toBeGreaterThan(0);
  });

  test('keeps the session cookie away from page scripts', async ({ page, context }) => {
    await page.goto('/');
    await signIn(page);
    await expect(page.locator('.leaflet-container')).toBeVisible();

    const session = (await context.cookies()).find((c) => c.name === 'argus_session');
    expect(session?.httpOnly).toBe(true);
    expect(session?.sameSite).toBe('Strict');
    expect(session?.value).not.toContain(TOKEN);
    expect(await page.evaluate(() => document.cookie)).not.toContain('argus_session');
  });

  test('restores the session from the saved token without asking again', async ({ page, context }) => {
    await page.goto('/');
    await signIn(page);
    await expect(page.locator('.leaflet-container')).toBeVisible();

    // A browser restart drops the session cookie and keeps localStorage. Leave
    // the page first: requests it still has in flight would count as denied.
    await page.goto('about:blank');
    await context.clearCookies();
    const denied = trackDenied(page);
    await page.goto('/');
    await expect(page.locator('.leaflet-container')).toBeVisible();
    await expect(page.locator('#auth-token-input')).toHaveCount(0);
    expect(await restStatus(page, '/api/ports')).toBe(200);
    expect(denied).toEqual([]);
  });

  test.describe('with a backend that does not answer', () => {
    // A service worker would bypass page.route.
    test.use({ serviceWorkers: 'block' });

    test('opens the app when the auth status hangs', async ({ page }) => {
      await page.route('**/api/auth/status', () => {});
      await page.goto('/');
      await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: 8000 });
    });

    test('shows the dialog when login hangs', async ({ page }) => {
      await page.addInitScript(() => localStorage.setItem('argus_auth_token', 'saved-token'));
      await page.route('**/api/auth/login', () => {});
      await page.goto('/');
      await expect(page.locator('#auth-token-input')).toBeVisible({ timeout: 8000 });
      expect(await page.evaluate(() => localStorage.getItem('argus_auth_token'))).toBe('saved-token');
    });

    test('asks for the token when the backend appears after the app opened', async ({ page }) => {
      await page.route('**/api/auth/status', (route) => route.abort());
      await page.goto('/');
      await expect(page.locator('.leaflet-container')).toBeVisible();

      await page.unroute('**/api/auth/status');
      await expect(page.locator('#auth-token-input')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('.leaflet-container')).toHaveCount(0);
    });
  });

  test('asks again when the saved token no longer works', async ({ page, context }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.setItem('argus_auth_token', 'stale-token'));
    await context.clearCookies();
    await page.reload();
    await expect(page.locator('#auth-token-input')).toBeVisible();
    await expect(page.locator('.leaflet-container')).toHaveCount(0);
    expect(await page.evaluate(() => localStorage.getItem('argus_auth_token'))).toBeNull();
  });
});

// What a phone on the network meets when Argus was started with a token and a network
// address and nothing else: the page loads, and the backend turns its login away because the
// address it was opened from is not in ARGUS_CORS_ORIGINS. Up to v3.8.0 the dialog then said
// "invalid token" to someone who had typed the right one.
test.describe('A page opened from an address the backend does not list', () => {
  const OTHER_PORT = 8132;
  let other: ChildProcess;

  test.use({ baseURL: `http://localhost:${OTHER_PORT}` });

  test.beforeAll(async () => {
    // A list of one's own replaces the default one, so this server's own page is not on it.
    other = spawn('python', ['run.py', '--port', String(OTHER_PORT)], {
      cwd: repoRoot,
      env: { ...process.env, ARGUS_NO_BROWSER: '1', GCS_AUTH_TOKEN: TOKEN, ARGUS_CORS_ORIGINS: 'http://localhost:5173' },
      stdio: 'ignore',
    });
    await expect
      .poll(
        () =>
          fetch(`http://127.0.0.1:${OTHER_PORT}/health`).then(
            (r) => r.status,
            () => 0,
          ),
        { timeout: 15000 },
      )
      .toBe(200);
  });

  test.afterAll(() => {
    other.kill();
  });

  test('is told what to add on the server, not that the token is wrong', async ({ page }) => {
    await page.goto('/');
    await signIn(page);

    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('ARGUS_CORS_ORIGINS');
    await expect(dialog).toContainText(`http://localhost:${OTHER_PORT}`);
    await expect(dialog).not.toContainText(/令牌无效|Invalid token/i);
    await expect(page.locator('.leaflet-container')).toHaveCount(0);
  });

  test('keeps a saved token: it is not what was refused', async ({ page }) => {
    await page.addInitScript((token) => localStorage.setItem('argus_auth_token', token), TOKEN);
    await page.goto('/');
    await expect(page.locator('#auth-token-input')).toBeVisible({ timeout: 8000 });
    expect(await page.evaluate(() => localStorage.getItem('argus_auth_token'))).toBe(TOKEN);
  });
});
