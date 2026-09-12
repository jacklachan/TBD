import { expect, test, type Page } from "@playwright/test";

async function ready(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Do nothing/ })).toBeEnabled();
  await page.evaluate(() => document.fonts.ready);
}

test("the numerical decision, moving clock, close-approach camera and both themes", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await ready(page);
  await expect(page.locator(".metric-card .metric")).toContainText("133.7");
  await expect(
    page.getByTestId("orbital-canvas").locator("canvas"),
  ).toBeVisible();
  await page.screenshot({
    path: "../Handoff/evidence/frontend-dark.png",
    fullPage: true,
  });
  const before = await page.getByTestId("simulation-clock").innerText();
  await page
    .getByRole("button", { name: "Play simulation", exact: true })
    .click();
  await expect(page.getByTestId("simulation-clock")).not.toHaveText(before);
  await page
    .getByRole("button", { name: "Pause simulation", exact: true })
    .click();
  await page.getByRole("button", { name: /The hidden conflict/ }).click();
  await expect(page.locator(".metric-card .metric")).toContainText("523.2");
  await page
    .getByRole("button", { name: "Focus closest approach", exact: true })
    .click();
  await expect(page.locator(".scene-caption")).toContainText(
    "Local encounter view",
  );
  await expect(page.locator(".live-reading .metric")).toContainText("523.2");
  await page.screenshot({
    path: "../Handoff/evidence/frontend-approach.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /The clear alternative/ }).click();
  await expect(page.locator(".metric-card .metric")).toContainText("2.492");
  await page.getByRole("button", { name: "Orbit", exact: true }).click();
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({
    path: "../Handoff/evidence/frontend-light.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /Maneuvers/ }).click();
  await expect(page.locator("tbody tr")).toHaveCount(25);
  await page
    .getByRole("button", { name: "Verified clear", exact: true })
    .click();
  expect(await page.locator("tbody tr").count()).toBeGreaterThan(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "Edit mission limits" }).click();
  await page.getByRole("spinbutton", { name: /Delta-v budget/ }).fill("0.10");
  await page.getByRole("button", { name: "Apply delta-v budget" }).click();
  await expect(page.getByText("Policy v2", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /The clear alternative/ }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Apply delta-v budget" }),
  ).toBeDisabled();
  await page.keyboard.press("Escape");
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export evidence", exact: true })
    .click();
  expect((await download).suggestedFilename()).toMatch(
    /satellite-demo-case_.*\.json/,
  );
  expect(errors).toEqual([]);
});

test("scenario switching and exact event samples", async ({ page }) => {
  await ready(page);
  await page
    .getByLabel("Scenario", { exact: true })
    .selectOption("no_encounter");
  await expect(page.getByRole("button", { name: /Do nothing/ })).toBeEnabled();
  await expect(page.locator(".metric-foot")).toContainText("Verified clear");
  await page
    .getByLabel("Scenario", { exact: true })
    .selectOption("no_feasible");
  await expect(page.getByRole("button", { name: /Do nothing/ })).toBeEnabled();
  await expect(
    page.getByRole("button", { name: /The clear alternative/ }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(
    page.getByText("No verified option", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No AI run yet.", { exact: false }),
  ).toBeVisible();
});

test("mobile layout, touch-sized controls, theme persistence and narrow chart", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await ready(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../Handoff/evidence/frontend-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("button", { name: /Do nothing/ })).toBeEnabled();
  await page.locator(".timeline-panel").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "../Handoff/evidence/frontend-mobile-chart.png",
  });
});

test("WebGL failure preserves chart and numerical workflow", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (type.includes("webgl")) return null;
      return original.call(this, type as never, ...(args as [])) as never;
    } as typeof original;
  });
  await ready(page);
  await expect(
    page.getByText("3D is unavailable on this device."),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Minimum separation/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: /The clear alternative/ }).click();
  await expect(page.locator(".metric-card .metric")).toContainText("2.492");
});
