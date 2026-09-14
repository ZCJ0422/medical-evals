import { expect, type Page } from "@playwright/test";

export async function signIn(page: Page) {
  await page.goto("/admin/login");
  await page.getByLabel("Administrator username").fill("admin");
  await page.getByLabel("Password").fill("medical-evals-admin");
  await page.getByRole("button", { name: "Enter admin console" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

export async function createEvaluation(page: Page, name: string) {
  await page.goto("/app/evaluations/new");
  await page.getByRole("combobox", { name: "Dataset", exact: true }).selectOption("medqa");
  await page.getByRole("combobox", { name: "Split", exact: true }).selectOption("dev");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("combobox", { name: "Target model", exact: true }).selectOption({ label: "E2E target · fixture-model" });
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel(/Run name/).fill(name);
  await page.getByLabel(/Sample limit/).fill("1");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Create evaluation", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/evaluations$/);
}
