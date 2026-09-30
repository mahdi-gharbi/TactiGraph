import { expect, test } from "@playwright/test";

test("analyst evaluation separates measured results from pending review", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Experiments", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Measured answers. Measured retrieval.",
    }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "The selected method does not meet every acceptance target.",
    ),
  ).toBeVisible();
  await expect(page.getByText("deterministic / held_out: 30/30")).toBeVisible();
  await expect(
    page.getByText("Independent human semantic review: pending."),
  ).toBeVisible();
});

test("analyst comparison resolves evidence and retrieves approved definitions", async ({
  page,
}) => {
  test.setTimeout(60000); // Includes one-time local encoder import/loading.
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Evidence Analyst", exact: true })
    .click();
  const panel = page.getByRole("region", {
    name: "Test the premise. Inspect the evidence.",
  });
  // Browser regression checks must never consume a configured remote API quota.
  await panel
    .getByRole("combobox", { name: "Claim selection provider" })
    .selectOption("deterministic");
  await panel
    .getByRole("button", { name: "Generate verified comparison" })
    .click();
  const report = panel.getByRole("article", {
    name: "Verified analyst report",
  });
  await expect(report).toContainText("human review pending");
  await expect(report).toContainText("0–15 versus 15–30");
  await expect(report).toContainText("do not establish a loss of control");
  await report
    .getByRole("button", { name: "Inspect before evidence" })
    .first()
    .click();
  await expect(
    panel.getByRole("complementary", { name: "Analyst evidence" }),
  ).toContainText("supporting events");
  await panel
    .getByRole("textbox", { name: "Methodology query" })
    .fill("field tilt");
  await panel.getByRole("button", { name: "Search definitions" }).click();
  // The optional local encoder is loaded on the first search.
  await expect(panel).toContainText("metric-field_tilt", { timeout: 30000 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await panel.getByRole("spinbutton", { name: "After start" }).fill("1");
  await panel
    .getByRole("button", { name: "Generate verified comparison" })
    .click();
  await expect(panel.getByRole("alert")).toContainText("cannot overlap");
});
