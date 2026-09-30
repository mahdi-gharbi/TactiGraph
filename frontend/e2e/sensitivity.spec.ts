import { expect, test } from "@playwright/test";

test("remove a player changes only the fixed historical graph and can be restored", async ({
  page,
}) => {
  await page.goto("/");
  const network = page.locator(".network-panel").first();
  const nodes = network.locator(".network-node");
  await expect(nodes.first()).toBeVisible();
  const count = await nodes.count();
  await nodes.first().focus();
  await page.keyboard.press("Enter");
  await network
    .getByRole("button", {
      name: "Remove selected player from observed network",
    })
    .click();
  const result = network.getByRole("region", {
    name: "Network removal result",
  });
  await expect(result).toBeVisible();
  await expect(result).toContainText("does not predict replacement behaviour");
  await expect(result).toContainText("Reachable ordered pairs");
  await expect(nodes).toHaveCount(count - 1);
  await network
    .getByRole("button", { name: "Restore observed network" })
    .click();
  await expect(result).not.toBeVisible();
  await expect(nodes).toHaveCount(count);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
