import { expect, test } from "@playwright/test";

test("Premier League graph and style publications render their own results", async ({
  page,
  request,
}) => {
  const prefix = "/leagues/premier-league/api/v1";
  const graph = await (await request.get(`${prefix}/experiments/graph`)).json();
  const styles = await (
    await request.get(`${prefix}/experiments/styles`)
  ).json();
  expect(graph.report.version).toBe("graph-premier-league-v1");
  expect(styles.status).toBe("available");
  expect(styles.report.version).toBe("styles-premier-league-v1");
  await page.goto("/?league=premier-league");
  const stylePanel = page.getByRole("region", { name: "Passing styles" });
  await expect(stylePanel).toContainText(
    `${styles.report.training_windows} windows`,
  );
  await stylePanel
    .getByRole("button", { name: "Inspect source passes" })
    .first()
    .click();
  await expect(stylePanel.locator(".styles-event-id").first()).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Experiments", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Does the passing graph add predictive value?",
  });
  await expect(panel).toContainText(
    graph.report.results.lightgbm.log_loss.toFixed(4),
  );
  await expect(panel).toContainText(graph.report.lock.artifact_hash);
});

test("Premier League analyst posts to the selected dataset", async ({
  page,
  request,
}) => {
  const prefix = "/leagues/premier-league/api/v1";
  const matches = await (await request.get(`${prefix}/matches`)).json();
  await page.goto("/?league=premier-league");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Evidence Analyst", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Test the premise. Inspect the evidence.",
  });
  await panel
    .getByRole("combobox", { name: "Claim selection provider" })
    .selectOption("deterministic");
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().includes(`${prefix}/analyst/report`) &&
      r.request().method() === "POST",
  );
  await panel
    .getByRole("button", { name: "Generate verified comparison" })
    .click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const report = await response.json();
  expect(report.arguments.match_id).toBe(matches.matches[0].id);
  await expect(
    panel.getByRole("article", { name: "Verified analyst report" }),
  ).toBeVisible();
});

test("Premier League tactical requests use its xT model", async ({ page }) => {
  await page.goto("/?league=premier-league");
  const lab = page.locator(".tactical-lab");
  await expect(lab.locator(".tactical-metric")).toHaveCount(7);
  await lab
    .getByRole("button", { name: "Inspect curve xT", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Analytical evidence" }),
  ).toContainText("xt-premier-league-v1");
});

test("league selection isolates real data and preserves evidence", async ({
  page,
  request,
}) => {
  const prefix = "/leagues/premier-league/api/v1";
  const premier = await (await request.get(`${prefix}/matches`)).json();
  expect(premier.matches).toHaveLength(380);
  expect(
    premier.matches.every(
      (m: { competition: string }) => m.competition === "Premier League",
    ),
  ).toBe(true);
  const match = premier.matches[0];
  const summary = await (
    await request.get(`${prefix}/matches/${match.id}/summary`)
  ).json();
  expect(summary.model.model_version).toBe("xg-premier-league-v1");
  const shots = await (
    await request.get(`${prefix}/matches/${match.id}/shots`)
  ).json();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("combobox", { name: "League", exact: true })
    .selectOption("premier-league");
  await expect(page).toHaveURL(/league=premier-league/);
  await expect(page.getByTestId("filtered-shot-count")).toHaveText(
    `${shots.total_shots}recorded shots`,
  );
  await expect(
    page.getByText(`MATCH #${match.id}`, { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect evidence", exact: false })
    .click();
  await expect(page.getByRole("dialog").locator(".evidence-event")).toHaveCount(
    shots.total_shots,
  );
  await page.keyboard.press("Escape");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await expect(page.getByTestId("dataset-match-count")).toHaveText("380 / 380");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `../output/premier-league-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page
    .getByRole("combobox", { name: "League", exact: true })
    .selectOption("wsl");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await expect(page.getByTestId("dataset-match-count")).toHaveText("457 / 457");
  expect(errors).toEqual([]);
});
