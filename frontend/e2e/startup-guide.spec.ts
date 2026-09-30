import { expect, test } from "@playwright/test";

test("unreachable API gives startup instructions and retry recovers", async ({
  page,
}) => {
  await page.route("**/api/v1/matches", (route) =>
    route.abort("connectionrefused"),
  );
  await page.goto("/");
  await expect(
    page.getByText(/Cannot reach the local TactiGraph server/),
  ).toBeVisible();
  await page.unroute("**/api/v1/matches");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByTestId("filtered-shot-count")).toBeVisible();
  await expect(
    page.getByText(/Cannot reach the local TactiGraph server/),
  ).toHaveCount(0);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await expect(page.getByText(/Dataset audit unavailable/)).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Learn from the training set." }),
  ).toBeVisible();
  await page.screenshot({
    path: `../output/restored-overview-${test.info().project.name}.png`,
  });
});

test("browser user guide loads all sections without any API dependency", async ({
  page,
}) => {
  await page.route("**/api/v1/**", (route) => route.abort());
  await page.goto("/guide");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Understand the app.",
  );
  await expect(page.locator("main section")).toHaveCount(12);
  await expect(
    page.getByRole("button", { name: "Print / Save as PDF" }),
  ).toBeVisible();
  await expect(page.locator("#start")).toContainText("Start-TactiGraph.cmd");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `../output/user-guide-${test.info().project.name}.png`,
  });
});
