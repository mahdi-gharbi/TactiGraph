import { expect, test } from "@playwright/test";

test("cached showcase respects review status and has navigable evidence", async ({
  page,
  request,
}) => {
  const data = await (await request.get("/api/v1/showcase")).json();
  const matches = await (await request.get("/api/v1/matches")).json();
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Evidence Analyst", exact: true })
    .click();
  const panel = page.getByRole("region", { name: "Cached showcase" });
  await expect(panel).toBeVisible();
  if (matches.mode === "public") {
    expect(data.status).toBe("review_pending");
    expect(data.reports).toHaveLength(0);
    await expect(panel).toContainText("Independent review pending");
    await expect(
      page.getByRole("combobox", { name: "Claim selection provider" }),
    ).toHaveCount(0);
    expect((await request.get("/api/v1/ready")).status()).toBe(503);
  } else {
    expect(data.reports).toHaveLength(36);
    const guided = [
      { name: "Progression", matchId: 19716, intent: "period_comparison" },
      { name: "Chance creation", matchId: 3764233, intent: "chance_creation" },
      {
        name: "Passing pattern",
        matchId: 2275026,
        intent: "network_concentration",
      },
    ];
    for (const item of guided) {
      await panel
        .getByRole("button", { name: new RegExp(item.name) })
        .first()
        .click();
      const report = data.reports.find(
        (candidate: (typeof data.reports)[number]) =>
          candidate.report.arguments.match_id === item.matchId &&
          candidate.report.arguments.intent === item.intent,
      );
      expect(report).toBeTruthy();
      await expect(panel).toContainText(report!.report.claims[0].text);
      await expect(panel).toContainText("03 / CHECK THE SOURCE");
      await expect(panel).toContainText("04 / THE LIMIT");
      if (item.name === "Progression") {
        await panel.screenshot({
          path: `../output/guided-showcase-${test.info().project.name}.png`,
        });
      }
    }
    await expect(
      panel
        .getByRole("combobox", { name: "Explore all prepared reports" })
        .locator("option"),
    ).toHaveCount(36);
    await panel
      .getByRole("combobox", { name: "Explore all prepared reports" })
      .selectOption("0");
    const entry = data.reports[0];
    await expect(panel).toContainText(entry.report.claims[0].text);
    await panel.getByText(/supporting measurements/).click();
    await expect(panel).toContainText(entry.report.claims[1].text);
    const inspect = panel
      .getByRole("button", { name: "Inspect before evidence", exact: true })
      .first();
    await inspect.focus();
    await page.keyboard.press("Enter");
    const evidence = panel.getByRole("complementary", {
      name: "Cached report evidence",
    });
    await expect(evidence.locator(".styles-event-id").first()).toBeVisible();
    await panel.getByRole("button", { name: "Close source evidence" }).click();
    await expect(evidence).toHaveCount(0);
    await panel
      .getByRole("combobox", { name: "Explore all prepared reports" })
      .selectOption("35");
    await expect(panel).toContainText(data.reports[35].report.claims[0].text);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  if (matches.mode !== "public") {
    expect(
      await panel
        .getByRole("combobox", { name: "Explore all prepared reports" })
        .evaluate(
          (element) => element.getBoundingClientRect().right <= innerWidth,
        ),
    ).toBe(true);
  }
  await panel.screenshot({
    path: `../output/showcase-${matches.mode}-${test.info().project.name}.png`,
  });
});
