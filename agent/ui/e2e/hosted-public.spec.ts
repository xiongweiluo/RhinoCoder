import { expect, test } from "@playwright/test";

test("hosted root opens a useful Replay without setup", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "RhinoCoder"})).toBeVisible();
  await expect(page.locator(".dashboard").getByText("replay-basic", {exact: true})).toBeVisible();
  await expect(page.getByRole("link", {name: "GitHub ↗"})).toHaveAttribute("href", "https://github.com/xiongweiluo/RhinoCoder");
  await expect(page.getByRole("tab")).toHaveCount(3);
  await expect(page.getByRole("tab", {name: /正常闭环 VERIFIED/})).toBeVisible();
  await expect(page.locator(".replay-origin")).toContainText("Synthetic Replay");
  await expect(page.getByRole("heading", {name: "先看结果，再钻进 Trace"})).toHaveCount(0);
});
