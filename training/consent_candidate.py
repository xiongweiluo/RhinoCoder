"""Opt-in, durable human consent gate for candidate writes.

No live Agent or Rhino path imports this module. The HTTP UI can approve or
revoke a prepared call, but cannot create one or dispatch it. Only trusted
Python code can dispatch after a separate Rhino atomic-state/idempotency gate.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator, Mapping, Protocol, Sequence

if TYPE_CHECKING:
    from aiohttp import web

from agent.privacy import PrivacyAction, classify_request
from training.tool_contract_candidate import (
    ContractError,
    parse_invocation,
    validate_arguments,
    validate_inventory,
)
from training.tool_controller_candidate import (
    READ_ONLY_TOOLS,
    SceneState,
    StepOutcome,
    compose_step_input,
    task_sha256,
)


_RHINO_GUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
DELEGATED_HEADLESS_SCOPE = "isolated_unsaved_headless_mm"


class ConsentError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SceneProvider(Protocol):
    def snapshot(self) -> SceneState: ...


class SyntheticDryRunExecutor:
    """Records a hypothetical dispatch; it has no Rhino transport or write API."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def simulate_call(
        self, name: str, arguments: Mapping[str, Any], *,
        expected_state: SceneState, idempotency_key: str,
    ) -> dict[str, Any]:
        receipt = {
            "tool": name,
            "arguments_sha256": _sha256(_canonical_arguments(arguments)),
            "scene_revision": expected_state.revision,
            "idempotency_key": idempotency_key,
            "dry_run_only": True,
        }
        self.calls.append(receipt)
        return receipt


@dataclass(frozen=True)
class ConsentLink:
    request_id: str
    capability: str

    @property
    def path(self) -> str:
        return f"/candidate/confirm/{self.request_id}?cap={self.capability}"


@dataclass(frozen=True)
class _Display:
    task: str
    arguments_json: str
    scene_summary_json: str
    scene: SceneProvider
    review_note: str = ""
    delegated_scope: str = ""


