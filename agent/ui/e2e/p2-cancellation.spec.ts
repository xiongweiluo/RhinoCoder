import { expect, test } from "@playwright/test";

test("a live cancellation terminal leaves the UI out of its running state", async ({page}) => {
  await page.addInitScript(() => {
    class TestSocket {
      static OPEN = 1;
      static CLOSED = 3;
      readyState = 0;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      private runId = "p2-cancel-browser";

      constructor() {
        window.setTimeout(() => {
          this.readyState = TestSocket.OPEN;
          this.onopen?.(new Event("open"));
          this.emit({type: "snapshot", active: [], history: []});
        }, 0);
      }

      send(raw: string) {
        const message = JSON.parse(raw);
        if (message.type === "instruction") {
          this.emit({type: "control.accepted", action: "start", run_id: this.runId});
          this.emit({type: "run.started", run_id: this.runId, seq: 1, timestamp: "2026-09-08T00:00:00Z", payload: {prompt: "已最小化"}});
          this.emit({type: "planning.started", run_id: this.runId, seq: 2, timestamp: "2026-09-08T00:00:01Z", payload: {round: 1}});
        }
        if (message.type === "cancel") {
          const terminal = {type: "run.cancelled", run_id: this.runId, seq: 3, timestamp: "2026-09-08T00:00:02Z", payload: {status: "cancelled", metrics: {duration_ms: 2000}}};
          this.emit(terminal);
          this.emit({
            type: "history.updated",
            history: [{run_id: this.runId, prompt: "创建一排柱子", closed_loop: true, status: "cancelled", events: [
              {type: "run.started", run_id: this.runId, seq: 1, timestamp: "2026-09-08T00:00:00Z", payload: {prompt: "已最小化"}},
              {type: "planning.started", run_id: this.runId, seq: 2, timestamp: "2026-09-08T00:00:01Z", payload: {round: 1}},
              terminal,
            ]}],
          });
        }
      }

      close() {
        this.readyState = TestSocket.CLOSED;
        this.onclose?.();
      }

      private emit(value: unknown) {
        window.setTimeout(() => this.onmessage?.(new MessageEvent("message", {data: JSON.stringify(value)})), 0);
      }
    }
    Object.defineProperty(window, "WebSocket", {value: TestSocket, configurable: true});
  });

  await page.goto("/");
  await expect(page.getByRole("status").filter({hasText: "Connected"})).toBeVisible();
  await page.getByPlaceholder("选择一个固定场景，或输入 Rhino 建模任务。").fill("创建一排柱子");
  await page.getByRole("button", {name: "执行任务"}).click();
  await expect(page.locator(".dashboard").getByText("执行中", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "停止"}).click();
  await expect(page.locator(".dashboard").getByText("已取消", {exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: "停止"})).toBeDisabled();
  await expect(page.locator(".timeline .event-kind").filter({hasText: "任务取消"})).toBeVisible();
});
