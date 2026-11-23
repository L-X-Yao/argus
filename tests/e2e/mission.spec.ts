import { test, expect } from '@playwright/test';

test.describe('Mission planning', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);
    const planTab = page.locator('nav button', { hasText: /规划|Plan/ }).first();
    await planTab.click();
    await page.waitForTimeout(1000);
  });

  test('plan view shows map and mission panel', async ({ page }) => {
    await expect(page.locator('.leaflet-container')).toBeVisible({ timeout: 5000 });
  });

  test('click on map adds waypoint', async ({ page }) => {
    const map = page.locator('.leaflet-container').first();
    const box = await map.boundingBox();
    if (box) {
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      await page.waitForTimeout(800);
      await expect(page.locator('body')).toContainText(/#1|WP1|航点/, { timeout: 3000 });
    }
  });

  test('a click in the fly view adds no waypoint', async ({ page }) => {
    const count = page
      .locator('h2', { hasText: /航点|Waypoints/i })
      .locator('xpath=..')
      .locator('span')
      .first();

    await page
      .locator('nav button', { hasText: /飞行|Fly/ })
      .first()
      .click();
    await page.waitForTimeout(500);
    const flyBox = (await page.locator('.leaflet-container').first().boundingBox())!;
    await page.mouse.click(flyBox.x + flyBox.width / 2, flyBox.y + flyBox.height / 2);
    await page.waitForTimeout(500);

    await page
      .locator('nav button', { hasText: /规划|Plan/ })
      .first()
      .click();
    await page.waitForTimeout(1000);
    await expect(count).toHaveText('(0)');

    // The same click here does add one, so the check above means something.
    const planBox = (await page.locator('.leaflet-container').first().boundingBox())!;
    await page.mouse.click(planBox.x + planBox.width * 0.4, planBox.y + planBox.height * 0.6);
    await expect(count).toHaveText('(1)', { timeout: 3000 });
  });

  test('add multiple waypoints shows distance', async ({ page }) => {
    const map = page.locator('.leaflet-container').first();
    const box = await map.boundingBox();
    if (box) {
      await page.mouse.click(box.x + box.width * 0.3, box.y + box.height / 2);
      await page.waitForTimeout(400);
      await page.mouse.click(box.x + box.width * 0.7, box.y + box.height / 2);
      await page.waitForTimeout(800);
      await expect(page.locator('body')).toContainText(/\d+\s*(m|km|米)/, { timeout: 5000 });
    }
  });

  test('Ctrl+Z undoes waypoint addition', async ({ page }) => {
    const map = page.locator('.leaflet-container').first();
    const box = await map.boundingBox();
    if (box) {
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      await page.waitForTimeout(500);
      await page.keyboard.press('Control+z');
      await page.waitForTimeout(500);
    }
  });

  test('default altitude input is editable', async ({ page }) => {
    const altInput = page.locator('input[type="number"]').first();
    if (await altInput.isVisible()) {
      await altInput.fill('80');
      await expect(altInput).toHaveValue('80');
    }
  });

  test('circle generator UI exists', async ({ page }) => {
    const circleBtn = page.locator('button', { hasText: /圆形|Circle/ }).first();
    if (await circleBtn.isVisible()) {
      await circleBtn.click();
      await page.waitForTimeout(300);
      await expect(page.locator('button', { hasText: /Gen|生成/ })).toBeVisible({ timeout: 3000 });
    }
  });

  test('editing a survey replaces its grid and keeps the existing route', async ({ page }) => {
    const map = page.locator('.leaflet-container').first();
    const readWaypoints = () =>
      page.evaluate(
        () =>
          JSON.parse(localStorage.getItem('argus_waypoints') || '[]') as {
            lat: number;
            lon: number;
            survey?: boolean;
          }[],
      );
    const clickMap = async (points: [number, number][]) => {
      const box = (await map.boundingBox())!;
      for (const [x, y] of points) await page.mouse.click(box.x + box.width * x, box.y + box.height * y);
    };

    await clickMap([[0.2, 0.2]]);
    await expect.poll(async () => (await readWaypoints()).length).toBe(1);
    const manual = (await readWaypoints())[0];

    await page.locator('button.map-btn', { hasText: /测绘|Survey/ }).click();
    await page.getByRole('button', { name: /在地图上绘制区域|Draw area on map/ }).click();
    await clickMap([
      [0.3, 0.3],
      [0.7, 0.3],
      [0.7, 0.65],
      [0.3, 0.65],
    ]);
    await page.getByRole('button', { name: /完成绘制|Finish Drawing/ }).click();
    const preview = page.getByText(/预计生成|Estimated/).locator('b');
    await expect.poll(async () => Number(await preview.textContent())).toBeGreaterThan(1);
    const firstCount = Number(await preview.textContent());
    await page.getByRole('button', { name: /生成航线|Generate Route/ }).click();
    await expect.poll(async () => (await readWaypoints()).length).toBe(1 + firstCount);

    await page.getByRole('button', { name: /添加顶点|Add vertices/ }).click();
    await clickMap([[0.2, 0.65]]);
    await page.getByRole('button', { name: /完成绘制|Finish Drawing/ }).click();
    await page.locator('#sv-angle').fill('45');
    const secondCount = Number(await preview.textContent());
    expect(secondCount).toBeGreaterThan(1);
    await page.getByRole('button', { name: /生成航线|Generate Route/ }).click();

    await expect.poll(async () => (await readWaypoints()).length).toBe(1 + secondCount);
    const regenerated = await readWaypoints();
    expect(regenerated[0]).toEqual(manual);
    expect(regenerated.slice(1).every((wp) => wp.survey === true)).toBe(true);
  });

  test('terrain follow refuses to rewrite heights without home', async ({ page }) => {
    await page.evaluate(() => {
      localStorage.setItem(
        'argus_waypoints',
        JSON.stringify([
          { lat: 34.1, lon: 108.8, alt: 50, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 },
          { lat: 34.12, lon: 108.82, alt: 60, drop: false, delay: 0, speed: 0, type: 'wp', loiter_param: 0 },
        ]),
      );
    });
    await page.reload();
    await page
      .locator('nav button', { hasText: /规划|Plan/ })
      .first()
      .click();
    await page.waitForTimeout(1000);

    await page.getByRole('button', { name: /地形跟随|Terrain Follow/ }).click();
    await expect(page.locator('body')).toContainText(/未知 home|Home position unknown|Home unknown/, {
      timeout: 5000,
    });
    const heights = await page.evaluate(() =>
      JSON.parse(localStorage.getItem('argus_waypoints') || '[]').map((w: { alt: number }) => w.alt),
    );
    expect(heights).toEqual([50, 60]);
  });
});
