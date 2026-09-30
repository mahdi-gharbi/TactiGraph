import { expect, test } from "@playwright/test";

test("four-season audit and training-only exploration", async ({
  page,
  request,
}) => {
  const response = await (await request.get("/api/v1/dataset")).json();
  expect(response.status).toBe("audited");
  expect(response.report.coverage_complete).toBe(true);
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await expect(page.getByTestId("dataset-match-count")).toHaveText(
    `${response.report.ready_matches} / ${response.report.expected_matches}`,
  );
  await expect(
    page.getByText(
      `${response.report.training_eda.match_count} training matches only`,
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Team profiles", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("2023/24 · held out")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("season selection loads a new match and keeps evidence correct", async ({
  page,
  request,
}) => {
  const matches = await (await request.get("/api/v1/matches")).json();
  const match = matches.matches.find(
    (m: { season: string }) => m.season === "2023/2024",
  );
  expect(match).toBeTruthy();
  await page.goto("/");
  await page
    .getByRole("combobox", { name: "Season", exact: true })
    .selectOption("2023/2024");
  await expect(
    page.getByText(`MATCH #${match.id}`, { exact: true }),
  ).toBeVisible();
  const shots = await (
    await request.get(`/api/v1/matches/${match.id}/shots`)
  ).json();
  await expect(page.getByTestId("filtered-shot-count")).toHaveText(
    `${shots.total_shots}recorded shots`,
  );
  await page
    .getByRole("button", { name: "Inspect evidence", exact: false })
    .click();
  await expect(page.getByRole("dialog").locator(".evidence-event")).toHaveCount(
    shots.total_shots,
  );
});
