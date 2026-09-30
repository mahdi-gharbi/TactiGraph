import { expect, test } from "@playwright/test";

test("period comparison, network selection and exact evidence", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const lab = page.locator(".tactical-lab");
  await expect(
    lab.getByRole("heading", { name: "Periods & passing networks" }),
  ).toBeVisible();
  await expect(lab.locator(".tactical-metric")).toHaveCount(7);
  await expect(lab.locator(".network-pitch")).toHaveCount(2);
  await expect(
    lab.getByRole("img", { name: "xG trailing five-minute curve" }),
  ).toBeVisible();
  await expect(
    lab.getByRole("img", { name: "Signed xT trailing five-minute curve" }),
  ).toBeVisible();
  await lab
    .getByRole("button", { name: "Inspect curve xT", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Analytical evidence" }),
  ).toContainText("xt-v1");
  await page.keyboard.press("Escape");
  await expect(lab.locator(".comparison-verdict")).toContainText("45–60 min");
  await expect(lab.locator(".comparison-verdict")).toContainText("60–75 min");
  const matches = await (await request.get("/api/v1/matches")).json();
  const match = matches.matches[0];
  const report = await (
    await request.post(`/api/v1/matches/${match.id}/compare`, {
      data: {
        team_id: match.home.id,
        before: { period: 2, start_ms: 0, end_ms: 900000 },
        after: { period: 2, start_ms: 900000, end_ms: 1800000 },
      },
    })
  ).json();
  const before = report.before.measurements.find(
    (m: { metric: string }) => m.metric === "final_third_entries",
  );
  await lab
    .getByRole("button", {
      name: "Before Final-third entries / min evidence",
      exact: true,
    })
    .click();
  const dialog = page.getByRole("dialog", { name: "Analytical evidence" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(before.evidence_id);
  await expect(dialog.locator(".tactical-references li")).toHaveCount(
    Math.min(before.numerator, 50),
  );
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  const first = lab.locator(".network-node").first();
  await first.focus();
  await page.keyboard.press("Enter");
  await expect(lab.locator(".player-statistics")).toHaveCount(1);
  await lab
    .getByRole("spinbutton", { name: "After start", exact: true })
    .fill("10");
  await lab
    .getByRole("button", { name: "Compare periods", exact: true })
    .click();
  await expect(lab.getByRole("alert")).toBeVisible();
  await lab
    .getByRole("spinbutton", { name: "After start", exact: true })
    .fill("15");
  await lab
    .getByRole("button", { name: "Compare periods", exact: true })
    .click();
  await expect(lab.locator(".tactical-metric")).toHaveCount(7);
  expect(
    await lab.evaluate(
      (el) => el.getBoundingClientRect().right <= innerWidth + 1,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("evaluated xT surface and held-out scores are inspectable", async ({
  page,
  request,
}) => {
  const response = await (await request.get("/api/v1/experiments/xt")).json();
  expect(response.status).toBe("evaluated");
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Experiments", exact: true })
    .click();
  const panel = page.locator(".xt-experiment");
  await expect(
    panel.getByRole("heading", {
      name: "Movement, with the cost of losing the ball.",
    }),
  ).toBeVisible();
  await expect(panel).toContainText(
    response.report.results.xt.brier.toFixed(6),
  );
  await expect(panel).toContainText(response.report.lock.artifact_hash);
  const zones = panel.getByRole("button", { name: /Zone / });
  await expect(zones).toHaveCount(96);
  await zones.last().focus();
  await page.keyboard.press("Enter");
  await expect(panel).toContainText("Zone 96:");
  expect(
    await panel.evaluate(
      (el) => el.getBoundingClientRect().right <= innerWidth + 1,
    ),
  ).toBe(true);
});
