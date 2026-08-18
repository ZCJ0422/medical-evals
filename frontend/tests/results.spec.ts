import { test, expect } from "@playwright/test";

test("completed evaluation opens a result summary", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("medical-evals-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.goto("/app/evaluations");
  const completed = page.getByRole("row").filter({ hasText: "completed" }).first();
  await expect(completed).toBeVisible();
  await completed.getByRole("link", { name: /View results/ }).click();
  await expect(page.getByText(/Evaluation results|测评结果/, { exact: true })).toBeVisible();
  await expect(page.getByText(/Parse success rate|解析成功率/)).toBeVisible();
  await expect(page.getByText(/Answer accuracy|答案准确率/)).toBeVisible();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toMatch(/report generated|报告已生成/i);
    await dialog.accept();
  });
  const generateReport = page.getByRole("button", { name: /Generate report|生成报告/ });
  await expect(generateReport).toHaveClass(/report-action/);
  await generateReport.click();
});

test("running evaluation opens live details", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("medical-evals-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.goto("/app/evaluations");

  const running = page.getByRole("row").filter({ hasText: "E2E running result fixture" }).first();
  await expect(running).toBeVisible();
  await running.getByRole("link", { name: /View results/ }).click();
  await expect(page.getByRole("heading", { name: /Run log|运行日志/ })).toBeVisible();
  await expect(page.getByText(/Queued|排队中|Preparing|准备中|Running|运行中/)).toBeVisible();
});
