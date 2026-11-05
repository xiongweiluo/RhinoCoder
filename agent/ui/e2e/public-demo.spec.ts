import { expect, test } from "@playwright/test";

const scenarios = [
  {id: "normal-loop", title: "Normal execution", events: "6/14 events", assertions: "5 / 5"},
  {id: "self-correction", title: "Self-correction", events: "10/14 events", assertions: "2 / 2"},
  {id: "privacy-route", title: "Privacy and routing", events: "6/11 events", assertions: "3 / 3"},
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
    await expect(page.getByRole("button", {name: "Key events", exact: true})).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText(scenario.events)).toBeVisible();
    await expect(page.getByRole("heading", {name: "Rhino scene result"})).toBeVisible();
    await expect(page.getByRole("heading", {name: "Why it passed"})).toBeVisible();
    await expect(page.locator(".proof-verdict").getByText(scenario.assertions, {exact: true})).toBeVisible();
    await expect(page.getByRole("heading", {name: "Privacy audit summary"})).toBeVisible();
    await expect(page.getByText("Not exposed", {exact: true})).toBeVisible();
    await expect(page.locator(".controls")).toHaveCount(0);
    await expect(page.getByRole("heading", {name: "Recent Runs"})).toHaveCount(0);
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await page.getByRole("button", {name: "All", exact: true}).click();
    await page.locator("details").evaluateAll((nodes) => nodes.forEach((node) => { node.open = true; }));
    expect(await page.locator("body").innerText()).not.toMatch(/\p{Script=Han}/u);
    const accessibleText = await page.locator("[aria-label], [title], [placeholder], svg title, svg desc").evaluateAll((nodes) => nodes.map((node) => [node.getAttribute("aria-label"), node.getAttribute("title"), node.getAttribute("placeholder"), node.textContent].join(" ")).join("\n"));
    expect(accessibleText).not.toMatch(/\p{Script=Han}/u);
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
  await expect(page.locator(".privacy-causality")).toContainText("Sensitive fields are minimized before the outbound model request.");
  await expect(page.locator(".scene-object-index").getByText("Legs ×4", {exact: true})).toBeVisible();
  await expect(page.locator(".scene-inspector").getByText("Legs × 4", {exact: true})).toBeVisible();
  await expect(page.locator(".scene-inspector").getByText("View individual objects", {exact: true})).toBeVisible();

  await page.getByRole("button", {name: "Verification", exact: true}).click();
  await expect(page.getByText("4/11 events", {exact: true})).toBeVisible();
  await expect(page.locator(".event-kind").filter({hasText: "Scene readback"})).toBeVisible();
  await expect(page.locator(".event-kind").filter({hasText: "Geometry assertion"}).first()).toBeVisible();

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
  const selectedTab = page.getByRole("tab", {name: /Self-correction/});
  await selectedTab.focus();
  await expect(selectedTab).toBeFocused();
  await expect(page.getByRole("link", {name: "Skip to run evidence"})).toHaveAttribute("href", "#evidence-chain");
  const readingOrder = await page.locator("main").evaluate(() => {
    const selectors = [".public-dashboard", ".proof-verdict", ".scene-stage", ".spatial-trace", ".scene-inspector", ".audit-panel"];
    return selectors.map((selector) => document.querySelector(selector)?.getBoundingClientRect().top ?? -1);
  });
  expect(readingOrder).toEqual([...readingOrder].sort((a, b) => a - b));
});
