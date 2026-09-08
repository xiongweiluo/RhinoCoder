import { expect, test } from "@playwright/test";

const scenarios = [
  {id: "normal-loop", title: "正常闭环", events: "10/10 events", assertions: "1/1"},
  {id: "self-correction", title: "错误恢复", events: "12/12 events", assertions: "1/2"},
  {id: "privacy-route", title: "隐私与路由", events: "9/9 events", assertions: "1/1"},
];

test("three public Replay scenarios expose the complete evidence chain without writes", async ({page}) => {
  const writes: string[] = [];
  const sockets: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/") && request.method() !== "GET") writes.push(`${request.method()} ${request.url()}`);
    if (request.resourceType() === "websocket") sockets.push(request.url());
  });

  for (const scenario of scenarios) {
    await page.goto(`/?demo=${scenario.id}&mode=replay`);
    await expect(page.getByRole("status").filter({hasText: "Read-only demo"})).toBeVisible();
    await expect(page.getByText(`${scenario.title} Replay 已完成`, {exact: false})).toBeVisible();
    await expect(page.getByText(scenario.events)).toBeVisible();
    await expect(page.getByRole("heading", {name: "Rhino 场景对比"})).toBeVisible();
    await expect(page.getByRole("heading", {name: "断言明细"})).toBeVisible();
    await expect(page.locator(".assertion-panel").getByText(scenario.assertions, {exact: true})).toBeVisible();
    await expect(page.getByRole("heading", {name: "脱敏审计摘要"})).toBeVisible();
    await expect(page.getByText("未暴露", {exact: true})).toBeVisible();
    await expect(page.getByRole("button", {name: "重试任务"})).toBeDisabled();
    await expect(page.getByRole("button", {name: "Undo"})).toBeDisabled();
    await expect(page.getByRole("button", {name: "精准回滚"})).toBeDisabled();
  }

  expect(writes).toEqual([]);
  expect(sockets).toEqual([]);
});

test("privacy route Replay is minimized, traceable, filterable, and searchable", async ({page}) => {
  await page.goto("/?demo=privacy-route&mode=replay");
  await expect(page.getByText("隐私与路由 Replay 已完成", {exact: false})).toBeVisible();
  await expect(page.getByText("minimize_cloud", {exact: true}).first()).toBeVisible();
  await expect(page.locator(".dashboard").getByText("replay-table", {exact: true})).toBeVisible();
  await expect(page.getByText("contact@example.invalid", {exact: false})).toHaveCount(0);
  await expect(page.locator(".timeline").getByText("<EMAIL_REDACTED>", {exact: false})).toBeVisible();

  await page.getByRole("button", {name: "验证", exact: true}).click();
  await expect(page.getByText("2/9 events", {exact: true})).toBeVisible();
  await expect(page.locator(".event-kind").filter({hasText: "场景读回"})).toBeVisible();
  await expect(page.locator(".event-kind").filter({hasText: "几何断言"})).toBeVisible();

  const search = page.getByPlaceholder("搜索指令或 run_id（快捷键 /）");
  await search.fill("replay-table");
  await expect(page.locator(".history").getByText("1/1", {exact: true})).toBeVisible();
  await page.getByRole("combobox").selectOption("replay");
  await expect(page.getByText("REPLAY", {exact: true})).toBeVisible();
});

test("public demo remains usable at a 390px viewport and has keyboard focus targets", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/?demo=self-correction&mode=replay");
  await expect(page.getByText("错误恢复 Replay 已完成", {exact: false})).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
  await page.keyboard.press("/");
  await expect(page.getByPlaceholder("搜索指令或 run_id（快捷键 /）")).toBeFocused();
  await expect(page.getByRole("link", {name: "跳到运行证据"})).toHaveAttribute("href", "#evidence-chain");
});
