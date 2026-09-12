import { expect, test, type Page } from "@playwright/test";

/**
 * The two panels that take in someone else's data: a conjunction record from
 * another operator, and catalogue element sets pasted by hand.
 *
 * Both are checked here rather than only in Python because both exist to be
 * driven by a person. A round trip that works over HTTP but cannot be completed
 * by clicking is not a working feature.
 */

const SEED_TLE = [
  "NOAA 20 (JPSS-1)",
  "1 43013U 17073A   26254.91060846  .00000019  00000+0  30092-4 0  9999",
  "2 43013  98.7810 193.6155 0001610  53.1622 306.9701 14.19525379456774",
].join("\n");

const SECOND_OBJECT = [
  "OTHER OBJECT",
  "1 54234U 22150A   26254.88000000  .00000021  00000+0  32000-4 0  9995",
  "2 54234  98.7400 193.2000 0001200  60.0000 300.0000 14.19540000200000",
].join("\n");

async function ready(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Do nothing/ })).toBeEnabled();
}

test("a record is issued, handed across, recomputed, and caught when altered", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await ready(page);

  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  const issue = page.getByRole("button", { name: /Issue record/ });
  await expect(issue).toBeEnabled();
  await issue.click();

  // The record has to carry state vectors, or the receiver can read the claim
  // and not check it -- which is the one thing this format exists to prevent.
  const record = page.locator("pre.record");
  await expect(record).toContainText("CCSDS_CDM_VERS");
  await expect(record).toContainText("X_DOT");
  await expect(page.locator(".exchange-half").first()).toContainText(
    "no covariance, so no probability",
  );

  await page.getByRole("button", { name: /Hand it to the other operator/ }).click();
  const received = page.getByLabel(
    "Conjunction record received from another operator",
  );
  await expect(received).toHaveValue(/CCSDS_CDM_VERS/);

  await page.getByRole("button", { name: /Recompute it/ }).click();
  const result = page.locator(".exchange-result");
  await expect(result).toBeVisible();
  await expect(result).toHaveClass(/verdict-(agrees|no_claims)/);
  await expect(result).not.toHaveClass(/verdict-disagrees/);

  // Now overstate the clearance in the record and check it is rejected. The
  // number is read back out of the record rather than hardcoded, so this does
  // not break when the fixture changes.
  const text = await received.inputValue();
  const claimed = text.match(/MISS_DISTANCE = ([\d.]+)/);
  test.skip(
    claimed === null,
    "this case states no miss distance, so there is nothing to overstate",
  );
  await received.fill(
    text.replace(claimed![0], "MISS_DISTANCE = 9999.000"),
  );
  await page.getByRole("button", { name: /Recompute it/ }).click();
  await expect(page.locator(".exchange-result")).toHaveClass(
    /verdict-disagrees/,
  );
  await expect(page.locator(".exchange-result")).toContainText(
    "Its numbers do not hold",
  );
  await expect(page.locator("tr.row-disagrees")).toHaveCount(1);

  expect(errors).toEqual([]);
});

test("a record that cannot be read is refused with a reason, not a blank panel", async ({
  page,
}) => {
  await ready(page);
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await page
    .getByLabel("Conjunction record received from another operator")
    .fill("here are the orbits, thanks");
  await page.getByRole("button", { name: /Recompute it/ }).click();
  await expect(page.locator(".exchange-error")).toBeVisible();
  await expect(page.locator(".exchange-result")).toHaveCount(0);
});

test("pasted catalogue elements become a case the workspace can screen", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await ready(page);

  await page.getByRole("button", { name: /Use real elements/ }).click();
  const screen = page.getByRole("button", { name: /Screen these objects/ });
  await expect(screen).toBeDisabled();

  await page
    .getByLabel("Two-line element sets")
    .fill(`${SEED_TLE}\n${SECOND_OBJECT}`);
  await expect(page.locator(".elements-panel .caption").first()).toContainText(
    "2 objects recognised",
  );
  await expect(screen).toBeEnabled();

  await screen.click();

  // A pasted pair has only two objects, where every generated fixture has
  // three. The scene used to assume the third and crash.
  await expect(page.getByRole("button", { name: /Do nothing/ })).toBeEnabled();
  await expect(page.locator(".scenario-switch")).toContainText(
    "Pasted catalogue elements",
  );
  await expect(
    page.getByTestId("orbital-canvas").locator("canvas"),
  ).toBeVisible();
  // The tracked object must follow the case: DEB-1 does not exist here.
  await expect(page.locator("#debris")).toHaveValue(/NORAD-/);
  await expect(page.locator(".live-reading .metric")).not.toContainText("—");

  expect(errors).toEqual([]);
});

test("elements that cannot be read are refused before a case is created", async ({
  page,
}) => {
  await ready(page);
  await page.getByRole("button", { name: /Use real elements/ }).click();

  // One object is not a screening, and the form says so before the request.
  await page.getByLabel("Two-line element sets").fill(SEED_TLE);
  await expect(page.locator(".elements-panel .caption").first()).toContainText(
    "At least two are needed",
  );
  await expect(
    page.getByRole("button", { name: /Screen these objects/ }),
  ).toBeDisabled();
});
