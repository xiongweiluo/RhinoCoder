import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const uiRoot = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./e2e",
  testMatch: ["public-demo.spec.ts", "hosted-public.spec.ts"],
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  timeout: 30_000,
  expect: {timeout: 8_000},
  use: {
    baseURL: "http://127.0.0.1:7863",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run preview:public",
    cwd: uiRoot,
    url: "http://127.0.0.1:7863/",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
