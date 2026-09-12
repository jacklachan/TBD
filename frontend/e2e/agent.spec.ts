import { expect, test } from "@playwright/test";

test("scripted provider: plan, reviewed proposal, approval, reset, sentence and confirm", async ({
  page,
}) => {
  test.skip(
    !process.env.TEST_SCRIPTED_AGENT,
    "Requires the explicitly scripted local fixture on port 8001.",
  );
  await page.route(/\/(cases|runs|health|context)(\/|\?|$)/, async (route) => {
    const target = new URL(route.request().url());
    target.port = "8001";
    await route.continue({ url: target.toString() });
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Run AI planner", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Run AI planner", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Approve simulated maneuver" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve simulated maneuver" }),
  ).toBeDisabled({ timeout: 1000 });
  await page
    .getByRole("button", { name: "Inspect proposed trajectory" })
    .click();
  await expect(
    page.getByRole("button", { name: "Approve simulated maneuver" }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Approve simulated maneuver" })
    .click();
  await expect(
    page.getByText("Recorded in simulation", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reset case", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Run AI planner", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("textbox", { name: "New restriction in plain English" })
    .fill("We lost a thruster. Halve the fuel budget.");
  await page.getByRole("button", { name: "Preview restriction" }).click();
  await expect(page.getByRole("dialog")).toContainText("Delta-v budget");
  await page.getByRole("button", { name: "Confirm & recompute" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Edit mission limits" }),
  ).toContainText("0.10 m/s");
  await expect(
    page.getByRole("button", { name: /The clear alternative/ }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(page.locator(".event-list")).toContainText("propose_policy");
});
