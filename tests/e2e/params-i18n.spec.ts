import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { connectSimulator, disconnectIfConnected } from './helpers';

// The panel's own rendering of the translated metadata. The backend merge is covered by
// tests/test_contract_param_meta.py; this spec pins the response shape and the UI behaviour.
const META = {
  _meta: {
    vehicle: 'copter',
    series: '4.6.3',
    locale: 'zh',
    selection: 'fw',
    translation: 'machine',
    translated: 4,
    total: 5,
    available_series: ['4.5.7', '4.6.3', '4.7.1'],
    data_version: 'fixture',
    schema: 1,
  },
  BATT_CAPACITY: {
    desc: 'Battery capacity',
    human: 'Battery capacity',
    units: 'mAh',
    range: [0, 100000],
    default: 3300,
    tr: { desc: '电池容量', human: '电池容量', status: 'machine' },
  },
  RTL_ALT: {
    desc: 'Minimum altitude to return to launch',
    human: 'RTL altitude',
    units: 'cm',
    range: [0, 100000],
    default: 1500,
    tr: { desc: '返航的最低高度', human: '返航高度', status: 'reviewed' },
  },
  LOG_BITMASK: {
    desc: 'Logging bitmask',
    human: 'Logging bitmask',
    bitmask: { '0': 'Fast Attitude', '1': 'Attitude', '2': 'GPS' },
    tr: {
      desc: '日志位掩码',
      human: '日志位掩码',
      bitmask: { '0': '快速姿态', '1': '姿态', '2': 'GPS' },
      status: 'generated',
    },
  },
  FLTMODE1: {
    desc: 'Flight mode for switch position 1',
    human: 'Flight mode 1',
    values: { '0': 'Stabilize', '1': 'Acro', '2': 'AltHold' },
    tr: {
      desc: '拨杆位置 1 的飞行模式',
      human: '飞行模式 1',
      values: { '0': '自稳', '1': '特技', '2': '定高' },
      status: 'reviewed',
    },
  },
  RC1_MAX: {
    desc: 'RC1 maximum',
    human: 'RC1 maximum',
    units: 'us',
    range: [800, 2200],
    default: 2000,
  },
};

test.describe('Parameter descriptions in the page language', () => {
  const row = (page: import('@playwright/test').Page, name: string) =>
    page.locator('div.font-bold.font-mono', { hasText: name }).first();

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('argus_locale', 'zh'));
    await page.route('**/api/param_meta**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(META) }),
    );
  });

  test.afterEach(async ({ page }) => {
    await disconnectIfConnected(page);
  });

  test('shows the translated description, the machine badge and the English original', async ({ page }) => {
    await connectSimulator(page);
    await page
      .locator('nav button', { hasText: /参数|Params/ })
      .first()
      .click();
    await page
      .locator('button', { hasText: /读取|Read/ })
      .first()
      .click();
    await expect(page.locator('input[type="text"]').first()).toBeVisible({ timeout: 15000 });

    await row(page, 'BATT_CAPACITY').click();
    await expect(page.getByText('电池容量', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('机器翻译', { exact: true }).first()).toBeVisible();

    await page.getByRole('button', { name: '显示英文原文' }).click();
    await expect(page.locator('p', { hasText: 'Battery capacity' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: '显示译文' })).toBeVisible();
  });

  test('shows reviewed and generated labels, and falls back to English without a translation', async ({ page }) => {
    await connectSimulator(page);
    await page
      .locator('nav button', { hasText: /参数|Params/ })
      .first()
      .click();
    await page
      .locator('button', { hasText: /读取|Read/ })
      .first()
      .click();
    await expect(page.locator('input[type="text"]').first()).toBeVisible({ timeout: 15000 });

    await row(page, 'RTL_ALT').click();
    await expect(page.getByText('已审校', { exact: true }).first()).toBeVisible();
    await row(page, 'RTL_ALT').click();

    await row(page, 'LOG_BITMASK').click();
    await expect(page.getByText('自动生成', { exact: true }).first()).toBeVisible();
    await row(page, 'LOG_BITMASK').click();

    await row(page, 'RC1_MAX').click();
    await expect(page.getByText('RC1 maximum', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('EN', { exact: true }).first()).toBeVisible();
  });

  test('searches translated text and exports the translated CSV with the English column', async ({ page }) => {
    await connectSimulator(page);
    await page
      .locator('nav button', { hasText: /参数|Params/ })
      .first()
      .click();
    await page
      .locator('button', { hasText: /读取|Read/ })
      .first()
      .click();
    const search = page.getByPlaceholder('搜索参数...');
    await expect(search).toBeVisible({ timeout: 15000 });

    await search.fill('Battery capacity');
    await expect(row(page, 'BATT_CAPACITY')).toBeVisible();

    await search.fill('电池');
    await expect(row(page, 'BATT_CAPACITY')).toBeVisible();
    await expect(row(page, 'RTL_ALT')).toHaveCount(0);

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'CSV', exact: true }).click(),
    ]);
    const csv = readFileSync(await download.path(), 'utf-8');
    expect(csv).toContain('DescriptionEN');
    expect(csv).toContain('电池容量');
  });

  test('offers the metadata series selector', async ({ page }) => {
    await connectSimulator(page);
    await page
      .locator('nav button', { hasText: /参数|Params/ })
      .first()
      .click();
    await page
      .locator('button', { hasText: /读取|Read/ })
      .first()
      .click();
    await expect(page.locator('input[type="text"]').first()).toBeVisible({ timeout: 15000 });
    const select = page.getByRole('combobox', { name: '说明版本' });
    await expect(select).toBeVisible();
    await expect(select).toContainText('自动');
    await expect(select).toContainText('4.6.3');
  });
});
