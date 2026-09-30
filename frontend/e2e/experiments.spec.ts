import { expect, test } from "@playwright/test";

test("held-out metrics and model provenance reconcile", async ({
  page,
  request,
}) => {
  const response = await (await request.get("/api/v1/experiments")).json();
  expect(response.status).toBe("evaluated");
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Experiments", exact: true })
    .click();
  await expect(page.locator(".serving-row")).toContainText(
    response.report.metrics[response.report.serving].log_loss.toFixed(4),
  );
  await expect(page.locator(".serving-row")).toContainText(
    response.report.metrics[response.report.serving].brier.toFixed(4),
  );
  await expect(
    page.getByRole("img", {
      name: "Reliability diagram for Logistic regression",
    }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Calibration model" })
    .selectOption("lightgbm");
  await expect(
    page.getByRole("img", { name: "Reliability diagram for LightGBM" }),
  ).toBeVisible();
  await expect(
    page.getByText(response.model.artifact_hash, { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    await page
      .locator(".experiments-page > *")
      .evaluateAll((elements) =>
        elements.every(
          (element) => element.getBoundingClientRect().right <= innerWidth + 1,
        ),
      ),
  ).toBe(true);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Match Lab", exact: true })
    .click();
  await page.locator(".event-table-wrap .player-button").first().click();
  const citation = page.getByRole("region", { name: "Prediction provenance" });
  await expect(citation).toContainText(response.model.artifact_hash);
  await expect(citation).toContainText("xg-v1");
  await expect(citation).toContainText(
    "Training/tuning predictions are in-sample",
  );
});
