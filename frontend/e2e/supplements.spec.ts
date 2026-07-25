import { test, expect } from "./fixtures";
import { completeOnboarding } from "./helpers";

/**
 * #161 Lane 3b: supplement library logging + explicit section absence,
 * end to end — inline-create a library product (POST /api/supplement-products),
 * log it at the default dose, mark caffeine "none today", save, and verify
 * both survive a reload (the round-trip contract in the wild).
 */
test.describe("Supplements + none today", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await completeOnboarding(page);
  });

  test("log a supplement from the library + mark none today; both persist", async ({
    page,
  }) => {
    // Expand the collapsed Supplements section and create a library product
    await page.getByRole("button", { name: /Supplements/ }).click();
    await page.getByRole("button", { name: "+ Add a supplement" }).click();
    await page.getByRole("button", { name: "+ New product" }).click();
    await page.getByLabel("New product name").fill("Melatonin");
    await page.getByLabel("New product default dose").fill("3");
    await page.getByRole("button", { name: "Add to library" }).click();

    // The new product lands as a row prefilled at the default dose
    const dose = page.getByRole("spinbutton", { name: "Melatonin dose (mg)" });
    await expect(dose).toHaveValue("3");

    // Dose IS the state: 0 shows the rust "none today" row state...
    await dose.fill("0");
    await expect(page.locator(".supp-row-none-text")).toBeVisible();
    // ...and a real dose clears it again
    await dose.fill("2.5");
    await expect(page.locator(".supp-row-none-text")).not.toBeVisible();

    // Explicit section absence: no caffeine today (section open by default)
    await page
      .getByRole("button", { name: "Mark caffeine none today" })
      .click();
    await expect(
      page.getByRole("button", { name: "Undo — restore caffeine today" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Saved ✓")).toBeVisible();

    // Reload — localStorage is cleared by the fixture, so re-expand
    await page.reload();
    await page.getByRole("button", { name: /Supplements/ }).click();
    await expect(
      page.getByRole("spinbutton", { name: "Melatonin dose (mg)" }),
    ).toHaveValue("2.5");
    await expect(
      page.getByRole("button", { name: "Undo — restore caffeine today" }),
    ).toBeVisible();
  });
});
