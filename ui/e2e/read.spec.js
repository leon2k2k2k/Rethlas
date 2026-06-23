import { expect, test } from "@playwright/test";

const RUN = "/run.html?run=" + encodeURIComponent("alg/fix_verified");

test.describe("index page", () => {
  test("lists runs with status chips", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".run-card")).toHaveCount(6);
    await expect(page.locator(".status-chip-verified").first()).toBeVisible();
    await expect(page.locator("#summary")).toContainText("runs");
  });

  test("search narrows the grid", async ({ page }) => {
    await page.goto("/");
    await page.fill("#search", "fix_verified");
    await expect(page.locator(".run-card")).toHaveCount(1);
    await page.fill("#search", "zzz-nothing");
    await expect(page.locator(".run-card")).toHaveCount(0);
    await expect(page.locator(".notice")).toContainText("No runs match");
  });

  test("status filter works", async ({ page }) => {
    await page.goto("/");
    await page.selectOption("#f-status", "verified");
    await expect(page.locator(".run-card")).toHaveCount(1);
  });
});

test.describe("run page tabs", () => {
  test("problem tab renders markdown with typeset math", async ({ page }) => {
    await page.goto(RUN);
    await expect(page.locator("#side-status")).toHaveText("verified");
    await expect(page.locator(".markdown h1")).toContainText("Fixture problem");
    await expect(page.locator("mjx-container").first()).toBeVisible();
  });

  test("transcript pairs calls with outputs and renders reasoning", async ({ page }) => {
    await page.goto(RUN);
    await page.click('button.tab[data-tab="Transcript"]');
    await expect(page.locator(".ev.call")).toHaveCount(2);
    await expect(page.locator(".ev.output")).toHaveCount(0); // paired, not standalone
    await expect(page.locator(".ev.call .call-status").first()).toContainText("chars out");
    await expect(page.locator(".ev.reasoning")).toHaveCount(1);
    await expect(page.locator(".divider", { hasText: "compacted" })).toBeVisible();
  });

  test("blueprint tab prefers verified blueprint", async ({ page }) => {
    await page.goto(RUN);
    await page.click('button.tab[data-tab="Blueprint"]');
    await expect(page.locator("article.markdown")).toContainText("theorem");
    await expect(page.locator("mjx-container").first()).toBeVisible();
  });

  test("verification tab shows verdicts and referee with transcript link", async ({ page }) => {
    await page.goto(RUN);
    await page.click('button.tab[data-tab="Verification"]');
    await expect(page.locator(".ev-head", { hasText: "verdict: correct" })).toBeVisible();
    const referee = page.locator("details.ev.call");
    await expect(referee).toHaveCount(1);
    await referee.locator("summary").click();
    await expect(referee.locator("a.button")).toContainText("open referee transcript");
    await expect(referee.locator(".ev.assistant")).toContainText("holds", { timeout: 10_000 });
  });

  test("memory tab renders channels with math", async ({ page }) => {
    await page.goto(RUN);
    await page.click('button.tab[data-tab="Memory"]');
    await expect(page.locator("details.ev summary", { hasText: "branch_states" })).toBeVisible();
    await expect(page.locator(".mem-rec")).toHaveCount(1);
  });

  test("logs tab parses console output with raw toggle", async ({ page }) => {
    await page.goto(RUN);
    await page.click('button.tab[data-tab="Logs"]');
    await expect(page.locator(".ev.assistant")).toContainText("Done, see blueprint");
    await page.check("#log-raw");
    await expect(page.locator("pre.log")).toContainText("session id");
  });

  test("files tab lists results", async ({ page }) => {
    await page.goto(RUN);
    await page.click('button.tab[data-tab="Files"]');
    await expect(page.locator(".file-card", { hasText: "blueprint_verified.md" })).toBeVisible();
  });
});

test.describe("routes and lineage", () => {
  test("routes tab appears for batch runs and renders cards", async ({ page }) => {
    await page.goto("/run.html?run=" + encodeURIComponent("geo/fix_batch"));
    await page.click('button.tab[data-tab="Routes"]');
    await expect(page.locator("details.ev summary", { hasText: "number_field_source_identified" }))
      .toBeVisible();
    await expect(page.locator(".ev-body")).toContainText("fixture family");
  });

  test("routes tab absent for plain runs", async ({ page }) => {
    await page.goto(RUN);
    await expect(page.locator('button.tab[data-tab="Routes"]')).toHaveCount(0);
  });
});

test.describe("session viewer", () => {
  test("bare session id renders transcript", async ({ page }) => {
    await page.goto("/run.html?session=01900000-0000-7000-8000-00000000000a");
    await expect(page.locator(".ev.assistant")).toContainText("Proof");
    await expect(page.locator("#side-status")).toHaveText("session");
  });
});
