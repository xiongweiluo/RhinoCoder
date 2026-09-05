"""Versioned SQLite audit store for runs, training data, and routing decisions."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from agent.sanitizer import contains_sensitive_data, sanitize_structure
from agent.privacy import sanitize_for_log


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUDIT_DB = PROJECT_ROOT / "data" / "audit" / "rhinocoder.sqlite3"
SCHEMA_VERSION = 2
logger = logging.getLogger("rhinocoder.audit_db")


MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (
        1,
        "initial_audit_schema",
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE tasks (
            task_key TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            instruction TEXT NOT NULL DEFAULT '',
            difficulty INTEGER,
            tags_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(campaign_id, task_id)
        );

        CREATE TABLE models (
            model_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            name TEXT NOT NULL,
            version TEXT,
            backend TEXT NOT NULL DEFAULT 'cloud',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            task_key TEXT NOT NULL REFERENCES tasks(task_key),
            model_id TEXT NOT NULL REFERENCES models(model_id),
            schema_version TEXT,
            app_version TEXT,
            prompt_version TEXT,
            tool_schema_version TEXT,
            instruction TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            duration_ms REAL NOT NULL DEFAULT 0,
            final_text TEXT NOT NULL DEFAULT '',
            messages_json TEXT NOT NULL DEFAULT '[]',
            events_json TEXT NOT NULL DEFAULT '[]',
            created_object_ids_json TEXT NOT NULL DEFAULT '[]',
            error_code TEXT,
            error_message TEXT,
            error_recoverable INTEGER NOT NULL DEFAULT 0 CHECK(error_recoverable IN (0, 1)),
            failure_type TEXT,
            source_kind TEXT NOT NULL,
            is_golden INTEGER NOT NULL DEFAULT 0 CHECK(is_golden IN (0, 1)),
            content_hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE route_decisions (
            route_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            selected_backend TEXT NOT NULL,
            selected_model_id TEXT REFERENCES models(model_id),
            privacy_level TEXT,
            task_difficulty INTEGER,
            tool_complexity TEXT,
            cost_budget_usd REAL,
            latency_budget_ms REAL,
            reason TEXT NOT NULL DEFAULT '',
            fallback_from TEXT,
            degraded INTEGER NOT NULL DEFAULT 0 CHECK(degraded IN (0, 1)),
            decision_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE tool_calls (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            call_id TEXT NOT NULL,
            call_index INTEGER NOT NULL,
            name TEXT NOT NULL,
            arguments_json TEXT NOT NULL DEFAULT '{}',
            round_index INTEGER,
            started_at TEXT,
            completed_at TEXT,
            duration_ms REAL NOT NULL DEFAULT 0,
            success INTEGER NOT NULL CHECK(success IN (0, 1)),
            output TEXT NOT NULL DEFAULT '',
            error_code TEXT,
            PRIMARY KEY(run_id, call_id)
        );

        CREATE TABLE scene_checks (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            check_index INTEGER NOT NULL,
            call_id TEXT,
            round_index INTEGER,
            timestamp TEXT,
            success INTEGER NOT NULL CHECK(success IN (0, 1)),
            output TEXT NOT NULL DEFAULT '',
            summary_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(run_id, check_index)
        );

        CREATE TABLE assertions (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            assertion_index INTEGER NOT NULL,
            kind TEXT,
            passed INTEGER NOT NULL CHECK(passed IN (0, 1)),
            reason TEXT NOT NULL DEFAULT '',
            specification_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(run_id, assertion_index)
        );

        CREATE TABLE feedback (
            feedback_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            timestamp TEXT,
            note TEXT NOT NULL DEFAULT '',
            feedback_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE admissions (
            run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
            admitted INTEGER NOT NULL CHECK(admitted IN (0, 1)),
            run_status TEXT,
            human_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(human_confirmed IN (0, 1)),
            assertions_passed INTEGER NOT NULL DEFAULT 0 CHECK(assertions_passed IN (0, 1)),
            partial INTEGER NOT NULL DEFAULT 0 CHECK(partial IN (0, 1)),
            scene_check_count INTEGER NOT NULL DEFAULT 0,
            successful_scene_summary INTEGER NOT NULL DEFAULT 0 CHECK(successful_scene_summary IN (0, 1)),
            feedback_label TEXT,
            feedback_source TEXT,
            sanitization_applied INTEGER NOT NULL DEFAULT 0 CHECK(sanitization_applied IN (0, 1)),
            reasons_json TEXT NOT NULL DEFAULT '[]',
            admission_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE cost_usage (
            run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            prompt_cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
            prompt_cache_miss_tokens INTEGER NOT NULL DEFAULT 0,
            prompt_cache_unknown_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            input_cost_lower_bound_usd REAL NOT NULL DEFAULT 0,
            input_cost_upper_bound_usd REAL NOT NULL DEFAULT 0,
            output_cost_usd REAL NOT NULL DEFAULT 0,
            estimated_cost_lower_bound_usd REAL NOT NULL DEFAULT 0,
            estimated_cost_upper_bound_usd REAL NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL DEFAULT 0,
            estimate_status TEXT NOT NULL DEFAULT 'unconfigured',
            usage_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE artifacts (
            artifact_id TEXT PRIMARY KEY,
            run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,
            task_key TEXT REFERENCES tasks(task_key),
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            mime_type TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE import_batches (
            import_id TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            summary_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(source_path, source_sha256)
        );
        """,
    ),
    (
        2,
        "audit_query_indexes",
        """
        CREATE INDEX idx_runs_task ON runs(task_key);
        CREATE INDEX idx_runs_model ON runs(model_id);
        CREATE INDEX idx_runs_status ON runs(status, is_golden);
        CREATE INDEX idx_route_run ON route_decisions(run_id, timestamp);
        CREATE INDEX idx_tool_name ON tool_calls(name, success);
        CREATE INDEX idx_feedback_run ON feedback(run_id, label);
        CREATE INDEX idx_artifacts_run ON artifacts(run_id, kind);
        CREATE INDEX idx_artifacts_task ON artifacts(task_key, kind);
        """,
    ),
)


