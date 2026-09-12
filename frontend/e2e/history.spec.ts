import { expect, test, type APIRequestContext } from "@playwright/test";

// Scripted model, real case storage/search/verifier. No external model call is made.
const fixture = "http://127.0.0.1:8001";

async function finishedCase(request: APIRequestContext) {
  const created = await request.post(`${fixture}/cases`, {
    data: { scenario_id: "primary" },
  });
  expect(created.ok()).toBeTruthy();
  const snapshot = await created.json();
  const run = await request.post(`${fixture}/cases/${snapshot.case_id}/plan`, {
    data: { expected_scenario_version: 1, expected_policy_version: 1 },
  });
  expect(run.ok()).toBeTruthy();
  const { run_id } = await run.json();
  await expect
    .poll(
      async () =>
        (await (await request.get(`${fixture}/runs/${run_id}`)).json()).status,
    )
    .toBe("DONE");
  return snapshot.case_id as string;
}

test.beforeEach(async ({ page }) => {
  test.skip(
    !process.env.TEST_SCRIPTED_AGENT,
    "Requires the scripted server on 8001.",
  );
  await page.route(/\/(cases|runs|health|context)(\/|\?|$)/, async (route) => {
    const target = new URL(route.request().url());
    target.port = "8001";
    await route.continue({ url: target.toString() });
  });
});

test("earlier case evidence is inspectable without changing the active workspace", async ({
  page,
  request,
}) => {
  const priorId = await finishedCase(request);
  await page.goto("/");
  const planner = page.getByRole("button", {
    name: "Run AI planner",
    exact: true,
  });
  await expect(planner).toBeEnabled();
  const activeId = await page.locator("main").getAttribute("data-case-id");
  await planner.click();
  await expect(
    page.getByRole("button", { name: /^Evidence.*earlier case/ }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Re-run AI planner", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: /^Evidence/ }).click();
  await page
    .getByRole("button", {
      name: `Inspect earlier case ${priorId}`,
      exact: true,
    })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Earlier case evidence");
  await expect(dialog).toContainText(priorId);
  await expect(dialog).toContainText("t30_ret_200");
  await expect(dialog).toContainText("ALLOW");
  await expect(dialog).toContainText("2.492 km");
  await expect(dialog).toContainText("No simulated execution recorded");
  await expect(page.locator("main")).toHaveAttribute("data-case-id", activeId!);
  await expect(
    dialog.getByRole("button", { name: /Approve|Apply/ }),
  ).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Export this evidence" })).toHaveCount(0);
  await page.screenshot({
    path: "../Handoff/evidence/prior-case-evidence.png",
    fullPage: true,
  });
  await dialog
    .getByRole("button", { name: "Back to current evidence" })
    .click();
  await expect(dialog).toContainText("Evidence, with a paper trail.");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(page.locator("main")).toHaveAttribute("data-case-id", activeId!);
});

test("an expired earlier case shows a recoverable error and preserves current evidence", async ({
  page,
  request,
}) => {
  const priorId = await finishedCase(request);
  await page.goto("/");
  const planner = page.getByRole("button", {
    name: "Run AI planner",
    exact: true,
  });
  await expect(planner).toBeEnabled();
  const activeId = await page.locator("main").getAttribute("data-case-id");
  await planner.click();
  await expect(
    page.getByRole("button", { name: /^Evidence.*earlier case/ }),
  ).toBeVisible();
  await page.route(`**/cases/${priorId}`, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "case expired" }),
    }),
  );
  await page.getByRole("button", { name: /^Evidence/ }).click();
  await page
    .getByRole("button", {
      name: `Inspect earlier case ${priorId}`,
      exact: true,
    })
    .click();
  await expect(page.getByRole("alert")).toContainText("no longer available");
  await page.getByRole("button", { name: "Back to current evidence" }).click();
  await expect(page.getByRole("dialog")).toContainText(activeId!);
  await page.keyboard.press("Escape");
  await expect(page.locator("main")).toHaveAttribute("data-case-id", activeId!);
});
