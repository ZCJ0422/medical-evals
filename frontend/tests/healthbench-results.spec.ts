import { test, expect } from "@playwright/test";

const summary = (completedCount: number) => ({
  run_id: "healthbench-e2e",
  name: "HealthBench E2E",
  status: "completed",
  dataset_version_id: "medical-healthbench.smoke.v1",
  target_model_id: "target-model",
  judge_model_id: "judge-model",
  created_at: "2026-08-21T00:00:00Z",
  updated_at: "2026-08-21T00:00:00Z",
  error: null,
  progress: { stage: "completed", progress_percent: 100 },
  total_score: 0.75,
  dimension_scores: { rubric_score: 0.75, "tag:safety": 0.75 },
  accuracy: 0.75,
  parse_success_rate: null,
  request_success_count: completedCount,
  parse_failed_count: 0,
  error_categories: {},
  completed_count: completedCount,
  failed_count: 0,
  retry_count: 0,
});

const sample = (index: number) => ({
  index,
  sample_id: `healthbench-${index + 1}`,
  raw_output: "Seek care if symptoms worsen.",
  rubric_judgments: [{ criteria_met: true, explanation: "meets the criterion" }],
  score: 0.75,
});

async function prepareAuthenticatedPage(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: { id: "e2e", username: "admin", role: "admin", status: "active" } }));
  await page.addInitScript(() => {
    window.sessionStorage.setItem("medical_evals_access_token", "e2e-token");
    window.localStorage.removeItem("medical_evals_locale");
  });
}

test("HealthBench sample records keep the answer in the scrollable panel only", async ({ page }) => {
  await prepareAuthenticatedPage(page);
  await page.route("**/api/v1/evaluations/healthbench-e2e/summary", (route) => route.fulfill({ json: summary(1) }));
  await page.route("**/api/v1/evaluations/healthbench-e2e/artifacts/run.log", (route) => route.fulfill({ body: "run started\n", contentType: "text/plain" }));
  await page.route("**/api/v1/evaluations/healthbench-e2e/samples?limit=50&offset=0", (route) => route.fulfill({ json: { run_id: "healthbench-e2e", offset: 0, limit: 50, total: 1, samples: [sample(0)] } }));

  await page.goto("/app/evaluations/healthbench-e2e/results");
  const record = page.locator(".sample-record");
  await expect(record).toBeVisible();
  await expect(record.locator(".sample-raw-output")).toHaveText("Seek care if symptoms worsen.");
  await expect(record.getByText("Seek care if symptoms worsen.", { exact: true })).toHaveCount(1);
  await expect(record.getByText("meets the criterion")).toBeVisible();
  await record.getByText(/Rubric judgments|Rubric 评分明细/).click();
  await expect(record.getByText("meets the criterion")).toBeHidden();
  await record.getByText(/Rubric judgments|Rubric 评分明细/).click();
  await expect(record.getByText("meets the criterion")).toBeVisible();
});

test("running HealthBench results refresh samples only when the persisted count changes", async ({ page }) => {
  await prepareAuthenticatedPage(page);
  let persistedCount = 1;
  let samplePayloadCount = 1;
  let sampleCalls = 0;
  await page.route("**/api/v1/evaluations/healthbench-live/summary", (route) => {
    return route.fulfill({ json: { ...summary(persistedCount), status: "running", progress: { progress_percent: persistedCount * 50, stage: "target_model" } } });
  });
  await page.route("**/api/v1/evaluations/healthbench-live/artifacts/run.log", (route) => route.fulfill({ body: "running\n", contentType: "text/plain" }));
  await page.route("**/api/v1/evaluations/healthbench-live/samples?limit=50&offset=0", (route) => {
    sampleCalls += 1;
    return route.fulfill({ json: { task_id: "healthbench-live", offset: 0, limit: 50, total: samplePayloadCount, samples: Array.from({ length: samplePayloadCount }, (_, index) => sample(index)) } });
  });

  await page.goto("/app/evaluations/healthbench-live/results");
  await expect.poll(() => sampleCalls).toBeGreaterThanOrEqual(1);
  await page.waitForLoadState("networkidle");
  const initialSampleCalls = sampleCalls;
  await page.waitForTimeout(3200);
  expect(sampleCalls).toBe(initialSampleCalls);
  persistedCount = 2;
  samplePayloadCount = 2;
  await page.waitForTimeout(3200);
  await expect.poll(() => sampleCalls).toBeGreaterThan(initialSampleCalls);
});
