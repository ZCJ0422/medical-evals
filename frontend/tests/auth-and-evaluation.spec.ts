import { test, expect } from "@playwright/test";

import { signIn, createEvaluation } from "./helpers";

test("administrator can sign in", async ({ page }) => {
  await signIn(page);
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
  const payloads: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/evaluations", async (route) => {
    if (route.request().method() === "POST") payloads.push(route.request().postDataJSON());
    await route.continue();
  });
  await signIn(page);
  await createEvaluation(page, "Browser smoke evaluation");
  await expect(page.getByRole("row").filter({ hasText: "Browser smoke evaluation" })).toBeVisible();
  expect(payloads).toHaveLength(1);
  expect(payloads[0]).toMatchObject({ evaluation_definition_id: "medqa", split: "dev", sample_limit: 1 });
});

test("created evaluation appears with its queued status", async ({ page }) => {
  await signIn(page);
  await createEvaluation(page, "Visible queued evaluation");
  const row = page.getByRole("row").filter({ hasText: "Visible queued evaluation" });
  await expect(row).toBeVisible();
  await expect(row.locator(".status")).toHaveAttribute("aria-label", "Queued");
  await expect(row.getByText("admin", { exact: true })).toBeVisible();
});
