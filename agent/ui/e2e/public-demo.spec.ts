import { expect, test } from "@playwright/test";

const scenarios = [
  {id: "normal-loop", title: "正常闭环", events: "6/14 events", assertions: "5 / 5"},
  {id: "self-correction", title: "错误恢复", events: "10/14 events", assertions: "2 / 2"},
  {id: "privacy-route", title: "隐私与路由", events: "6/11 events", assertions: "3 / 3"},
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
    await expect(page.locator(".replay-origin")).toContainText("Synthetic Replay");
    await expect(page.getByRole("button", {name: "关键", exact: true})).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(scenario.events)).toBeVisible();
    await expect(page.getByRole("heading", {name: "Rhino 空间结果"})).toBeVisible();
    await expect(page.getByRole("heading", {name: "为什么通过"})).toBeVisible();
    await expect(page.locator(".proof-verdict").getByText(scenario.assertions, {exact: true})).toBeVisible();
    await expect(page.getByRole("heading", {name: "脱敏审计摘要"})).toBeVisible();
    await expect(page.getByText("未暴露", {exact: true})).toBeVisible();
    await expect(page.locator(".controls")).toHaveCount(0);
    await expect(page.getByRole("heading", {name: "Recent Runs"})).toHaveCount(0);
  }

  expect(writes).toEqual([]);
  expect(sockets).toEqual([]);
});

test("privacy route Replay is minimized, traceable, and filterable", async ({page}) => {
  await page.goto("/?demo=privacy-route&mode=replay");
  await expect(page.locator(".dashboard").getByText("replay-table", {exact: true})).toBeVisible();
  await expect(page.getByText("minimize_cloud", {exact: true}).first()).toBeVisible();
  await expect(page.locator(".dashboard").getByText("replay-table", {exact: true})).toBeVisible();
  await expect(page.getByText("contact@example.invalid", {exact: false})).toHaveCount(0);
  await expect(page.locator(".timeline").getByText("<EMAIL_REDACTED>", {exact: false})).toBeVisible();
  await expect(page.locator(".privacy-causality")).toContainText("敏感字段在出站模型请求前完成最小化。");
  await expect(page.locator(".scene-object-index").getByText("Legs ×4", {exact: true})).toBeVisible();
  await expect(page.locator(".scene-inspector").getByText("Legs × 4", {exact: true})).toBeVisible();
  await expect(page.locator(".scene-inspector").getByText("View individual objects", {exact: true})).toBeVisible();

  await page.getByRole("button", {name: "验证", exact: true}).click();
  await expect(page.getByText("4/11 events", {exact: true})).toBeVisible();
  await expect(page.locator(".event-kind").filter({hasText: "场景读回"})).toBeVisible();
  await expect(page.locator(".event-kind").filter({hasText: "几何断言"}).first()).toBeVisible();

});

test("normal loop exposes detailed proof and defaults to true object color", async ({page}) => {
  await page.goto("/?demo=normal-loop&mode=replay");
  await expect(page.locator(".proof-verdict").getByText("5 / 5", {exact: true})).toBeVisible();
  await expect(page.getByText("scene_object_count", {exact: true})).toBeVisible();
  await expect(page.getByText("base_dimensions", {exact: true})).toBeVisible();
  await expect(page.getByText("sphere_radius", {exact: true})).toBeVisible();
  await expect(page.locator(".assertion-panel").getByText("Expected", {exact: true}).first()).toBeVisible();
  await expect(page.locator(".assertion-panel").getByText("Actual", {exact: true}).first()).toBeVisible();
  await expect(page.getByRole("button", {name: "Shaded", exact: true})).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".cad-sphere")).toHaveAttribute("data-object-color", "255,0,0");
  await expect(page.locator(".scene-inspector").getByText("RGB 255 / 0 / 0", {exact: true})).toBeVisible();
  await expect(page.locator(".scene-inspector").getByText("8", {exact: true})).toBeVisible();
  await expect(page.locator(".scene-viewport svg")).toHaveAttribute("data-auto-fit", "bounds");
  await page.getByRole("button", {name: "Wireframe", exact: true}).click();
  await expect(page.getByRole("button", {name: "Wireframe", exact: true})).toHaveAttribute("aria-pressed", "true");
});

test("recovery Replay distinguishes re-read and verifies radius and color independently", async ({page}) => {
  await page.goto("/?demo=self-correction&mode=replay");
  await expect(page.locator(".proof-verdict").getByText("RECOVERED", {exact: true})).toBeVisible();
  await expect(page.locator(".proof-verdict").getByText("Verified after correction", {exact: true})).toBeVisible();
  await expect(page.locator(".proof-verdict").getByText("2 / 2", {exact: true})).toBeVisible();
  await expect(page.locator(".timeline").getByText("Scene read", {exact: true})).toBeVisible();
  await expect(page.locator(".timeline").getByText("Scene re-read", {exact: true})).toBeVisible();
  await expect(page.locator(".assertion-list > .assertion-row").getByText("sphere_radius", {exact: true})).toBeVisible();
  await expect(page.locator(".assertion-list > .assertion-row").getByText("sphere_color", {exact: true})).toBeVisible();
});

test("1440x900 viewport keeps the core evidence chain in the first screen", async ({page}) => {
  await page.setViewportSize({width: 1440, height: 900});
  await page.goto("/?demo=normal-loop&mode=replay");
  await expect(page.locator(".proof-verdict").getByText("5 / 5", {exact: true})).toBeVisible();
  const selectors = [".run-brief", ".public-dashboard", ".spatial-trace .section-title", ".cad-subject", ".proof-verdict", ".assertion-row"];
  const positions = await page.locator("main").evaluate((_, targets) => targets.map((selector) => {
    const rect = document.querySelector(selector)?.getBoundingClientRect();
    return rect ? {top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height} : null;
  }), selectors);
  for (const position of positions) {
    expect(position).not.toBeNull();
    expect(position!.top).toBeGreaterThanOrEqual(0);
    expect(position!.top).toBeLessThan(900);
  }
  const subject = positions[3]!;
  const viewport = await page.locator(".scene-viewport").boundingBox();
  expect(viewport).not.toBeNull();
  expect(subject.width / viewport!.width).toBeGreaterThan(.4);
  expect(subject.height / viewport!.height).toBeGreaterThan(.4);
});

test("public demo remains usable at a 390px viewport and has keyboard focus targets", async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto("/?demo=self-correction&mode=replay");
  await expect(page.locator(".dashboard").getByText("replay-correction", {exact: true})).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
  const selectedTab = page.getByRole("tab", {name: /错误恢复/});
  await selectedTab.focus();
  await expect(selectedTab).toBeFocused();
  await expect(page.getByRole("link", {name: "跳到运行证据"})).toHaveAttribute("href", "#evidence-chain");
  const readingOrder = await page.locator("main").evaluate(() => {
    const selectors = [".public-dashboard", ".proof-verdict", ".scene-stage", ".spatial-trace", ".scene-inspector", ".audit-panel"];
    return selectors.map((selector) => document.querySelector(selector)?.getBoundingClientRect().top ?? -1);
  });
  expect(readingOrder).toEqual([...readingOrder].sort((a, b) => a - b));
});
