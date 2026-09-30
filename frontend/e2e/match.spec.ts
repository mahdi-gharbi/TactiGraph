import { expect, test } from "@playwright/test";

test("real match filters reconcile and citations open", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const matches = await (await request.get("/api/v1/matches")).json();
  expect(matches.matches.length).toBeGreaterThan(0);
  const match = matches.matches[0];
  const shots = await (
    await request.get(`/api/v1/matches/${match.id}/shots`)
  ).json();
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Inside the match." }),
  ).toBeVisible();
  await expect(page.getByTestId("filtered-shot-count")).toHaveText(
    `${shots.total_shots}recorded shots`,
  );
  const summary = await (
    await request.get(`/api/v1/matches/${match.id}/summary`)
  ).json();
  await expect(page.getByTestId("match-xg")).toHaveText(
    `${summary.teams[0].xg.toFixed(2)} — ${summary.teams[1].xg.toFixed(2)}`,
  );
  await page
    .getByRole("button", { name: "Inspect evidence", exact: false })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".evidence-event")).toHaveCount(
    shots.total_shots,
  );
  await expect(
    dialog.getByText(matches.provenance.source_commit, { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await page
    .getByRole("combobox", { name: "Team", exact: true })
    .selectOption(String(match.home.id));
  await page
    .getByRole("combobox", { name: "Period", exact: true })
    .selectOption("2");
  const filtered = await (
    await request.get(
      `/api/v1/matches/${match.id}/shots?team_id=${match.home.id}&period=2`,
    )
  ).json();
  await expect(page.getByTestId("filtered-shot-count")).toHaveText(
    `${filtered.total_shots}recorded shots`,
  );
  await expect(page.locator("tbody tr")).toHaveCount(filtered.total_shots);
  await page.getByRole("spinbutton", { name: "Start minute" }).fill("119");
  await page.getByRole("spinbutton", { name: "End minute" }).fill("120");
  await expect(page.getByText("No shots in this selection.")).toBeVisible();
  await expect(page.getByTestId("filtered-shot-count")).toHaveText(
    "0recorded shots",
  );
  expect(errors).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("shot markers are keyboard accessible and experiments are honest", async ({
  page,
}) => {
  await page.goto("/");
  const marker = page.locator(".shot-marker").first();
  await expect(marker).toBeVisible();
  await marker.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.locator(".evidence-event.highlight")).toHaveCount(1);
  await page.getByRole("button", { name: "Close evidence" }).click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Experiments" })
    .click();
  await expect(
    page.getByRole("heading", { name: /Probabilities,\s*put to the test\./ }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "The selected method does not meet every acceptance target.",
      {
        exact: false,
      },
    ),
  ).toBeVisible();
});
