import { expect, test } from "@playwright/test";

test("graph report reconciles with the exported experiment", async ({
  page,
  request,
}) => {
  const data = await (await request.get("/api/v1/experiments/graph")).json();
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Experiments", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Does the passing graph add predictive value?",
  });
  await expect(panel).toBeVisible();
  if (data.status === "not_trained") {
    await expect(panel).toContainText("Not evaluated");
  } else {
    await expect(panel).toContainText(
      data.report.test.n.toLocaleString("en-US"),
    );
    await expect(panel).toContainText(
      data.report.results.lightgbm.log_loss.toFixed(4),
    );
    await expect(panel).toContainText(data.report.lock.artifact_hash);
    await panel
      .getByText("Graph justification gates and paired differences", {
        exact: true,
      })
      .click();
    await expect(panel).toContainText(
      data.report.decision.justified
        ? "Graph contribution supported"
        : "Graph contribution not established",
    );
    await panel
      .getByText("Team-disjoint stress test and eligibility exclusions", {
        exact: true,
      })
      .click();
    await expect(panel).toContainText("Group 0:");
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("stored third-pass predictions resolve model and cutoff evidence", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Match Lab", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Will this episode produce a shot?",
  });
  await expect(panel).toBeVisible();
  await expect(panel).not.toContainText("Loading stored predictions");
  const predictions = panel.locator(".forecast-item");
  if (await predictions.count()) {
    await predictions.first().click();
    const evidence = panel.getByRole("complementary", {
      name: "Third-pass prediction evidence",
    });
    await expect(evidence).toContainText("Cutoff event");
    await expect(evidence).toContainText("Artifact SHA-256");
    await expect(evidence.getByRole("link")).toHaveAttribute(
      "href",
      /hudl\/open-data\/blob\/[a-f0-9]{40}\/data\/events\/[0-9]+\.json/,
    );
    await expect(panel).toContainText("in-sample");
  } else {
    await expect(panel).toContainText("No evaluated third-pass predictions");
  }
  await panel
    .getByRole("combobox", { name: "Prediction period" })
    .selectOption("2");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
