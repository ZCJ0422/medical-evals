import { test, expect } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("medical-evals-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("administrator can sign in", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("medical-evals-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: "Evaluation control room" })).toBeVisible();
});

test("sidebar controls match navigation styling and remain readable on hover", async ({ page }) => {
  await signIn(page);
  const languageButton = page.locator(".locale-toggle");
  const logoutButton = page.locator(".logout");
  await expect(languageButton).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(logoutButton).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(languageButton).toHaveCSS("border-radius", "13px");
  await expect(logoutButton).toHaveCSS("border-radius", "13px");
  await languageButton.hover();
  await expect(languageButton).toHaveCSS("background-color", "rgba(255, 255, 255, 0.09)");
  await expect(languageButton).toHaveCSS("color", "rgb(255, 255, 255)");
  await logoutButton.hover();
  await expect(logoutButton).toHaveCSS("background-color", "rgba(255, 255, 255, 0.09)");
  await expect(logoutButton).toHaveCSS("color", "rgb(255, 255, 255)");
});

test("administrator can create an evaluation", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("medical-evals-admin");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "New evaluation" }).click();
  await page.getByRole("combobox", { name: /Dataset version/ }).selectOption("medical-medqa.dev.v1");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel(/Target model/).fill("target-model");
  await page.getByLabel(/Target Base URL/).fill("https://target.example/v1");
  await page.getByLabel(/Target API Key/).fill("test-key");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel(/Run name/).fill("Browser smoke evaluation");
  await page.getByLabel(/Max samples/).fill("1");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Create evaluation", exact: true }).click();
  await expect(page.getByText(/^Evaluation queued:/)).toBeVisible();
});

test("created evaluation appears with its queued status", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "New evaluation" }).click();
  await page.getByRole("combobox", { name: /Dataset version/ }).selectOption("medical-medqa.dev.v1");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel(/Target model/).fill("target-model");
  await page.getByLabel(/Target Base URL/).fill("https://target.example/v1");
  await page.getByLabel(/Target API Key/).fill("test-key");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel(/Run name/).fill("Visible queued evaluation");
  await page.getByLabel(/Max samples/).fill("1");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Create evaluation", exact: true }).click();
  await page.waitForURL(/\/app\/evaluations$/);
  const row = page.getByRole("row").filter({ hasText: "Visible queued evaluation" }).first();
  await expect(row).toBeVisible();
  await expect(row.locator(".status")).toHaveText("");
  await expect(row.locator(".status")).toHaveAttribute("aria-label", /Queued|Running|Completed|Partial failed|Failed|Cancelled|排队中|运行中|完成|部分失败|失败|已取消/);
  expect(await row.locator(".text-button").evaluateAll((buttons) => buttons.every((button) => button.textContent?.trim() === ""))).toBe(true);
});
