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
          this.emit({type: "run.started", run_id: this.runId, seq: 1, timestamp: "2026-09-08T00:00:00Z", payload: {prompt: "Minimized"}});
          this.emit({type: "planning.started", run_id: this.runId, seq: 2, timestamp: "2026-09-08T00:00:01Z", payload: {round: 1}});
        }
        if (message.type === "cancel") {
          const terminal = {type: "run.cancelled", run_id: this.runId, seq: 3, timestamp: "2026-09-08T00:00:02Z", payload: {status: "cancelled", metrics: {duration_ms: 2000}}};
          this.emit(terminal);
          this.emit({
            type: "history.updated",
            history: [{run_id: this.runId, prompt: "Create a row of columns", closed_loop: true, status: "cancelled", events: [
              {type: "run.started", run_id: this.runId, seq: 1, timestamp: "2026-09-08T00:00:00Z", payload: {prompt: "Minimized"}},
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
  await page.getByPlaceholder("Choose a fixed scenario or enter a Rhino modeling task.").fill("Create a row of columns");
  await page.getByRole("button", {name: "Run task"}).click();
  await expect(page.locator(".dashboard").getByText("Running", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Stop"}).click();
  await expect(page.locator(".dashboard").getByText("Cancelled", {exact: true})).toBeVisible();
  await expect(page.getByRole("button", {name: "Stop"})).toBeDisabled();
  await expect(page.locator(".timeline .event-kind").filter({hasText: "Run cancelled"})).toBeVisible();
});
