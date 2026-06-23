import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:8099",
  },
  webServer: {
    command: "bash e2e/serve-fixture.sh",
    url: "http://127.0.0.1:8099/api/runs",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
