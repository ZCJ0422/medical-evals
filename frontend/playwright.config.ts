import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  testIgnore: ["**/._*.spec.ts"],
  // The API fixture and SQLite database are single-machine shared state.
  workers: 1,
  fullyParallel: false,
  globalSetup: "./tests/global-setup.ts",
  use: {
    baseURL: "http://127.0.0.1:3000",
    ...devices["Desktop Chrome"],
    headless: true,
  },
  webServer: [
    { command: "npm run dev -- --hostname 127.0.0.1", url: "http://127.0.0.1:3000", reuseExistingServer: true, timeout: 120000 },
    { command: "uv run python -m medical_evals_api.cli api", cwd: "../backend", url: "http://127.0.0.1:8000/healthz", reuseExistingServer: true, timeout: 120000 },
  ],
});
