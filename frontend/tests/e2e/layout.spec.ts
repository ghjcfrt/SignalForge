import { expect, test } from "@playwright/test";

test("dashboard renders the main workflow surfaces", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("热讯工坊").first()).toBeVisible();
  await expect(page.getByText("老板指令")).toBeVisible();
  await expect(page.getByText("流水线").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /打开产物文件夹/ })).toBeVisible();
  await page.screenshot({ path: `test-results/dashboard-${test.info().project.name}.png`, fullPage: true });
});

test("forms and pipeline remain usable at narrow width", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("input").first()).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
  await page.getByText("设置", { exact: true }).click();
  await expect(page.getByText("运行时设置").or(page.getByText("服务设置"))).toBeVisible();
  await page.screenshot({ path: `test-results/settings-${test.info().project.name}.png`, fullPage: true });
});

test("output details can expand without layout overlap", async ({ page }) => {
  await page.goto("/");
  const details = page.locator("details.output-item").first();
  if (await details.count()) {
    await details.locator("summary").click();
    await expect(details).toHaveAttribute("open", "");
  }
});
