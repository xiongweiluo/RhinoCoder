import { expect, test } from "@playwright/test";

test("hosted root opens a useful Replay without setup", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "RhinoCoder"})).toBeVisible();
  await expect(page.getByText("正常闭环 Replay 已完成", {exact: false})).toBeVisible();
  await expect(page.locator(".dashboard").getByText("replay-basic", {exact: true})).toBeVisible();
  await expect(page.getByRole("link", {name: "GitHub ↗"})).toHaveAttribute("href", "https://github.com/xiongweiluo/RhinoCoder");
});
