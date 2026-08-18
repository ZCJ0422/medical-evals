import { test, expect } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("medical-evals-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("new evaluation lists MedQA and HealthBench and switches language", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "New evaluation" }).click();
  const options = page.locator('select[name="dataset_version_id"] option');
  await expect(options).toHaveCount(6);
  await expect(options.nth(1)).toContainText("MedQA");
  await expect(options.nth(2)).toContainText("HealthBench");
  await page.getByRole("button", { name: "中文" }).click();
  await expect(page.getByRole("heading", { name: "创建测评" })).toBeVisible();
  await expect(page.getByLabel("数据集版本 必填")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Configure a run" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});
