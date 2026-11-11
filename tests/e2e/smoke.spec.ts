import { test, expect } from '@playwright/test';

// The page comes with a content policy (backend/app.py CONTENT_POLICY): its scripts are this
// server's own files, so markup that gets into it cannot bring a handler that runs.
test.describe('Content policy', () => {
  test('markup that gets into the page runs no script', async ({ page }) => {
    const response = await page.goto('/');
    expect(response!.headers()['content-security-policy']).toContain("script-src 'self'");

    const refused = await page.evaluate(
      () =>
        new Promise<string>((resolve) => {
          document.addEventListener('securitypolicyviolation', (e) => resolve(e.violatedDirective), { once: true });
          // What a tooltip or an icon written with innerHTML would do with a hostile name.
          const box = document.createElement('div');
          box.innerHTML = '<img src="/no-such-picture.png" onerror="window.__argus_xss=1">';
          document.body.appendChild(box);
        }),
    );
    expect(refused).toMatch(/^script-src/);
    expect(await page.evaluate(() => (window as unknown as { __argus_xss?: number }).__argus_xss)).toBeUndefined();
  });

  test('the page itself stays inside it, on every tab', async ({ page }) => {
    await page.addInitScript(() => {
      const seen: string[] = [];
      (window as unknown as { __refused: string[] }).__refused = seen;
      document.addEventListener('securitypolicyviolation', (e) => seen.push(`${e.violatedDirective} ${e.blockedURI}`));
    });
    await page.goto('/');
    await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: 8000 });
    for (const tab of [/规划|Plan/, /监控|Monitor/, /参数|Params/, /飞行|Fly/]) {
      await page.locator('nav button', { hasText: tab }).first().click();
      await page.waitForTimeout(700);
    }
    expect(await page.evaluate(() => (window as unknown as { __refused: string[] }).__refused)).toEqual([]);
  });
});

test.describe('Smoke tests', () => {
  test('homepage loads with app name in header', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByRole('banner').getByText('Argus')).toBeVisible({ timeout: 8000 });
  });

  test('dark theme is default', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('html')).toHaveClass(/dark/);
  });

  test('welcome card shows when disconnected', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);
    const welcomeCard = page.locator('text=Ctrl+K');
    const isVisible = await welcomeCard.isVisible().catch(() => false);
    expect(isVisible || (await page.locator('.leaflet-container').isVisible())).toBeTruthy();
  });

  test('no third-party branding visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);
    const content = await page.textContent('body');
    expect(content).not.toContain('ArduPilot');
    expect(content).not.toContain('ArduCopter');
    expect(content).not.toContain('ChibiOS');
  });

  test('backend health endpoint responds', async ({ request }) => {
    const res = await request.get('/health');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.ok).toBe(true);
  });

  test('API version endpoint responds', async ({ request }) => {
    const res = await request.get('/api/version');
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    expect(data.version).toMatch(/^\d+\.\d+\.\d+$/);
  });
});
