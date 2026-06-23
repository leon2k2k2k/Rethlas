import { expect, test } from "@playwright/test";

// serve-fixture.sh sets RETHLAS_STUB_JOBS=1, so the stub type is enabled.

test.describe("jobs system", () => {
  test("launch page renders forms with problem picker", async ({ page }) => {
    await page.goto("/launch.html");
    await expect(page.locator(".tab", { hasText: "Attempt-based run" })).toBeVisible();
    await expect(page.locator("#f-problem_file")).toBeVisible();
    const options = await page.locator("#f-problem_file option").allTextContents();
    expect(options.join(" ")).toContain("data/alg/fix_verified.md");
    // switch to discovery form
    await page.click('.tab[data-type="discovery"]');
    await expect(page.locator("#f-dry_run")).toBeVisible();
  });

  test("stub job lifecycle on jobs page: appears, logs, stops", async ({ page, request }) => {
    const created = await (await request.post("/api/jobs", {
      data: { type: "stub", params: { seconds: 120 } },
    })).json();
    expect(created.status).toBe("running");

    await page.goto("/jobs.html");
    const card = page.locator("details[data-job='" + created.id + "']");
    await expect(card).toBeVisible();
    await expect(card.locator(".chip", { hasText: "running" })).toBeVisible();

    // log shows stub output
    await card.locator("summary").click();
    await card.locator("[data-log]").click();
    await expect(page.locator("#log-" + created.id)).toContainText("stub started");

    // stop it
    page.on("dialog", d => d.accept());
    await card.locator("[data-stop]").click();
    await expect(page.locator("details[data-job='" + created.id + "'] .chip",
      { hasText: /stopped|failed/ })).toBeVisible({ timeout: 15_000 });
  });

  test("completed stub job reports done", async ({ page, request }) => {
    const created = await (await request.post("/api/jobs", {
      data: { type: "stub", params: { seconds: 0 } },
    })).json();
    await expect.poll(async () => {
      const jobs = await (await request.get("/api/jobs")).json();
      return jobs.find(j => j.id === created.id).status;
    }, { timeout: 10_000 }).toBe("done");
    await page.goto("/jobs.html");
    await expect(page.locator("details[data-job='" + created.id + "'] .chip",
      { hasText: "done" })).toBeVisible();
  });

  test("invalid launch params rejected with message", async ({ request }) => {
    const resp = await request.post("/api/jobs", {
      data: { type: "retries", params: { problem_file: "../../etc/passwd" } },
    });
    expect(resp.status()).toBe(400);
  });
});
