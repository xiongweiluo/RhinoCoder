import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const uiRoot = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(uiRoot, "../..");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  timeout: 30_000,
  expect: {timeout: 8_000},
  use: {
    baseURL: "http://127.0.0.1:7862",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "python -m agent.ui_server --port 7862",
    cwd: projectRoot,
    url: "http://127.0.0.1:7862/api/demo-scenarios",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
