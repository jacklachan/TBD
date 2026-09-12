import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 25_000 },
  workers: 1,
  use: {
    baseURL: process.env.APP_URL || "http://127.0.0.1:5173",
    channel: "chrome",
    viewport: { width: 1440, height: 1100 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  reporter: "list",
});
