import { expect, test } from "@playwright/test";

test.describe("editor", () => {
  test("edit problem file roundtrip with math preview", async ({ page }) => {
    await page.goto("/editor.html");
    await page.click('[data-open="data/alg/fix_verified.md"]');
    await expect(page.locator("#current-file")).toContainText("fix_verified.md");

    // live preview renders markdown + math
    await page.check("#preview-toggle");
    await expect(page.locator("#preview h1")).toContainText("Fixture problem");
    await expect(page.locator("#preview mjx-container").first()).toBeVisible();

    // edit and save
    await page.fill("#edit-area",
      (await page.inputValue("#edit-area")) + "\n\nAppended by e2e \\(y^2\\).\n");
    await page.click("#save-btn");
    await expect(page.locator("#status-line")).toContainText("saved");

    // reload shows the change
    await page.reload();
    await page.click('[data-open="data/alg/fix_verified.md"]');
    await expect(page.locator("#edit-area")).toHaveValue(/Appended by e2e/);
  });

  test("new problem from template", async ({ page }) => {
    await page.goto("/editor.html");
    await page.fill("#new-name", "data/e2e/created.md");
    await page.click("#new-btn");
    await expect(page.locator("#edit-area")).toHaveValue(/Target Statement/);
    await page.click("#save-btn");
    await expect(page.locator("#status-line")).toContainText("saved");
    await expect(page.locator('[data-open="data/e2e/created.md"]')).toBeVisible();
  });

  test("config editing shows warning banner", async ({ page }) => {
    await page.goto("/editor.html");
    const config = page.locator("#config-list [data-open]").first();
    await config.click();
    await expect(page.locator("#config-warning")).toBeVisible();
  });
});