@dataclass(frozen=True)
class ImportSummary:
    source_path: str
    source_sha256: str
    source_rows: int
    golden_runs: int
    golden_tasks: int
    tool_calls: int
    scene_checks: int
    assertions: int
    feedback: int
    admissions: int
    cost_usage: int
    artifacts: int
    counts_unchanged_on_repeat: bool
    sensitive_field_findings: int
    lineage_findings: int


@dataclass(frozen=True)
class AuditResult:
    passed: bool
    schema_version: int
    integrity: str
    foreign_key_findings: list[dict[str, Any]]
    sensitive_field_findings: list[str]
    lineage_findings: list[str]
    counts: dict[str, int]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        sanitize_structure(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(sanitize_structure(str(value)))


def _bool(value: Any) -> int:
    return int(bool(value))


def _provider_for_model(name: str) -> str:
    lowered = name.lower()
    if "deepseek" in lowered:
        return "deepseek"
    if "claude" in lowered or "anthropic" in lowered:
        return "anthropic"
    if "gpt" in lowered or "openai" in lowered:
        return "openai"
    return "unknown" if name == "unknown" else "custom"


def _model_name(record: dict[str, Any]) -> str:
    route_decision = (record.get("run") or {}).get("route_decision") or record.get(
        "route_decision"
    )
    if isinstance(route_decision, dict) and route_decision.get("selected_model"):
        return str(route_decision["selected_model"])
    run = record.get("run") or {}
    for event in run.get("events") or []:
        if isinstance(event, dict) and event.get("type") == "run.started":
            model = str((event.get("payload") or {}).get("model") or "").strip()
            if model:
                return model
    return str(record.get("model") or "unknown")


def _record_task(record: dict[str, Any], run_id: str) -> tuple[str, dict[str, Any]]:
    metadata = record.get("metadata") or {}
    task = record.get("task") or metadata.get("task") or {}
    campaign_id = str(task.get("campaign_id") or "adhoc")
    task_id = str(task.get("task_id") or run_id)
    normalized = {**task, "campaign_id": campaign_id, "task_id": task_id}
    return f"{campaign_id}/{task_id}", normalized


def _failure_type(record: dict[str, Any]) -> str | None:
    run = record.get("run") or {}
    error = run.get("error") or {}
    if error.get("code"):
        return str(error["code"]).split(".", 1)[0]
    evaluation = record.get("evaluation") or (record.get("metadata") or {}).get("evaluation") or {}
    reasons = evaluation.get("failed_reasons") or []
    if reasons:
        return str(reasons[0]).split(":", 1)[0]
    if run.get("status") not in (None, "completed"):
        return str(run.get("status"))
    return None


class AuditDatabase:
    """Thread-safe SQLite database with nested transactions and migrations."""

    def __init__(self, path: Path | str = DEFAULT_AUDIT_DB) -> None:
        self.path = Path(path).expanduser().resolve()
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not parent_existed:
            self.path.parent.chmod(0o700)
        self._connection = sqlite3.connect(
            self.path,
            timeout=10,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._transaction_depth = 0
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")
        self._connection.execute("PRAGMA busy_timeout = 10000")
        self._secure_database_files()
        self.migrate()

    def __enter__(self) -> "AuditDatabase":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._connection.close()
            self._secure_database_files()

    def _secure_database_files(self) -> None:
        for path in (
            self.path,
            self.path.with_name(f"{self.path.name}-wal"),
            self.path.with_name(f"{self.path.name}-shm"),
        ):
            if path.exists():
                path.chmod(0o600)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            depth = self._transaction_depth
            savepoint = f"audit_sp_{depth}"
            self._connection.execute("BEGIN IMMEDIATE" if depth == 0 else f"SAVEPOINT {savepoint}")
            self._transaction_depth += 1
            try:
                yield
            except Exception:
                self._transaction_depth -= 1
                if depth == 0:
                    self._connection.execute("ROLLBACK")
                else:
                    self._connection.execute(f"ROLLBACK TO {savepoint}")
                    self._connection.execute(f"RELEASE {savepoint}")
                raise
            else:
                self._transaction_depth -= 1
                self._connection.execute("COMMIT" if depth == 0 else f"RELEASE {savepoint}")

    def migrate(self) -> None:
        with self._lock:
            current = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            if current > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema {current} is newer than supported {SCHEMA_VERSION}"
                )
            for version, name, script in MIGRATIONS:
                if version <= current:
                    continue
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in script.split(";"):
                        if statement.strip():
                            self._connection.execute(statement)
                    self._connection.execute(
                        "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                        (version, name, utc_now()),
                    )
                    self._connection.execute(f"PRAGMA user_version = {version}")
                    self._connection.execute("COMMIT")
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise

    @property
    def schema_version(self) -> int:
        return int(self._connection.execute("PRAGMA user_version").fetchone()[0])

    def _upsert_task(self, task_key: str, task: dict[str, Any], instruction: str) -> None:
        now = utc_now()
        self._connection.execute(
            """
            INSERT INTO tasks(
                task_key, campaign_id, task_id, instruction, difficulty,
                tags_json, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_key) DO UPDATE SET
                instruction=CASE WHEN excluded.instruction = '' THEN tasks.instruction ELSE excluded.instruction END,
                difficulty=COALESCE(excluded.difficulty, tasks.difficulty),
                tags_json=CASE WHEN excluded.tags_json = '[]' THEN tasks.tags_json ELSE excluded.tags_json END,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                task_key,
                str(task.get("campaign_id") or "adhoc"),
                str(task.get("task_id") or task_key),
                _safe_text(instruction),
                task.get("difficulty"),
                _canonical_json(task.get("tags") or []),
                _canonical_json(task),
                now,
                now,
            ),
        )

    def _upsert_model(
        self,
        name: str,
        *,
        provider: str | None = None,
        backend: str = "cloud",
    ) -> str:
        provider = provider or _provider_for_model(name)
        model_id = f"{provider}:{name}"
        now = utc_now()
        self._connection.execute(
            """
            INSERT INTO models(
                model_id, provider, name, backend, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_id) DO UPDATE SET
                backend=excluded.backend,
                updated_at=excluded.updated_at
            """,
            (model_id, provider, _safe_text(name), _safe_text(backend), now, now),
        )
        return model_id

    def ingest_trace(
        self,
        record: dict[str, Any],
        *,
        source_kind: str = "live",
        is_golden: bool = False,
        artifact_path: Path | None = None,
        artifact_root: Path = PROJECT_ROOT,
    ) -> None:
        sanitized = sanitize_structure(record)
        run_id = str(sanitized.get("run_id") or (sanitized.get("run") or {}).get("run_id") or "")
        if not run_id:
            raise ValueError("Audit trace requires run_id")
        run = sanitized.get("run") or {}
        metadata = sanitized.get("metadata") or {}
        evaluation = sanitized.get("evaluation") or metadata.get("evaluation") or {}
        admission = sanitized.get("admission") or metadata.get("admission") or {}
        feedback_record = sanitized.get("feedback") or metadata.get("feedback") or {}
        instruction = str(sanitized.get("instruction") or "")
        task_key, task = _record_task(sanitized, run_id)
        metrics = run.get("metrics") or {}
        error = run.get("error") or {}
        route_decision = run.get("route_decision") or sanitized.get("route_decision") or {}
        model_name = _model_name(sanitized)
        content_hash = _sha256_bytes(_canonical_json(sanitized).encode("utf-8"))
        now = utc_now()

        with self.transaction():
            self._upsert_task(task_key, task, instruction)
            route_model_id = str(route_decision.get("selected_model_id") or "")
            route_provider = route_model_id.split(":", 1)[0] if ":" in route_model_id else None
            route_backend = str(route_decision.get("selected_backend") or "cloud")
            model_id = self._upsert_model(
                model_name,
                provider=route_provider,
                backend=route_backend,
            )
            self._connection.execute(
                """
                INSERT INTO runs(
                    run_id, task_key, model_id, schema_version, app_version,
                    prompt_version, tool_schema_version, instruction, status,
                    started_at, completed_at, duration_ms, final_text, messages_json,
                    events_json, created_object_ids_json, error_code, error_message,
                    error_recoverable, failure_type, source_kind, is_golden,
                    content_hash, metadata_json, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(run_id) DO UPDATE SET
                    task_key=excluded.task_key,
                    model_id=excluded.model_id,
                    schema_version=excluded.schema_version,
                    app_version=excluded.app_version,
                    prompt_version=excluded.prompt_version,
                    tool_schema_version=excluded.tool_schema_version,
                    instruction=CASE WHEN excluded.instruction = '' THEN runs.instruction ELSE excluded.instruction END,
                    status=excluded.status,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at,
                    duration_ms=excluded.duration_ms,
                    final_text=excluded.final_text,
                    messages_json=excluded.messages_json,
                    events_json=excluded.events_json,
                    created_object_ids_json=excluded.created_object_ids_json,
                    error_code=excluded.error_code,
                    error_message=excluded.error_message,
                    error_recoverable=excluded.error_recoverable,
                    failure_type=excluded.failure_type,
                    source_kind=excluded.source_kind,
                    is_golden=MAX(runs.is_golden, excluded.is_golden),
                    content_hash=excluded.content_hash,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    run_id,
                    task_key,
                    model_id,
                    str(sanitized.get("schema_version") or ""),
                    str(sanitized.get("app_version") or metadata.get("app_version") or ""),
                    str(sanitized.get("prompt_version") or metadata.get("prompt_version") or ""),
                    str(sanitized.get("tool_schema_version") or metadata.get("tool_schema_version") or ""),
                    _safe_text(instruction),
                    str(run.get("status") or admission.get("run_status") or "unknown"),
                    metrics.get("started_at"),
                    metrics.get("completed_at"),
                    float(metrics.get("duration_ms") or 0),
                    _safe_text(run.get("final_text")),
                    _canonical_json(run.get("messages") or sanitized.get("messages") or []),
                    _canonical_json(run.get("events") or []),
                    _canonical_json(run.get("created_object_ids") or []),
                    error.get("code"),
                    _safe_text(error.get("message")),
                    _bool(error.get("recoverable")),
                    _failure_type(sanitized),
                    _safe_text(source_kind),
                    _bool(is_golden),
                    content_hash,
                    _canonical_json(metadata),
                    now,
                    now,
                ),
            )
            self._replace_tool_calls(run_id, run.get("tool_calls") or [])
            self._replace_scene_checks(run_id, run.get("scene_checks") or [])
            self._replace_assertions(run_id, evaluation.get("results") or [])
            self._upsert_cost_usage(run_id, metrics)
            if route_decision:
                self.record_route_decision(
                    run_id,
                    {**route_decision, "selected_model_id": model_id},
                )
            if feedback_record:
                self.ingest_feedback({**feedback_record, "run_id": run_id})
            if admission:
                self.upsert_admission(run_id, admission, admitted=is_golden)
            if artifact_path is not None:
                self.record_artifact(
                    kind="trace",
                    path=artifact_path,
                    root=artifact_root,
                    run_id=run_id,
                    task_key=task_key,
                )

    def _replace_tool_calls(self, run_id: str, calls: Sequence[dict[str, Any]]) -> None:
        self._connection.execute("DELETE FROM tool_calls WHERE run_id = ?", (run_id,))
        for index, call in enumerate(calls):
            call_id = str(call.get("call_id") or f"call-{index}")
            self._connection.execute(
                "INSERT INTO tool_calls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    call_id,
                    index,
                    str(call.get("name") or "unknown"),
                    _canonical_json(call.get("arguments") or {}),
                    call.get("round_index"),
                    call.get("started_at"),
                    call.get("completed_at"),
                    float(call.get("duration_ms") or 0),
                    _bool(call.get("success")),
                    _safe_text(call.get("output")),
                    call.get("error_code"),
                ),
            )

    def _replace_scene_checks(self, run_id: str, checks: Sequence[dict[str, Any]]) -> None:
        self._connection.execute("DELETE FROM scene_checks WHERE run_id = ?", (run_id,))
        for index, check in enumerate(checks):
            self._connection.execute(
                "INSERT INTO scene_checks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    index,
                    check.get("call_id"),
                    check.get("round"),
                    check.get("timestamp"),
                    _bool(check.get("success")),
                    _safe_text(check.get("output")),
                    _canonical_json(check.get("scene_summary") or {}),
                ),
            )

    def _replace_assertions(self, run_id: str, assertions: Sequence[dict[str, Any]]) -> None:
        self._connection.execute("DELETE FROM assertions WHERE run_id = ?", (run_id,))
        for index, assertion in enumerate(assertions):
            specification = assertion.get("spec") or {}
            self._connection.execute(
                "INSERT INTO assertions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    index,
                    specification.get("kind"),
                    _bool(assertion.get("ok")),
                    _safe_text(assertion.get("reason")),
                    _canonical_json(specification),
                ),
            )

    def _upsert_cost_usage(self, run_id: str, metrics: dict[str, Any]) -> None:
        values = (
            run_id,
            int(metrics.get("prompt_tokens") or 0),
            int(metrics.get("prompt_cache_hit_tokens") or 0),
            int(metrics.get("prompt_cache_miss_tokens") or 0),
            int(metrics.get("prompt_cache_unknown_tokens") or 0),
            int(metrics.get("completion_tokens") or 0),
            int(metrics.get("total_tokens") or 0),
            float(metrics.get("input_cost_lower_bound_usd") or 0),
            float(metrics.get("input_cost_upper_bound_usd") or 0),
            float(metrics.get("output_cost_usd") or 0),
            float(metrics.get("estimated_cost_lower_bound_usd") or 0),
            float(metrics.get("estimated_cost_upper_bound_usd") or 0),
            float(metrics.get("estimated_cost_usd") or 0),
            str(metrics.get("cost_estimate_status") or "unconfigured"),
            _canonical_json(metrics),
        )
        self._connection.execute(
            """
            INSERT INTO cost_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                prompt_tokens=excluded.prompt_tokens,
                prompt_cache_hit_tokens=excluded.prompt_cache_hit_tokens,
                prompt_cache_miss_tokens=excluded.prompt_cache_miss_tokens,
                prompt_cache_unknown_tokens=excluded.prompt_cache_unknown_tokens,
                completion_tokens=excluded.completion_tokens,
                total_tokens=excluded.total_tokens,
                input_cost_lower_bound_usd=excluded.input_cost_lower_bound_usd,
                input_cost_upper_bound_usd=excluded.input_cost_upper_bound_usd,
                output_cost_usd=excluded.output_cost_usd,
                estimated_cost_lower_bound_usd=excluded.estimated_cost_lower_bound_usd,
                estimated_cost_upper_bound_usd=excluded.estimated_cost_upper_bound_usd,
                estimated_cost_usd=excluded.estimated_cost_usd,
                estimate_status=excluded.estimate_status,
                usage_json=excluded.usage_json
            """,
            values,
        )

    def ingest_feedback(self, record: dict[str, Any]) -> str:
        sanitized = sanitize_structure(record)
        run_id = str(sanitized.get("run_id") or "")
        if not run_id:
            raise ValueError("Audit feedback requires run_id")
        feedback_id = _sha256_bytes(_canonical_json(sanitized).encode("utf-8"))
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO feedback(
                    feedback_id, run_id, label, source, timestamp, note, feedback_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feedback_id) DO NOTHING
                """,
                (
                    feedback_id,
                    run_id,
                    str(sanitized.get("label") or "unknown"),
                    str(sanitized.get("source") or ""),
                    sanitized.get("timestamp"),
                    _safe_text(sanitized.get("note")),
                    _canonical_json(sanitized),
                ),
            )
        return feedback_id

    def upsert_admission(
        self, run_id: str, admission: dict[str, Any], *, admitted: bool = True
    ) -> None:
        sanitized = sanitize_structure(admission)
        reasons = sanitized.get("reasons") or sanitized.get("gate_reasons") or []
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO admissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    admitted=MAX(admissions.admitted, excluded.admitted),
                    run_status=excluded.run_status,
                    human_confirmed=excluded.human_confirmed,
                    assertions_passed=excluded.assertions_passed,
                    partial=excluded.partial,
                    scene_check_count=excluded.scene_check_count,
                    successful_scene_summary=excluded.successful_scene_summary,
                    feedback_label=excluded.feedback_label,
                    feedback_source=excluded.feedback_source,
                    sanitization_applied=excluded.sanitization_applied,
                    reasons_json=excluded.reasons_json,
                    admission_json=excluded.admission_json
                """,
                (
                    run_id,
                    _bool(admitted),
                    sanitized.get("run_status"),
                    _bool(sanitized.get("human_confirmed")),
                    _bool(sanitized.get("assertions_passed")),
                    _bool(sanitized.get("partial")),
                    int(sanitized.get("scene_check_count") or 0),
                    _bool(sanitized.get("successful_get_scene_summary")),
                    sanitized.get("feedback_label"),
                    sanitized.get("feedback_source"),
                    _bool(sanitized.get("sanitization_applied")),
                    _canonical_json(reasons),
                    _canonical_json(sanitized),
                ),
            )

    def mark_golden(self, golden_record: dict[str, Any]) -> None:
        sanitized = sanitize_structure(golden_record)
        run_id = str(sanitized.get("run_id") or "")
        metadata = sanitized.get("metadata") or {}
        if not run_id:
            raise ValueError("Golden audit record requires run_id")
        with self.transaction():
            exists = self._connection.execute(
                "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if not exists:
                self.ingest_trace(
                    {
                        "run_id": run_id,
                        "schema_version": sanitized.get("schema_version"),
                        "messages": sanitized.get("messages") or [],
                        "task": metadata.get("task") or {},
                        "evaluation": metadata.get("evaluation") or {},
                        "feedback": metadata.get("feedback") or {},
                        "admission": metadata.get("admission") or {},
                        "run": {
                            "run_id": run_id,
                            "status": (metadata.get("admission") or {}).get("run_status") or "completed",
                            "messages": sanitized.get("messages") or [],
                        },
                    },
                    source_kind="golden_jsonl",
                    is_golden=True,
                )
            self._connection.execute(
                "UPDATE runs SET is_golden = 1, metadata_json = ?, updated_at = ? WHERE run_id = ?",
                (_canonical_json(metadata), utc_now(), run_id),
            )
            if metadata.get("admission"):
                self.upsert_admission(run_id, metadata["admission"], admitted=True)
            if metadata.get("feedback"):
                self.ingest_feedback({**metadata["feedback"], "run_id": run_id})

    def record_route_decision(self, run_id: str, decision: dict[str, Any]) -> str:
        sanitized = sanitize_structure(decision)
        canonical = _canonical_json({"run_id": run_id, **sanitized})
        route_id = str(sanitized.get("route_id") or _sha256_bytes(canonical.encode("utf-8")))
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO route_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(route_id) DO UPDATE SET decision_json=excluded.decision_json
                """,
                (
                    route_id,
                    run_id,
                    str(sanitized.get("timestamp") or utc_now()),
                    str(sanitized.get("selected_backend") or "unknown"),
                    sanitized.get("selected_model_id"),
                    sanitized.get("privacy_level"),
                    sanitized.get("task_difficulty"),
                    sanitized.get("tool_complexity"),
                    sanitized.get("cost_budget_usd"),
                    sanitized.get("latency_budget_ms"),
                    _safe_text(sanitized.get("reason")),
                    sanitized.get("fallback_from"),
                    _bool(sanitized.get("degraded")),
                    _canonical_json(sanitized),
                ),
            )
        return route_id

    def record_artifact(
        self,
        *,
        kind: str,
        path: Path,
        root: Path = PROJECT_ROOT,
        run_id: str | None = None,
        task_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        root = root.resolve()
        requested = path if path.is_absolute() else root / path
        if requested.is_symlink():
            raise ValueError(f"Audit artifacts cannot be symlinks: {path}")
        resolved = requested.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(f"Audit artifact must be a project file: {path}")
        relative = resolved.relative_to(root).as_posix()
        artifact_id = _sha256_bytes(
            f"{run_id or ''}\0{task_key or ''}\0{kind}\0{relative}".encode("utf-8")
        )
        with self.transaction():
            self._connection.execute(
                """
                INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    sha256=excluded.sha256,
                    size_bytes=excluded.size_bytes,
                    mime_type=excluded.mime_type,
                    metadata_json=excluded.metadata_json
                """,
                (
                    artifact_id,
                    run_id,
                    task_key,
                    _safe_text(kind),
                    relative,
                    _sha256_file(resolved),
                    resolved.stat().st_size,
                    _mime_type(resolved),
                    _canonical_json(metadata or {}),
                ),
            )
        return artifact_id

    def get_run_lineage(self, run_id: str) -> dict[str, Any]:
        run = self._row("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        if run is None:
            raise KeyError(f"Unknown run_id: {run_id}")
        return {
            "run": run,
            "task": self._row("SELECT * FROM tasks WHERE task_key = ?", (run["task_key"],)),
            "model": self._row("SELECT * FROM models WHERE model_id = ?", (run["model_id"],)),
            "route_decisions": self._rows(
                "SELECT * FROM route_decisions WHERE run_id = ? ORDER BY timestamp", (run_id,)
            ),
            "tool_calls": self._rows(
                "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY call_index", (run_id,)
            ),
            "scene_checks": self._rows(
                "SELECT * FROM scene_checks WHERE run_id = ? ORDER BY check_index", (run_id,)
            ),
            "assertions": self._rows(
                "SELECT * FROM assertions WHERE run_id = ? ORDER BY assertion_index", (run_id,)
            ),
            "feedback": self._rows(
                "SELECT * FROM feedback WHERE run_id = ? ORDER BY timestamp, feedback_id", (run_id,)
            ),
            "admission": self._row("SELECT * FROM admissions WHERE run_id = ?", (run_id,)),
            "cost_usage": self._row("SELECT * FROM cost_usage WHERE run_id = ?", (run_id,)),
            "artifacts": self._rows(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY kind, path", (run_id,)
            ),
        }

    def summary(self) -> dict[str, Any]:
        model_rows = self._rows(
            """
            SELECT m.provider, m.name AS model, COUNT(*) AS runs,
                   SUM(r.is_golden) AS golden_runs,
                   SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                   ROUND(AVG(r.duration_ms), 2) AS average_duration_ms,
                   SUM(c.total_tokens) AS total_tokens,
                   ROUND(SUM(c.estimated_cost_usd), 6) AS estimated_cost_usd
            FROM runs r
            JOIN models m ON m.model_id = r.model_id
            LEFT JOIN cost_usage c ON c.run_id = r.run_id
            GROUP BY m.model_id
            ORDER BY runs DESC, model
            """
        )
        tags: dict[str, dict[str, int]] = {}
        for row in self._connection.execute(
            "SELECT t.tags_json, r.status, r.is_golden FROM runs r JOIN tasks t ON t.task_key = r.task_key"
        ):
            for tag in json.loads(row["tags_json"]):
                bucket = tags.setdefault(str(tag), {"runs": 0, "golden_runs": 0, "completed": 0})
                bucket["runs"] += 1
                bucket["golden_runs"] += int(row["is_golden"])
                bucket["completed"] += int(row["status"] == "completed")
        return {
            "schema_version": self.schema_version,
            "generated_at": utc_now(),
            "counts": self.table_counts(),
            "by_model": model_rows,
            "by_tag": [{"tag": tag, **values} for tag, values in sorted(tags.items())],
            "by_failure_type": self._rows(
                """
                SELECT COALESCE(failure_type, 'none') AS failure_type, COUNT(*) AS runs
                FROM runs GROUP BY COALESCE(failure_type, 'none') ORDER BY runs DESC
                """
            ),
        }

    @staticmethod
    def export_json(payload: Any, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
        return path

    def table_counts(self) -> dict[str, int]:
        tables = (
            "runs", "tasks", "models", "route_decisions", "tool_calls",
            "scene_checks", "assertions", "feedback", "admissions", "cost_usage",
            "artifacts", "import_batches",
        )
        return {
            table: int(self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }

    def audit(self) -> AuditResult:
        integrity = str(self._connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = [dict(row) for row in self._connection.execute("PRAGMA foreign_key_check")]
        sensitive = self._sensitive_findings()
        lineage = self._golden_lineage_findings()
        return AuditResult(
            passed=integrity == "ok" and not foreign_keys and not sensitive and not lineage,
            schema_version=self.schema_version,
            integrity=integrity,
            foreign_key_findings=foreign_keys,
            sensitive_field_findings=sensitive,
            lineage_findings=lineage,
            counts=self.table_counts(),
        )

    def _sensitive_findings(self) -> list[str]:
        columns = {
            "tasks": ("instruction", "tags_json", "metadata_json"),
            "models": ("metadata_json",),
            "runs": (
                "instruction", "final_text", "messages_json", "events_json",
                "created_object_ids_json", "error_message", "metadata_json",
            ),
            "route_decisions": ("reason", "decision_json"),
            "tool_calls": ("arguments_json", "output"),
            "scene_checks": ("output", "summary_json"),
            "assertions": ("reason", "specification_json"),
            "feedback": ("note", "feedback_json"),
            "admissions": ("reasons_json", "admission_json"),
            "cost_usage": ("usage_json",),
            "artifacts": ("metadata_json",),
            "import_batches": ("summary_json",),
        }
        findings: list[str] = []
        for table, names in columns.items():
            select = ", ".join(("rowid AS audit_rowid", *names))
            for row in self._connection.execute(f"SELECT {select} FROM {table}"):
                for name in names:
                    value = row[name]
                    if value in (None, ""):
                        continue
                    if name.endswith("_json"):
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            findings.append(f"{table}:{row['audit_rowid']}:{name}:invalid_json")
                            continue
                    if contains_sensitive_data(value, parent_key=name):
                        findings.append(f"{table}:{row['audit_rowid']}:{name}:sensitive_data")
        return findings

    def _golden_lineage_findings(self) -> list[str]:
        findings: list[str] = []
        for row in self._connection.execute("SELECT run_id FROM runs WHERE is_golden = 1"):
            run_id = str(row["run_id"])
            lineage = self.get_run_lineage(run_id)
            if not lineage["task"]:
                findings.append(f"{run_id}:missing_task")
            if not lineage["model"]:
                findings.append(f"{run_id}:missing_model")
            if not lineage["assertions"]:
                findings.append(f"{run_id}:missing_assertions")
            if not any(item["label"] == "accepted" for item in lineage["feedback"]):
                findings.append(f"{run_id}:missing_accepted_feedback")
            if not lineage["admission"] or not lineage["admission"]["admitted"]:
                findings.append(f"{run_id}:missing_admission")
            if not lineage["cost_usage"]:
                findings.append(f"{run_id}:missing_cost_usage")
            if not lineage["artifacts"]:
                findings.append(f"{run_id}:missing_evidence")
        return findings

    def _row(self, query: str, parameters: Sequence[Any] = ()) -> dict[str, Any] | None:
        row = self._connection.execute(query, parameters).fetchone()
        return dict(row) if row is not None else None

    def _rows(self, query: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self._connection.execute(query, parameters)]


def _mime_type(path: Path) -> str:
    return {
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
        ".md": "text/markdown",
        ".png": "image/png",
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
    }.get(path.suffix.lower(), "application/octet-stream")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no} must contain a JSON object")
        rows.append(value)
    return rows


def _candidate_task_key(record: dict[str, Any]) -> str | None:
    task = record.get("task") or {}
    campaign_id = str(task.get("campaign_id") or "")
    task_id = str(task.get("task_id") or "")
    return f"{campaign_id}/{task_id}" if campaign_id and task_id else None


def import_golden_dataset(
    database: AuditDatabase,
    *,
    root: Path = PROJECT_ROOT,
    golden_path: Path | None = None,
    expected_count: int = 300,
) -> ImportSummary:
    root = root.resolve()
    golden_path = (golden_path or root / "data" / "golden_traces_v2.jsonl").resolve()
    golden_rows = _read_jsonl(golden_path)
    if len(golden_rows) != expected_count:
        raise ValueError(f"Expected {expected_count} golden rows, found {len(golden_rows)}")
    run_ids = [str(row.get("run_id") or "") for row in golden_rows]
    if "" in run_ids or len(set(run_ids)) != expected_count:
        raise ValueError("Golden run IDs must be present and unique")
    run_id_set = set(run_ids)

    feedback_by_run: dict[str, list[dict[str, Any]]] = {}
    for row in _read_jsonl(root / "data" / "feedback.jsonl"):
        run_id = str(row.get("run_id") or "")
        if run_id in run_id_set:
            feedback_by_run.setdefault(run_id, []).append(row)

    screenshots_by_task: dict[str, set[Path]] = {}
    for row in _read_jsonl(root / "data" / "ai_reviewed_candidates.jsonl"):
        task_key = _candidate_task_key(row)
        evidence = str(
            (((row.get("feedback") or {}).get("review") or {}).get("visual_evidence")) or ""
        )
        if task_key and evidence:
            screenshots_by_task.setdefault(task_key, set()).add(Path(evidence))

    before = database.table_counts()
    with database.transaction():
        for golden in golden_rows:
            run_id = str(golden["run_id"])
            trace_path = root / "data" / "traces" / f"{run_id}.json"
            if not trace_path.is_file():
                raise ValueError(f"Missing source trace for golden run {run_id}")
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            database.ingest_trace(
                trace,
                source_kind="golden_jsonl",
                is_golden=True,
                artifact_path=trace_path,
                artifact_root=root,
            )
            database.mark_golden(golden)
            for feedback in feedback_by_run.get(run_id, []):
                database.ingest_feedback(feedback)
            task_key, _task = _record_task(golden, run_id)
            for screenshot in screenshots_by_task.get(task_key, set()):
                database.record_artifact(
                    kind="screenshot",
                    path=screenshot,
                    root=root,
                    run_id=run_id,
                    task_key=task_key,
                    metadata={"source": "ai_visual_review"},
                )

        global_artifacts = [
            golden_path,
            *sorted((root / "data" / "collection_reports").glob("*")),
            root / "eval" / "collection" / "phase1_30.json",
            root / "eval" / "collection" / "phase2_100.json",
            root / "eval" / "collection" / "phase3_300.json",
        ]
        for artifact in global_artifacts:
            if artifact.is_file():
                database.record_artifact(
                    kind=(
                        "golden_dataset"
                        if artifact == golden_path
                        else "quality_report"
                        if "quality" in artifact.name
                        else "campaign_evidence"
                    ),
                    path=artifact,
                    root=root,
                )

        source_sha = _sha256_file(golden_path)
        import_id = _sha256_bytes(f"{golden_path}\0{source_sha}".encode("utf-8"))
        database._connection.execute(
            """
            INSERT INTO import_batches VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(import_id) DO NOTHING
            """,
            (
                import_id,
                golden_path.relative_to(root).as_posix(),
                source_sha,
                utc_now(),
                len(golden_rows),
                _canonical_json({"expected_count": expected_count}),
            ),
        )
        audit = database.audit()
        if audit.sensitive_field_findings or audit.lineage_findings:
            raise ValueError(
                "Audit database validation failed: "
                f"sensitive={audit.sensitive_field_findings[:5]}, "
                f"lineage={audit.lineage_findings[:5]}"
            )

    after = database.table_counts()
    golden_runs = int(
        database._connection.execute("SELECT COUNT(*) FROM runs WHERE is_golden = 1").fetchone()[0]
    )
    golden_tasks = int(
        database._connection.execute(
            "SELECT COUNT(DISTINCT task_key) FROM runs WHERE is_golden = 1"
        ).fetchone()[0]
    )
    if golden_runs != expected_count or golden_tasks != expected_count:
        raise ValueError(
            f"SQLite/JSONL mismatch: runs={golden_runs}, tasks={golden_tasks}, JSONL={expected_count}"
        )
    repeated = before["import_batches"] > 0
    return ImportSummary(
        source_path=golden_path.relative_to(root).as_posix(),
        source_sha256=_sha256_file(golden_path),
        source_rows=len(golden_rows),
        golden_runs=golden_runs,
        golden_tasks=golden_tasks,
        tool_calls=after["tool_calls"],
        scene_checks=after["scene_checks"],
        assertions=after["assertions"],
        feedback=after["feedback"],
        admissions=after["admissions"],
        cost_usage=after["cost_usage"],
        artifacts=after["artifacts"],
        counts_unchanged_on_repeat=(not repeated or before == after),
        sensitive_field_findings=0,
        lineage_findings=0,
    )


def configured_audit_path() -> Path:
    return Path(os.environ.get("RHINOCODER_AUDIT_DB", DEFAULT_AUDIT_DB)).expanduser().resolve()


def audit_writes_enabled() -> bool:
    return os.environ.get("RHINOCODER_AUDIT_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def record_live_trace(record: dict[str, Any], *, artifact_path: Path | None = None) -> None:
    if not audit_writes_enabled():
        return
    try:
        with AuditDatabase(configured_audit_path()) as database:
            database.ingest_trace(record, artifact_path=artifact_path)
    except Exception as exc:
        logger.warning(
            "SQLite audit trace write failed for %s: %s",
            record.get("run_id"),
            sanitize_for_log(str(exc)),
        )


def record_live_feedback(record: dict[str, Any]) -> None:
    if not audit_writes_enabled():
        return
    try:
        with AuditDatabase(configured_audit_path()) as database:
            database.ingest_feedback(record)
    except Exception as exc:
        logger.warning(
            "SQLite audit feedback write failed for %s: %s",
            record.get("run_id"),
            sanitize_for_log(str(exc)),
        )


def record_live_golden(record: dict[str, Any]) -> None:
    if not audit_writes_enabled():
        return
    try:
        with AuditDatabase(configured_audit_path()) as database:
            database.mark_golden(record)
    except Exception as exc:
        logger.warning(
            "SQLite audit golden write failed for %s: %s",
            record.get("run_id"),
            sanitize_for_log(str(exc)),
        )
