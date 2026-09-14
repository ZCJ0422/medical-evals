import { test, expect } from "@playwright/test";

import { signIn } from "./helpers";

test("new evaluation lists MedQA and HealthBench and switches language", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "New evaluation" }).click();
  const dataset = page.getByRole("combobox", { name: "Dataset", exact: true });
  await expect(dataset.locator("option")).toHaveCount(3);
  await expect(dataset.locator("option").nth(1)).toHaveText("MedQA");
  await expect(dataset.locator("option").nth(2)).toHaveText("HealthBench");
  await dataset.selectOption("healthbench");
  await expect(page.getByRole("combobox", { name: "Split", exact: true }).locator("option")).toHaveCount(5);
  await page.getByRole("button", { name: "中文" }).click();
  await expect(page.getByRole("heading", { name: "创建测评" })).toBeVisible();

  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Configure a run" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});