def _canonical_arguments(arguments: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            arguments, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ConsentError("invalid_arguments") from exc


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ConsentStore:
    """Single-process UI session backed by transactional, append-only SQLite audit."""

    def __init__(
        self, path: Path, tools: Sequence[Mapping[str, Any]], *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.inventory = validate_inventory(tools)
        self.clock = clock
        self.session_id = secrets.token_hex(16)
        self._display: dict[str, _Display] = {}
        self._lock = threading.RLock()
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS consent_requests (
                    request_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    capability_sha256 TEXT NOT NULL,
                    task_sha256 TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_sha256 TEXT NOT NULL,
                    scene_revision INTEGER NOT NULL,
                    scene_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'pending','approved','revoked','expired','invalidated','consumed'
                    )),
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS consent_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL REFERENCES consent_requests(request_id),
                    event_type TEXT NOT NULL,
                    occurred_at INTEGER NOT NULL,
                    reason_code TEXT NOT NULL DEFAULT ''
                );
                CREATE TRIGGER IF NOT EXISTS consent_events_no_update
                    BEFORE UPDATE ON consent_events BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
                CREATE TRIGGER IF NOT EXISTS consent_events_no_delete
                    BEFORE DELETE ON consent_events BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
            """)
        self.path.chmod(0o600)
        with self._tx() as db:
            for row in db.execute(
                "SELECT request_id FROM consent_requests WHERE status IN ('pending','approved')"
            ).fetchall():
                self._set_status(db, row["request_id"], "invalidated", "process_restarted")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    def _event(self, db: sqlite3.Connection, request_id: str, kind: str, reason: str = "") -> None:
        db.execute(
            "INSERT INTO consent_events(request_id,event_type,occurred_at,reason_code) VALUES(?,?,?,?)",
            (request_id, kind, int(self.clock()), reason),
        )

    def _set_status(self, db: sqlite3.Connection, request_id: str, status: str, reason: str = "") -> None:
        db.execute("UPDATE consent_requests SET status=? WHERE request_id=?", (status, request_id))
        self._event(db, request_id, status, reason)

    def _row(self, db: sqlite3.Connection, request_id: str, capability: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM consent_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if (
            row is None or not isinstance(capability, str)
            or not secrets.compare_digest(row["capability_sha256"], _sha256(capability))
        ):
            raise ConsentError("not_found")
        return row

    def _current(self, row: sqlite3.Row) -> bool:
        display = self._display.get(row["request_id"])
        if display is None or row["session_id"] != self.session_id:
            return False
        try:
            state = display.scene.snapshot()
        except Exception:
            return False
        return (
            isinstance(state, SceneState)
            and state.revision == row["scene_revision"]
            and state.scene_sha256 == row["scene_sha256"]
        )

    def prepare(
        self, task: str, tool_name: str, arguments: Mapping[str, Any], *,
        scene: SceneProvider, ttl_seconds: int = 120,
        selection: StepOutcome | None = None,
        review_note: str = "",
        delegated_scope: str = "",
    ) -> ConsentLink:
        if not isinstance(task, str) or not task.strip() or len(task) > 4096:
            raise ConsentError("invalid_task")
        if tool_name in READ_ONLY_TOOLS or tool_name not in self.inventory:
            raise ConsentError("not_a_write_tool")
        if not isinstance(review_note, str) or len(review_note) > 512:
            raise ConsentError("invalid_review_note")
        if not isinstance(delegated_scope, str) or delegated_scope not in {"", DELEGATED_HEADLESS_SCOPE}:
            raise ConsentError("invalid_delegated_scope")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
            raise ConsentError("invalid_expiry")
        try:
            checked = validate_arguments(tool_name, dict(arguments), self.inventory[tool_name])
            arguments_json = _canonical_arguments(checked)
            if _RHINO_GUID.search(task) or _RHINO_GUID.search(arguments_json):
                raise ConsentError("raw_guid_rejected")
            state = scene.snapshot()
            current_input = compose_step_input(task, state)
            if selection is not None and (
                not isinstance(selection, StepOutcome)
                or selection.status != "selection_observed"
                or selection.stage != "selector"
                or selection.selected_tool != tool_name
                or selection.task_sha256 != task_sha256(task)
                or selection.before_revision != state.revision
                or selection.before_scene_sha256 != state.scene_sha256
            ):
                raise ConsentError("selection_binding_mismatch")
            action = classify_request(current_input + "\n" + arguments_json).action
            scene_summary_json = json.dumps(
                state.summary, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            )
        except ConsentError:
            raise
        except Exception as exc:
            raise ConsentError("preflight_rejected") from exc
        if action is PrivacyAction.BLOCK or action not in {
            PrivacyAction.ALLOW_CLOUD, PrivacyAction.MINIMIZE_CLOUD, PrivacyAction.FORCE_LOCAL,
        }:
            raise ConsentError("privacy_rejected")
        if len(arguments_json) > 4096:
            raise ConsentError("arguments_too_large")

        request_id = secrets.token_urlsafe(24)
        capability = secrets.token_urlsafe(32)
        now = int(self.clock())
        with self._tx() as db:
            db.execute(
                """INSERT INTO consent_requests VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    request_id, self.session_id, _sha256(capability), task_sha256(task),
                    tool_name, _sha256(arguments_json), state.revision,
                    state.scene_sha256, "pending", now, now + ttl_seconds,
                ),
            )
            self._event(db, request_id, "requested")
        self._display[request_id] = _Display(
            task, arguments_json, scene_summary_json, scene, review_note, delegated_scope,
        )
        return ConsentLink(request_id, capability)

    def prepare_from_invocation(
        self, task: str, selection: StepOutcome, invocation_text: str, *,
        scene: SceneProvider, ttl_seconds: int = 120,
    ) -> ConsentLink:
        """Bind a strict model call to its observed selection and fresh scene.

        This only creates a *pending* human review. The model cannot approve it.
        """

        if (
            not isinstance(selection, StepOutcome)
            or selection.status != "selection_observed"
            or selection.stage != "selector"
            or not isinstance(selection.selected_tool, str)
            or selection.selected_tool in READ_ONLY_TOOLS
        ):
            raise ConsentError("selection_not_write_ready")
        try:
            call = parse_invocation(invocation_text, selection.selected_tool, list(self.inventory.values()))
        except (ContractError, TypeError, ValueError) as exc:
            raise ConsentError("invocation_rejected") from exc
        return self.prepare(
            task, call["name"], call["arguments"], scene=scene,
            ttl_seconds=ttl_seconds, selection=selection,
        )

    def inspect(self, link: ConsentLink) -> tuple[dict[str, Any], _Display]:
        with self._tx() as db:
            row = self._row(db, link.request_id, link.capability)
            display = self._display.get(link.request_id)
            if display is None or row["session_id"] != self.session_id:
                raise ConsentError("not_available")
            if row["status"] in {"pending", "approved"}:
                if row["expires_at"] <= int(self.clock()):
                    self._set_status(db, link.request_id, "expired")
                elif not self._current(row):
                    self._set_status(db, link.request_id, "invalidated", "scene_or_session_changed")
                row = self._row(db, link.request_id, link.capability)
            return dict(row), display

    def status_for_runner(self, link: ConsentLink) -> str:
        """Read only the durable decision; never substitute for a scene check.

        Long-lived runners may wait for the operator without repeatedly
        consuming Rhino's bounded read-only request budget. `inspect` and
        `_consume` still enforce expiry, session identity, and fresh scene.
        """
        with self._tx() as db:
            row = self._row(db, link.request_id, link.capability)
            if row["session_id"] != self.session_id or link.request_id not in self._display:
                raise ConsentError("not_available")
            return str(row["status"])

    def decide(self, link: ConsentLink, decision: str) -> str:
        if decision not in {"approve", "revoke"}:
            raise ConsentError("invalid_decision")
        with self._tx() as db:
            row = self._row(db, link.request_id, link.capability)
            status = row["status"]
            if status not in ({"pending"} if decision == "approve" else {"pending", "approved"}):
                return status
            if row["expires_at"] <= int(self.clock()):
                status = "expired"
                self._set_status(db, link.request_id, status)
            elif not self._current(row):
                status = "invalidated"
                self._set_status(db, link.request_id, status, "scene_or_session_changed")
            else:
                status = "approved" if decision == "approve" else "revoked"
                self._set_status(db, link.request_id, status, "human_action")
            return status

    def approve_delegated_headless(self, link: ConsentLink) -> str:
        """Approve only a runner-marked disposable headless request.

        This is not exposed over HTTP and is never logged as a human click.
        The caller must first establish the isolated unsaved Rhino fixture;
        expiry, session binding and a fresh scene are still checked here.
        """
        with self._tx() as db:
            row = self._row(db, link.request_id, link.capability)
            display = self._display.get(link.request_id)
            if (display is None or row["session_id"] != self.session_id
                    or display.delegated_scope != DELEGATED_HEADLESS_SCOPE):
                raise ConsentError("delegated_scope_missing")
            if row["status"] != "pending":
                return str(row["status"])
            if row["expires_at"] <= int(self.clock()):
                self._set_status(db, link.request_id, "expired")
                return "expired"
            if not self._current(row):
                self._set_status(db, link.request_id, "invalidated", "scene_or_session_changed")
                return "invalidated"
            self._set_status(db, link.request_id, "approved", "codex_delegated_headless")
            return "approved"

    def abort_without_human(self, link: ConsentLink) -> str:
        """Fail-closed cleanup of a pending/approved candidate, never approval.

        Test and cancellation machinery must not leave a synthetic revocation
        mislabeled as a human action in the durable audit trail.
        """

        with self._tx() as db:
            row = self._row(db, link.request_id, link.capability)
            if row["status"] not in {"pending", "approved"}:
                return row["status"]
            self._set_status(db, link.request_id, "revoked", "automatic_safety_cleanup")
            return "revoked"

    def _consume(
        self, link: ConsentLink, *, task: str, tool_name: str,
        arguments: Mapping[str, Any], scene: SceneProvider,
    ) -> SceneState:
        arguments_json = _canonical_arguments(arguments)
        with self._tx() as db:
            row = self._row(db, link.request_id, link.capability)
            if row["status"] != "approved":
                error = "not_approved"
            elif row["expires_at"] <= int(self.clock()):
                self._set_status(db, link.request_id, "expired")
                error = "expired"
            elif (
                row["task_sha256"] != task_sha256(task)
                or row["tool_name"] != tool_name
                or row["arguments_sha256"] != _sha256(arguments_json)
                or link.request_id not in self._display
                or scene is not self._display[link.request_id].scene
            ):
                error = "binding_mismatch"
            else:
                try:
                    expected = scene.snapshot()
                except Exception:
                    expected = None
                if (
                    row["session_id"] != self.session_id
                    or not isinstance(expected, SceneState)
                    or expected.revision != row["scene_revision"]
                    or expected.scene_sha256 != row["scene_sha256"]
                ):
                    self._set_status(db, link.request_id, "invalidated", "scene_or_session_changed")
                    error = "scene_changed"
                else:
                    error = ""
                    self._set_status(db, link.request_id, "consumed")
            if error:
                self._event(db, link.request_id, "dispatch_denied", error)
        if error:
            raise ConsentError(error)
        return expected

    def dispatch_synthetic(
        self, link: ConsentLink, *, task: str, tool_name: str,
        arguments: Mapping[str, Any], scene: SceneProvider, executor: SyntheticDryRunExecutor,
    ) -> Any:
        """Consume before one synthetic dispatch; no real Rhino executor accepted."""

        if type(executor) is not SyntheticDryRunExecutor:
            raise ConsentError("real_execution_not_authorized")
        expected = self._consume(
            link, task=task, tool_name=tool_name, arguments=arguments, scene=scene,
        )
        try:
            receipt = executor.simulate_call(
                tool_name, arguments, expected_state=expected,
                idempotency_key=_sha256(link.request_id),
            )
        except Exception as exc:
            with self._tx() as db:
                self._event(db, link.request_id, "execution_uncertain")
            raise ConsentError("execution_uncertain") from exc
        with self._tx() as db:
            self._event(db, link.request_id, "synthetic_dispatched")
        return receipt

    def audit_events(self, request_id: str) -> list[dict[str, Any]]:
        with self._tx() as db:
            return [dict(row) for row in db.execute(
                "SELECT event_id,request_id,event_type,occurred_at,reason_code "
                "FROM consent_events WHERE request_id=? ORDER BY event_id", (request_id,),
            )]


