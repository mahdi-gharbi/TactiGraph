import { expect, test } from "@playwright/test";

test("styles reconcile with stored results and source passes on desktop and mobile", async ({
  page,
  request,
}) => {
  const report = await (await request.get("/api/v1/experiments/styles")).json();
  expect(report.status).toBe("available");
  await page.goto("/");
  const section = page.getByRole("region", { name: "Passing styles" });
  await expect(section).toContainText(
    `${report.report.training_windows} windows`,
  );
  const inspect = section
    .getByRole("button", { name: "Inspect source passes" })
    .first();
  await inspect.focus();
  await page.keyboard.press("Enter");
  await expect(
    section.getByRole("heading", { name: "Source evidence" }),
  ).toBeVisible();
  await expect(section.locator(".styles-event-id").first()).toBeVisible();
  const first = await section.locator(".styles-event-id").first().textContent();
  await section.getByRole("button", { name: "Next passes" }).click();
  await expect(section.locator(".styles-event-id").first()).not.toHaveText(
    first!,
  );
  await section.getByRole("button", { name: "Close evidence" }).click();
  await expect(
    section.getByRole("heading", { name: "Source evidence" }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Experiments", exact: true })
    .click();
  await expect(section).toContainText(
    report.report.training_silhouette.toFixed(3),
  );
  expect(await section.locator(".styles-grid article").count()).toBe(4);
  await section.screenshot({
    path: `../output/styles-${test.info().project.name}.png`,
  });
});
