import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60000,
  expect: { timeout: 10000 },
  retries: 1,
  workers: 1,
  use: {
    baseURL: 'http://localhost:8100',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
  outputDir: './test-results',
  webServer: {
    command: 'ARGUS_NO_BROWSER=1 python run.py --sim',
    url: 'http://localhost:8100/health',
    timeout: 15000,
    reuseExistingServer: true,
  },
});
