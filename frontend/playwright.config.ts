import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

// Each suite owns its database and servers; never reuse a developer's API.
const testRoot = process.env.MEDICAL_EVALS_E2E_ROOT ?? mkdtempSync(path.join(tmpdir(), "medical-evals-e2e-"));
process.env.MEDICAL_EVALS_E2E_ROOT = testRoot;
Object.assign(process.env, {
  MEDICAL_EVALS_DATABASE_URL: `sqlite+pysqlite:///${path.join(testRoot, "workbench.sqlite3")}`,
  MEDICAL_EVALS_DATABASE_PATH: path.join(testRoot, "legacy.sqlite3"),
  MEDICAL_EVALS_ARTIFACT_DIR: path.join(testRoot, "artifacts"),
  MEDICAL_EVALS_REDIS_URL: "redis://127.0.0.1:1/0",
  MEDICAL_EVALS_FRONTEND_ORIGIN: "http://127.0.0.1:3107",
  NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8107",
});

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  testIgnore: ["**/._*.spec.ts"],
  workers: 1,
  fullyParallel: false,
  globalSetup: "./tests/global-setup.ts",
  use: { baseURL: "http://127.0.0.1:3107", ...devices["Desktop Chrome"], headless: true },
  webServer: [
    { command: "npm run dev -- --hostname 127.0.0.1 --port 3107", url: "http://127.0.0.1:3107", reuseExistingServer: false, timeout: 120000 },
    { command: "uv run --no-sync python -m uvicorn medical_evals_api.main:app --host 127.0.0.1 --port 8107", cwd: "../backend", url: "http://127.0.0.1:8107/healthz", reuseExistingServer: false, timeout: 120000 },
  ],
});