def create_consent_app(store: ConsentStore) -> web.Application:
    """Expose only review/decision pages; no HTTP endpoint can create or dispatch."""

    from aiohttp import web  # noqa: PLC0415

    app = web.Application(client_max_size=2048)
    stylesheet = """
        :root { font-family: system-ui, sans-serif; color: #17212b; background: #f3f6f8; }
        * { box-sizing: border-box; }
        body { margin: 0; padding: 1.5rem; }
        main { max-width: 44rem; margin: 2rem auto; padding: 2rem; background: white;
               border: 1px solid #d7e0e7; border-radius: 1rem; box-shadow: 0 12px 36px #182a3a12; }
        h1 { margin-top: 0; font-size: clamp(1.35rem, 4vw, 1.8rem); }
        .notice { color: #57481b; background: #fff5d9; padding: .8rem; border-radius: .5rem; }
        dl { display: grid; grid-template-columns: 8rem 1fr; gap: .8rem; }
        dt { color: #536779; font-weight: 650; }
        dd { margin: 0; overflow-wrap: anywhere; }
        pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
        form { margin-top: 1rem; }
        label { display: flex; gap: .6rem; align-items: flex-start; line-height: 1.5; }
        input[type=checkbox] { width: 1.2rem; height: 1.2rem; flex: none; }
        button { padding: .75rem 1rem; border: 0; border-radius: .5rem; color: white;
                 background: #185a73; font: inherit; font-weight: 650; cursor: pointer; }
        button.danger { background: #9b2c2c; }
        button:focus-visible, input:focus-visible { outline: 3px solid #d49b21; outline-offset: 3px; }
        @media (max-width: 35rem) { body { padding: .5rem; } main { padding: 1rem; margin: 0; }
                                   dl { grid-template-columns: 1fr; gap: .35rem; } dd { margin-bottom: .6rem; } }
    """

    def security_headers(response: web.Response) -> web.Response:
        response.headers.update({
            "Cache-Control": "no-store",
            # `no-referrer` makes Chromium send `Origin: null` for same-origin
            # form POSTs. `strict-origin` keeps exact Origin CSRF validation
            # while never sending the capability-bearing path/query as Referer.
            "Referrer-Policy": "strict-origin",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'",
        })
        return response

    async def css(_request: web.Request) -> web.Response:
        return security_headers(web.Response(text=stylesheet, content_type="text/css"))

    async def page(request: web.Request) -> web.Response:
        link = ConsentLink(request.match_info["request_id"], request.query.get("cap", ""))
        try:
            row, display = store.inspect(link)
        except ConsentError:
            raise web.HTTPNotFound(text="确认请求不可用")
        title = "候选写操作确认"
        expires_at = datetime.fromtimestamp(row["expires_at"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        details = (
            "<dl>"
            + (f"<dt>执行范围</dt><dd>{html.escape(display.review_note)}</dd>" if display.review_note else "")
            +
            f"<dt>任务</dt><dd>{html.escape(display.task)}</dd>"
            f"<dt>工具</dt><dd><code>{html.escape(row['tool_name'])}</code></dd>"
            f"<dt>参数</dt><dd><pre>{html.escape(display.arguments_json)}</pre></dd>"
            f"<dt>场景版本</dt><dd>{row['scene_revision']} / <code>{html.escape(row['scene_sha256'])}</code></dd>"
            f"<dt>场景摘要</dt><dd><pre>{html.escape(display.scene_summary_json)}</pre></dd>"
            f"<dt>授权截止</dt><dd>{expires_at}</dd>"
            f"<dt>状态</dt><dd>{html.escape(row['status'])}</dd>"
            "</dl>"
        )
        actions = ""
        if row["status"] in {"pending", "approved"}:
            action = f"/candidate/confirm/{html.escape(link.request_id)}"
            hidden = f'<input type="hidden" name="capability" value="{html.escape(link.capability)}">'
            if row["status"] == "pending":
                actions += (
                    f'<form method="post" action="{action}">{hidden}'
                    '<label><input type="checkbox" name="acknowledged" value="yes" required>'
                    '我已核对任务、工具、参数与当前场景</label>'
                    '<button name="decision" value="approve">明确批准本次写操作</button></form>'
                )
            actions += (
                f'<form method="post" action="{action}">{hidden}'
                '<button class="danger" name="decision" value="revoke">撤销本次授权</button></form>'
            )
        notice = (
            "打开页面不等于批准；批准后，独立的受控运行器会尝试执行本页所列的一次性写入。"
            if display.review_note else "打开页面不等于批准；此页面不会执行 Rhino 写入。"
        )
        afterword = (
            "批准生成一次性许可，受控运行器会立即消费；失败不会自动重试，几何 Undo 尚未接入。"
            if display.review_note else "批准只生成一次性许可；执行后几何 Undo 尚未接入。"
        )
        body = (
            "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{title}</title><link rel='stylesheet' href='/candidate/consent.css'></head>"
            f"<body><main><h1>{title}</h1><p class='notice'>请逐项核对。{notice}</p>"
            f"{details}{actions}"
            f"<p>{afterword}</p>"
            "</main></body></html>"
        )
        return security_headers(web.Response(text=body, content_type="text/html"))

    async def decide(request: web.Request) -> web.Response:
        if request.headers.get("Origin") != f"http://{request.host}":
            raise web.HTTPForbidden(text="仅允许同源用户操作")
        if request.content_type != "application/x-www-form-urlencoded":
            raise web.HTTPUnsupportedMediaType(text="表单格式无效")
        data = await request.post()
        if data.get("decision") == "approve" and data.get("acknowledged") != "yes":
            raise web.HTTPBadRequest(text="必须明确核对并勾选确认")
        link = ConsentLink(request.match_info["request_id"], str(data.get("capability", "")))
        try:
            status = store.decide(link, str(data.get("decision", "")))
        except ConsentError:
            raise web.HTTPNotFound(text="确认请求不可用")
        display = store._display.get(link.request_id)
        message = (
            "批准状态已记录；独立受控运行器可能正在处理本次一次性授权。"
            if display is not None and display.review_note and status == "approved"
            else "此页面不会执行 Rhino 写入。"
        )
        return security_headers(web.Response(
            text="<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
                 "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                 "<link rel='stylesheet' href='/candidate/consent.css'></head>"
                 f"<body><main><h1>授权状态：{html.escape(status)}</h1>"
                 f"<p>{message}</p></main></body></html>",
            content_type="text/html",
        ))

    app.router.add_get("/candidate/consent.css", css)
    app.router.add_get("/candidate/confirm/{request_id}", page)
    app.router.add_post("/candidate/confirm/{request_id}", decide)
    return app


async def start_local_consent_ui(
    store: ConsentStore, *, port: int = 0,
) -> tuple[web.AppRunner, str]:
    """Start opt-in review UI bound to loopback only; caller owns cleanup."""

    from aiohttp import web  # noqa: PLC0415

    runner = web.AppRunner(create_consent_app(store))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    actual_port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{actual_port}"
