import { test, expect } from "@playwright/test";

test("renders the Medical Evals shell", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Medical Evals/i);
  await expect(page.getByRole("heading", { name: "Medical Evals" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
});
