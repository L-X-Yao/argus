import { defineConfig, devices } from '@playwright/test';

// For the specs that drive the built app against real firmware through the backend.
// tests/e2e/run-panels-sitl.sh boots both and says where they are, so there is no
// webServer here: the main config's would start a simulator on port 8100.
export default defineConfig({
  testDir: './e2e',
  timeout: 300000,
  expect: { timeout: 15000 },
  retries: 0,
  workers: 1,
  use: {
    ...devices['Desktop Chrome'],
    viewport: { width: 1600, height: 1000 },
    baseURL: process.env.ARGUS_URL,
    headless: true,
    actionTimeout: 15000, // a control that never turns up should not take the whole test timeout
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  outputDir: '../test-results/panels-sitl',
});
