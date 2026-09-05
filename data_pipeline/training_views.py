"""Deterministic, lineage-preserving A5 training-view export and audit."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from agent.privacy import cloud_sensitive_findings, minimize_for_cloud, minimize_text_for_cloud


PIPELINE_VERSION = "a5-training-views-v1"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPLIT_SEED = "rhinocoder-a5-v1"
SPLITS = ("train", "validation", "holdout")
SPLIT_RATIOS = {"train": 0.70, "validation": 0.15, "holdout": 0.15}
VIEWS = (
    "instruction_to_tool_call",
    "full_trajectory",
    "error_to_correction",
    "scene_to_next_step",
)
VIEW_MAX_CHARS = {
    "instruction_to_tool_call": 8_192,
    "full_trajectory": 16_384,
    "error_to_correction": 12_288,
    "scene_to_next_step": 12_288,
}
DEFAULT_SOURCE = Path("data/golden_traces_v2.jsonl")
DEFAULT_OUTPUT = Path("data/training/a5")
DEFAULT_CAMPAIGN_MANIFEST = Path("eval/collection/phase3_300.json")
ERROR_MARKERS = (
    "参数错误",
    "执行失败",
    "调用失败",
    "失败 [",
    "失败：",
    "异常",
    "超时",
    "invalid",
    "not found",
    "error",
    "timeout",
)
NUMERIC_RE = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?")
GUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
REDACTED_LABEL_PATTERNS = (
    (
        re.compile(
            r"(?i)(?:图层|layer(?:[_ ]?name)?)[\s:：=「」『』'\"`]{0,12}"
            r"<LAYER_REDACTED>[」』'\"`]*"
        ),
        "<LAYER_REDACTED>",
    ),
    (
        re.compile(
            r"(?i)(?:群组|group(?:[_ ]?name)?s?)[\s:：=「」『』'\"`]{0,12}"
            r"<GROUP_REDACTED>[」』'\"`]*"
        ),
        "<GROUP_REDACTED>",
    ),
)


class TrainingDataError(RuntimeError):
    """Raised when source or output invariants would make an export unsafe."""


@dataclass(frozen=True, slots=True)
class BuildConfig:
    split_seed: str = SPLIT_SEED
    split_ratios: Mapping[str, float] = field(default_factory=lambda: dict(SPLIT_RATIOS))
    view_max_chars: Mapping[str, int] = field(default_factory=lambda: dict(VIEW_MAX_CHARS))


@dataclass(slots=True)
class AuditResult:
    passed: bool = True
    source_tasks: int = 0
    samples: int = 0
    artifacts: int = 0
    duplicate_samples: int = 0
    template_leaks: int = 0
    numeric_template_leaks: int = 0
    lineage_failures: int = 0
    privacy_findings: int = 0
    findings: list[str] = field(default_factory=list)

    def add(self, finding: str) -> None:
        self.findings.append(finding)
        self.passed = False


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _read_jsonl_with_lines(path: Path) -> list[tuple[int, dict[str, Any]]]:
    if not path.is_file():
        raise TrainingDataError(f"source JSONL does not exist: {path}")
    rows: list[tuple[int, dict[str, Any]]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TrainingDataError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise TrainingDataError(f"{path}:{line_no}: row must be an object")
        rows.append((line_no, value))
    return rows


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [row for _line_no, row in _read_jsonl_with_lines(path)]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(_canonical_bytes(row).decode("utf-8") + "\n")


def numeric_template_signature(instruction: str) -> str:
    """Normalize only values that commonly produce trivial task variants."""

    normalized = instruction.strip().lower()
    normalized = GUID_RE.sub("<guid>", normalized)
    normalized = NUMERIC_RE.sub("<n>", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _source_task(trace: Mapping[str, Any], line_no: int) -> dict[str, Any]:
    metadata = trace.get("metadata")
    task = metadata.get("task") if isinstance(metadata, dict) else None
    if not isinstance(task, dict):
        raise TrainingDataError(f"source line {line_no}: metadata.task is missing")
    task_id = str(task.get("task_id") or "").strip()
    campaign_id = str(task.get("campaign_id") or "").strip()
    if not task_id or not campaign_id:
        raise TrainingDataError(f"source line {line_no}: task lineage is incomplete")
    return task


def _first_user_instruction(trace: Mapping[str, Any], line_no: int) -> str:
    for message in trace.get("messages") or []:
        if isinstance(message, dict) and message.get("role") == "user":
            content = str(message.get("content") or "").strip()
            if content:
                return content
    raise TrainingDataError(f"source line {line_no}: user instruction is missing")


def _walk_named_literals(value: Any, found: dict[str, set[str]], parent_key: str = "") -> None:
    key = parent_key.lower()
    if key in {"layer", "layer_name", "project_layer"} and isinstance(value, str):
        if value and value != "Default" and not value.startswith("<"):
            found["layer"].add(value)
    if key in {"group", "groups", "group_name", "group_names", "in_group"}:
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and item and not item.startswith("<"):
                found["group"].add(item)
    if isinstance(value, dict):
        for child_key, item in value.items():
            if str(child_key).lower() == "arguments" and isinstance(item, str):
                try:
                    decoded = json.loads(item)
                except json.JSONDecodeError:
                    pass
                else:
                    _walk_named_literals(decoded, found)
            _walk_named_literals(item, found, str(child_key))
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk_named_literals(item, found, parent_key)


def _sensitive_literals(trace: Mapping[str, Any], task_definition: Mapping[str, Any]) -> dict[str, set[str]]:
    found = {"layer": set(), "group": set()}
    _walk_named_literals(trace, found)
    _walk_named_literals(task_definition.get("asserts") or [], found)
    return found


def _replace_literals(text: str, literals: Mapping[str, set[str]]) -> str:
    for kind, replacement in (("layer", "<LAYER_REDACTED>"), ("group", "<GROUP_REDACTED>")):
        for literal in sorted(literals.get(kind, set()), key=lambda item: (-len(item), item)):
            text = text.replace(literal, replacement)
    return text


def _clean_text(text: Any, literals: Mapping[str, set[str]]) -> str:
    value = _replace_literals(str(text or ""), literals)
    value = minimize_text_for_cloud(value)
    for pattern, replacement in REDACTED_LABEL_PATTERNS:
        value = pattern.sub(replacement, value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _clean_arguments(raw: Any, literals: Mapping[str, set[str]]) -> tuple[str, int]:
    repaired = 0
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            repaired_raw = re.sub(
                r'(?<!["\w])(<(?:COORD|GUID)_REDACTED>)(?!["\w])',
                r'"\1"',
                raw,
            )
            try:
                value = json.loads(repaired_raw)
            except json.JSONDecodeError as exc:
                raise TrainingDataError(f"tool arguments are not recoverable JSON: {raw[:160]!r}") from exc
            repaired = 1
    else:
        value = raw
    value = minimize_for_cloud(value)
    return _canonical_bytes(value).decode("utf-8"), repaired


def clean_messages(
    messages: Sequence[Mapping[str, Any]],
    *,
    instruction: str,
    literals: Mapping[str, set[str]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Remove reasoning/runtime noise and normalize transient call IDs."""

    cleaned: list[dict[str, Any]] = []
    call_ids: dict[str, str] = {}
    next_call = 1
    removed_fields = 0
    repaired_arguments = 0
    user_replaced = False
    allowed = {"role", "content", "tool_calls", "tool_call_id", "name"}
    for raw in messages:
        if not isinstance(raw, Mapping):
            continue
        role = str(raw.get("role") or "")
        removed_fields += len(set(raw).difference(allowed))
        if role == "system":
            removed_fields += len(raw)
            continue
        if role not in {"user", "assistant", "tool"}:
            removed_fields += len(raw)
            continue
        message: dict[str, Any] = {"role": role}
        if role == "user" and not user_replaced:
            message["content"] = instruction
            user_replaced = True
        else:
            content = _clean_text(raw.get("content"), literals)
            if content or role == "tool":
                message["content"] = content
        if raw.get("name"):
            message["name"] = str(raw["name"])
        tool_calls = raw.get("tool_calls")
        if isinstance(tool_calls, list):
            normalized_calls: list[dict[str, Any]] = []
            for call in tool_calls:
                if not isinstance(call, Mapping):
                    continue
                function = call.get("function") or {}
                if not isinstance(function, Mapping) or not function.get("name"):
                    continue
                original_id = str(call.get("id") or f"missing-{next_call}")
                if original_id not in call_ids:
                    call_ids[original_id] = f"call_{next_call:03d}"
                    next_call += 1
                normalized_id = call_ids[original_id]
                arguments, repaired = _clean_arguments(function.get("arguments") or {}, literals)
                repaired_arguments += repaired
                normalized_calls.append(
                    {
                        "id": normalized_id,
                        "type": "function",
                        "function": {
                            "name": str(function["name"]),
                            "arguments": arguments,
                        },
                    }
                )
            if normalized_calls:
                message["tool_calls"] = normalized_calls
        if role == "tool":
            original_id = str(raw.get("tool_call_id") or "")
            if original_id:
                if original_id not in call_ids:
                    call_ids[original_id] = f"call_{next_call:03d}"
                    next_call += 1
                message["tool_call_id"] = call_ids[original_id]
        if len(message) > 1:
            cleaned.append(message)
    if not user_replaced:
        cleaned.insert(0, {"role": "user", "content": instruction})
    return cleaned, removed_fields, repaired_arguments


def _message_chars(messages: Sequence[Mapping[str, Any]]) -> int:
    return len(_canonical_bytes(messages).decode("utf-8"))


def _is_tool_error(message: Mapping[str, Any]) -> bool:
    if message.get("role") != "tool":
        return False
    text = str(message.get("content") or "").lower()
    return any(marker.lower() in text for marker in ERROR_MARKERS)


def _tool_name_by_call(messages: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for message in messages:
        for call in message.get("tool_calls") or []:
            if isinstance(call, Mapping):
                function = call.get("function") or {}
                names[str(call.get("id") or "")] = str(function.get("name") or "")
    return names


def _preceding_call(messages: Sequence[dict[str, Any]], index: int, call_id: str) -> dict[str, Any] | None:
    for message in reversed(messages[:index]):
        if any(call.get("id") == call_id for call in message.get("tool_calls") or []):
            return message
    return None


def _next_assistant(messages: Sequence[dict[str, Any]], index: int) -> dict[str, Any] | None:
    for message in messages[index + 1 :]:
        if message.get("role") == "assistant" and (message.get("tool_calls") or message.get("content")):
            return message
    return None


def _view_message_sets(messages: list[dict[str, Any]]) -> dict[str, list[list[dict[str, Any]]]]:
    user = next((message for message in messages if message.get("role") == "user"), None)
    first_tool_plan = next(
        (message for message in messages if message.get("role") == "assistant" and message.get("tool_calls")),
        None,
    )
    result: dict[str, list[list[dict[str, Any]]]] = {view: [] for view in VIEWS}
    if user and first_tool_plan:
        result["instruction_to_tool_call"].append([user, first_tool_plan])
    if user and messages:
        result["full_trajectory"].append(messages)

    call_names = _tool_name_by_call(messages)
    for index, message in enumerate(messages):
        if message.get("role") != "tool":
            continue
        call_id = str(message.get("tool_call_id") or "")
        call = _preceding_call(messages, index, call_id)
        target = _next_assistant(messages, index)
        if not user or not call or not target:
            continue
        if _is_tool_error(message):
            result["error_to_correction"].append([user, call, message, target])
        if call_names.get(call_id) == "get_scene_summary":
            result["scene_to_next_step"].append([user, call, message, target])
    return result


class _DisjointSet:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)


def _template_groups(tasks: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    ids = [task["task_id"] for task in tasks]
    dsu = _DisjointSet(ids)
    semantic_owner: dict[tuple[str, tuple[str, ...]], str] = {}
    numeric_owner: dict[str, str] = {}
    numeric_ids: dict[str, str] = {}
    for task in tasks:
        task_id = task["task_id"]
        semantic = (task["campaign_id"], tuple(sorted(task["tags"])))
        numeric = numeric_template_signature(task["instruction"])
        numeric_ids[task_id] = _stable_hash(numeric)[:16]
        for mapping, key in ((semantic_owner, semantic), (numeric_owner, numeric)):
            owner = mapping.setdefault(key, task_id)
            dsu.union(task_id, owner)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped[dsu.find(task["task_id"])].append(task)
    groups: list[dict[str, Any]] = []
    task_templates: dict[str, str] = {}
    for members in grouped.values():
        task_ids = sorted(member["task_id"] for member in members)
        template_id = "tpl_" + _stable_hash("\n".join(task_ids))[:16]
        tag_counts = Counter(tag for member in members for tag in member["split_labels"])
        groups.append(
            {
                "template_id": template_id,
                "task_ids": task_ids,
                "size": len(members),
                "tag_counts": dict(sorted(tag_counts.items())),
            }
        )
        for task_id in task_ids:
            task_templates[task_id] = template_id
    return groups, task_templates, numeric_ids


def _split_targets(total: int, ratios: Mapping[str, float]) -> dict[str, int]:
    if set(ratios) != set(SPLITS) or abs(sum(ratios.values()) - 1.0) > 1e-9:
        raise TrainingDataError("split ratios must define train/validation/holdout and sum to 1")
    train = int(total * ratios["train"])
    validation = int(total * ratios["validation"])
    return {"train": train, "validation": validation, "holdout": total - train - validation}


def _assign_splits(
    groups: Sequence[dict[str, Any]],
    *,
    targets: Mapping[str, int],
    seed: str,
    locked_tasks: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    locked_tasks = locked_tasks or {}
    total_tasks = sum(group["size"] for group in groups)
    global_tag_counts = Counter(
        {
            tag: sum(group["tag_counts"].get(tag, 0) for group in groups)
            for tag in {tag for group in groups for tag in group["tag_counts"]}
        }
    )
    counts = Counter({split: 0 for split in SPLITS})
    tag_counts: dict[str, Counter[str]] = {split: Counter() for split in SPLITS}
    assignments: dict[str, str] = {}
    task_splits: dict[str, str] = {}
    pending: list[dict[str, Any]] = []

    ordered = sorted(
        groups,
        key=lambda group: (
            -int(any(tag.startswith("view:") for tag in group["tag_counts"])),
            -max(
                (
                    amount / group["size"]
                    for tag, amount in group["tag_counts"].items()
                    if tag.startswith("view:")
                ),
                default=0.0,
            ),
            -group["size"],
            _stable_hash(seed + group["template_id"]),
        ),
    )
    for group in ordered:
        locked = {locked_tasks[task_id] for task_id in group["task_ids"] if task_id in locked_tasks}
        if len(locked) > 1:
            raise TrainingDataError(
                f"template {group['template_id']} joins previously separated locked splits: {sorted(locked)}"
            )
        if locked:
            split = next(iter(locked))
            if split not in SPLITS:
                raise TrainingDataError(f"invalid locked split {split!r}")
            assignments[group["template_id"]] = split
            counts[split] += group["size"]
            tag_counts[split].update(group["tag_counts"])
        else:
            pending.append(group)

    for group in pending:
        candidates = [split for split in SPLITS if counts[split] + group["size"] <= targets[split]]
        if not candidates:
            candidates = list(SPLITS)

        def score(split: str) -> tuple[float, str]:
            target = max(targets[split], 1)
            fill = (counts[split] + group["size"]) / target
            tag_fill: list[float] = []
            for tag, amount in group["tag_counts"].items():
                desired = max(global_tag_counts[tag] * target / max(total_tasks, 1), 0.25)
                tag_fill.append((tag_counts[split][tag] + amount) / desired)
            balance = sum(tag_fill) / len(tag_fill) if tag_fill else 0.0
            view_fill = [
                fill_value
                for tag, fill_value in zip(group["tag_counts"], tag_fill, strict=True)
                if tag.startswith("view:")
            ]
            view_balance = sum(view_fill) / len(view_fill) if view_fill else 0.0
            tie = _stable_hash(f"{seed}:{group['template_id']}:{split}")
            return fill + 0.20 * balance + 1.50 * view_balance, tie

        split = min(candidates, key=score)
        assignments[group["template_id"]] = split
        counts[split] += group["size"]
        tag_counts[split].update(group["tag_counts"])

    for group in groups:
        split = assignments[group["template_id"]]
        for task_id in group["task_ids"]:
            task_splits[task_id] = split
    return assignments, task_splits


def _sample(
    *,
    view: str,
    ordinal: int,
    messages: list[dict[str, Any]],
    task: Mapping[str, Any],
    trace: Mapping[str, Any],
    source_line: int,
    source_path: str,
    split: str,
    template_id: str,
    numeric_template_id: str,
    task_sha256: str,
) -> dict[str, Any]:
    run_id = str(trace.get("run_id") or "")
    sample_id = "sample_" + _stable_hash(f"{run_id}:{view}:{ordinal}")[:24]
    trace_sha = _sha256_bytes(_canonical_bytes(trace))
    return {
        "schema_version": "1.0",
        "sample_id": sample_id,
        "view": view,
        "view_ordinal": ordinal,
        "split": split,
        "template_id": template_id,
        "numeric_template_id": numeric_template_id,
        "tags": list(task["tags"]),
        "difficulty": task["difficulty"],
        "messages": messages,
        "target_message_index": len(messages) - 1,
        "lineage": {
            "source_path": source_path,
            "source_line": source_line,
            "trace_sha256": trace_sha,
            "run_id": run_id,
            "campaign_id": task["campaign_id"],
            "task_id": task["task_id"],
            "task_sha256": task_sha256,
            "prompt_version": (trace.get("metadata") or {}).get("prompt_version"),
            "tool_schema_version": (trace.get("metadata") or {}).get("tool_schema_version"),
        },
    }


def _old_split_lock(output_dir: Path) -> dict[str, str]:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if manifest.get("pipeline_version") != PIPELINE_VERSION:
        return {}
    mapping = manifest.get("task_splits") or {}
    return {str(key): str(value) for key, value in mapping.items() if str(value) in SPLITS}


def build_training_dataset(
    source_path: Path,
    output_dir: Path,
    *,
    task_catalog: Mapping[str, Mapping[str, Any]] | None = None,
    campaign_manifest_path: Path | None = None,
    config: BuildConfig | None = None,
) -> dict[str, Any]:
    config = config or BuildConfig()
    source_path = source_path.resolve()
    output_dir = output_dir.resolve()
    source_records = _read_jsonl_with_lines(source_path)
    traces = [trace for _line_no, trace in source_records]
    if not traces:
        raise TrainingDataError("golden source is empty")

    tasks: list[dict[str, Any]] = []
    seen_runs: set[str] = set()
    seen_tasks: set[str] = set()
    prepared: list[tuple[int, dict[str, Any], dict[str, Any], dict[str, set[str]]]] = []
    for line_no, trace in source_records:
        if trace.get("schema_version") != "1.0" or not isinstance(trace.get("messages"), list):
            raise TrainingDataError(f"source line {line_no}: unsupported schema or messages")
        run_id = str(trace.get("run_id") or "").strip()
        if not run_id or run_id in seen_runs:
            raise TrainingDataError(f"source line {line_no}: run_id is missing or duplicated")
        seen_runs.add(run_id)
        source_task = _source_task(trace, line_no)
        task_id = str(source_task["task_id"])
        if task_id in seen_tasks:
            raise TrainingDataError(f"source line {line_no}: task_id {task_id!r} is duplicated")
        seen_tasks.add(task_id)
        if task_catalog is not None and task_id not in task_catalog:
            raise TrainingDataError(f"source line {line_no}: task {task_id!r} is missing from campaign")
        definition = dict((task_catalog or {}).get(task_id) or {})
        instruction = str(definition.get("instruction") or _first_user_instruction(trace, line_no))
        tags = list(definition.get("tags") or source_task.get("tags") or [])
        difficulty = int(definition.get("difficulty") or source_task.get("difficulty") or 0)
        task = {
            "task_id": task_id,
            "campaign_id": str(source_task["campaign_id"]),
            "instruction": instruction,
            "tags": sorted({str(tag) for tag in tags if str(tag)}),
            "difficulty": difficulty,
        }
        if not task["tags"] or not 1 <= difficulty <= 5:
            raise TrainingDataError(f"source line {line_no}: invalid tags or difficulty")
        literals = _sensitive_literals(trace, definition)
        task["instruction"] = _clean_text(instruction, literals)
        split_labels = {*task["tags"], f"difficulty:{difficulty}"}
        if any(_is_tool_error(message) for message in trace.get("messages") or [] if isinstance(message, Mapping)):
            split_labels.add("view:error_to_correction")
        task["split_labels"] = sorted(split_labels)
        tasks.append(task)
        prepared.append((line_no, trace, task, literals))

    groups, task_templates, numeric_ids = _template_groups(tasks)
    targets = _split_targets(len(tasks), config.split_ratios)
    template_splits, task_splits = _assign_splits(
        groups,
        targets=targets,
        seed=config.split_seed,
        locked_tasks=_old_split_lock(output_dir),
    )
    actual_counts = Counter(task_splits.values())
    if dict(actual_counts) != targets:
        raise TrainingDataError(f"cannot satisfy exact split targets: actual={dict(actual_counts)} target={targets}")

    output_rows: dict[tuple[str, str], list[dict[str, Any]]] = {
        (split, view): [] for split in SPLITS for view in VIEWS
    }
    fingerprints: dict[str, set[str]] = {view: set() for view in VIEWS}
    duplicate_drops = Counter()
    length_drops = Counter()
    noise_fields_removed = 0
    repaired_tool_arguments = 0
    source_relative = _portable_path(source_path)
    task_fingerprints = {
        task["task_id"]: _sha256_bytes(_canonical_bytes(task)) for task in tasks
    }

    for line_no, trace, task, literals in prepared:
        messages, removed, repaired = clean_messages(
            trace.get("messages") or [],
            instruction=task["instruction"],
            literals=literals,
        )
        noise_fields_removed += removed
        repaired_tool_arguments += repaired
        views = _view_message_sets(messages)
        split = task_splits[task["task_id"]]
        for view in VIEWS:
            for ordinal, view_messages in enumerate(views[view], 1):
                if _message_chars(view_messages) > config.view_max_chars[view]:
                    length_drops[view] += 1
                    continue
                fingerprint = _sha256_bytes(_canonical_bytes({"view": view, "messages": view_messages}))
                if fingerprint in fingerprints[view]:
                    duplicate_drops[view] += 1
                    continue
                fingerprints[view].add(fingerprint)
                output_rows[(split, view)].append(
                    _sample(
                        view=view,
                        ordinal=ordinal,
                        messages=view_messages,
                        task=task,
                        trace=trace,
                        source_line=line_no,
                        source_path=source_relative,
                        split=split,
                        template_id=task_templates[task["task_id"]],
                        numeric_template_id=numeric_ids[task["task_id"]],
                        task_sha256=task_fingerprints[task["task_id"]],
                    )
                )

    for rows in output_rows.values():
        rows.sort(key=lambda row: (row["lineage"]["task_id"], row["view"], row["sample_id"]))
    view_counts = {
        split: {view: len(output_rows[(split, view)]) for view in VIEWS}
        for split in SPLITS
    }
    all_samples = [row for rows in output_rows.values() for row in rows]
    stats = {
        "source_tasks": len(tasks),
        "template_groups": len(groups),
        "split_task_counts": dict(sorted(actual_counts.items())),
        "view_counts": view_counts,
        "total_samples": len(all_samples),
        "noise_fields_removed": noise_fields_removed,
        "repaired_tool_arguments": repaired_tool_arguments,
        "duplicate_samples_dropped": dict(sorted(duplicate_drops.items())),
        "samples_dropped_by_length": dict(sorted(length_drops.items())),
        "max_sample_chars": max((_message_chars(row["messages"]) for row in all_samples), default=0),
        "tag_distribution": {
            split: dict(
                sorted(
                    Counter(
                        tag
                        for task in tasks
                        if task_splits[task["task_id"]] == split
                        for tag in task["tags"]
                    ).items()
                )
            )
            for split in SPLITS
        },
        "stratification_distribution": {
            split: dict(
                sorted(
                    Counter(
                        label
                        for task in tasks
                        if task_splits[task["task_id"]] == split
                        for label in task["split_labels"]
                    ).items()
                )
            )
            for split in SPLITS
        },
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".a5-build-", dir=output_dir.parent) as temporary:
        staging = Path(temporary) / "dataset"
        for split in SPLITS:
            for view in VIEWS:
                _write_jsonl(staging / split / f"{view}.jsonl", output_rows[(split, view)])
        _write_json(staging / "stats.json", stats)
        artifacts = []
        for path in sorted(staging.glob("**/*")):
            if path.is_file():
                artifacts.append(
                    {
                        "path": path.relative_to(staging).as_posix(),
                        "sha256": _sha256_file(path),
                        "bytes": path.stat().st_size,
                        "rows": (
                            sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line)
                            if path.suffix == ".jsonl"
                            else None
                        ),
                    }
                )
        manifest = {
            "schema_version": "1.0",
            "pipeline_version": PIPELINE_VERSION,
            "split_seed": config.split_seed,
            "split_ratios": dict(config.split_ratios),
            "split_targets": targets,
            "holdout_policy": "locked_never_train",
            "view_max_chars": dict(config.view_max_chars),
            "source": {
                "path": source_relative,
                "sha256": _sha256_file(source_path),
                "rows": len(traces),
                "campaign_manifest": _portable_path(campaign_manifest_path) if campaign_manifest_path else None,
                "campaign_manifest_sha256": (
                    _sha256_file(campaign_manifest_path) if campaign_manifest_path else None
                ),
            },
            "stats": stats,
            "task_splits": dict(sorted(task_splits.items())),
            "task_fingerprints": dict(sorted(task_fingerprints.items())),
            "template_assignments": {
                group["template_id"]: {
                    "split": template_splits[group["template_id"]],
                    "task_ids": group["task_ids"],
                }
                for group in sorted(groups, key=lambda item: item["template_id"])
            },
            "artifacts": artifacts,
        }
        _write_json(staging / "manifest.json", manifest)
        staged_audit = audit_training_dataset(staging, source_path)
        if not staged_audit.passed:
            raise TrainingDataError("staged export audit failed: " + "; ".join(staged_audit.findings[:10]))
        backup = output_dir.with_name(output_dir.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if output_dir.exists():
            output_dir.rename(backup)
        try:
            shutil.move(str(staging), str(output_dir))
        except Exception:
            if backup.exists() and not output_dir.exists():
                backup.rename(output_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    return manifest


def audit_training_dataset(output_dir: Path, source_path: Path) -> AuditResult:
    output_dir = output_dir.resolve()
    source_path = source_path.resolve()
    result = AuditResult()
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        result.add("manifest.json is missing")
        return result
    if manifest_path.is_symlink():
        result.add("symlinked manifest is not allowed")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.add(f"manifest.json is invalid: {exc}")
        return result
    if manifest.get("pipeline_version") != PIPELINE_VERSION:
        result.add("pipeline_version does not match")
    if manifest.get("holdout_policy") != "locked_never_train":
        result.add("holdout policy is not locked")
    try:
        expected_targets = _split_targets(result.source_tasks or manifest.get("source", {}).get("rows", 0), manifest["split_ratios"])
    except (KeyError, TypeError, TrainingDataError) as exc:
        result.add(f"split configuration is invalid: {exc}")
    else:
        if expected_targets != manifest.get("split_targets"):
            result.add("split targets do not match source size and ratios")
    if not source_path.is_file() or manifest.get("source", {}).get("sha256") != _sha256_file(source_path):
        result.add("source hash does not match manifest")
        return result
    if manifest.get("source", {}).get("path") != _portable_path(source_path):
        result.add("source path does not match manifest")
    campaign_value = manifest.get("source", {}).get("campaign_manifest")
    if campaign_value:
        campaign_path = Path(str(campaign_value))
        if not campaign_path.is_absolute():
            campaign_path = PROJECT_ROOT / campaign_path
        expected_campaign_hash = manifest.get("source", {}).get("campaign_manifest_sha256")
        if not campaign_path.is_file() or _sha256_file(campaign_path) != expected_campaign_hash:
            result.add("campaign manifest hash does not match")
    source_records = _read_jsonl_with_lines(source_path)
    source_rows = [row for _line_no, row in source_records]
    result.source_tasks = len(source_rows)
    if manifest.get("source", {}).get("rows") != len(source_rows):
        result.add("source row count does not match manifest")
    if manifest.get("stats", {}).get("source_tasks") != len(source_rows):
        result.add("source task count does not match stats")
    lineage: dict[str, tuple[int, str]] = {}
    for line_no, row in source_records:
        task = _source_task(row, line_no)
        lineage[str(task["task_id"])] = (line_no, _sha256_bytes(_canonical_bytes(row)))

    expected_artifacts = {
        *(f"{split}/{view}.jsonl" for split in SPLITS for view in VIEWS),
        "stats.json",
    }
    artifacts = manifest.get("artifacts") or []
    declared_artifacts = [str(item.get("path") or "") for item in artifacts]
    if len(declared_artifacts) != len(set(declared_artifacts)):
        result.add("manifest contains duplicate artifact paths")
    if set(declared_artifacts) != expected_artifacts:
        result.add(
            "artifact inventory mismatch: "
            f"declared={sorted(declared_artifacts)} expected={sorted(expected_artifacts)}"
        )
    actual_artifacts = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.glob("**/*")
        if path.is_file() and path != manifest_path
    }
    if actual_artifacts != expected_artifacts:
        result.add(
            f"output inventory mismatch: actual={sorted(actual_artifacts)} "
            f"expected={sorted(expected_artifacts)}"
        )
    stats_path = output_dir / "stats.json"
    if stats_path.is_file():
        try:
            stats_file = json.loads(stats_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.add(f"stats.json is invalid: {exc}")
        else:
            if stats_file != manifest.get("stats"):
                result.add("stats.json does not match manifest stats")

    sample_ids: set[str] = set()
    fingerprints: dict[str, set[str]] = defaultdict(set)
    template_splits: dict[str, set[str]] = defaultdict(set)
    numeric_splits: dict[str, set[str]] = defaultdict(set)
    task_observed_splits: dict[str, set[str]] = defaultdict(set)
    task_views: dict[str, set[str]] = defaultdict(set)
    observed_counts: Counter[str] = Counter()
    observed_views: dict[str, Counter[str]] = {split: Counter() for split in SPLITS}
    declared_task_templates: dict[str, str] = {}
    for template_id, assignment in (manifest.get("template_assignments") or {}).items():
        for task_id in assignment.get("task_ids") or []:
            if task_id in declared_task_templates:
                result.add(f"task appears in multiple template assignments: {task_id}")
            declared_task_templates[task_id] = template_id
    for artifact in artifacts:
        relative = str(artifact.get("path") or "")
        candidate = output_dir / relative
        path = candidate.resolve()
        if not path.is_relative_to(output_dir) or not path.is_file():
            result.add(f"artifact is missing or escapes output: {relative}")
            continue
        if candidate.is_symlink():
            result.add(f"symlinked artifact is not allowed: {relative}")
        result.artifacts += 1
        if artifact.get("sha256") != _sha256_file(path) or artifact.get("bytes") != path.stat().st_size:
            result.add(f"artifact hash/size mismatch: {relative}")
        if path.suffix != ".jsonl":
            continue
        rows = _read_jsonl(path)
        if artifact.get("rows") != len(rows):
            result.add(f"artifact row count mismatch: {relative}")
        for row in rows:
            result.samples += 1
            sample_id = str(row.get("sample_id") or "")
            if not sample_id or sample_id in sample_ids:
                result.duplicate_samples += 1
                result.add(f"duplicate sample_id: {sample_id}")
            sample_ids.add(sample_id)
            view, split = str(row.get("view") or ""), str(row.get("split") or "")
            if view not in VIEWS or split not in SPLITS or relative != f"{split}/{view}.jsonl":
                result.add(f"sample location/view mismatch: {sample_id}")
                continue
            observed_counts[split] += 1 if view == "full_trajectory" else 0
            observed_views[split][view] += 1
            messages = row.get("messages") or []
            if not isinstance(messages, list) or not messages:
                result.add(f"sample messages are empty: {sample_id}")
                continue
            if row.get("target_message_index") != len(messages) - 1:
                result.add(f"target_message_index mismatch: {sample_id}")
            ordinal = row.get("view_ordinal")
            run_id = str((row.get("lineage") or {}).get("run_id") or "")
            if not isinstance(ordinal, int) or ordinal < 1 or sample_id != "sample_" + _stable_hash(
                f"{run_id}:{view}:{ordinal}"
            )[:24]:
                result.add(f"sample identity mismatch: {sample_id}")
            if _message_chars(messages) > int(manifest["view_max_chars"][view]):
                result.add(f"sample exceeds length budget: {sample_id}")
            allowed_message_fields = {"role", "content", "tool_calls", "tool_call_id", "name"}
            known_calls: set[str] = set()
            for message in messages:
                if not isinstance(message, dict):
                    result.add(f"non-object message retained: {sample_id}")
                    continue
                unexpected = set(message).difference(allowed_message_fields)
                if unexpected:
                    result.add(f"runtime message fields retained in {sample_id}: {sorted(unexpected)}")
                for call in message.get("tool_calls") or []:
                    call_id = str(call.get("id") or "")
                    if not re.fullmatch(r"call_\d{3}", call_id):
                        result.add(f"non-normalized call ID in {sample_id}: {call_id}")
                    known_calls.add(call_id)
                    arguments = ((call.get("function") or {}).get("arguments"))
                    try:
                        json.loads(arguments)
                    except (TypeError, json.JSONDecodeError):
                        result.add(f"invalid tool arguments JSON in {sample_id}: {call_id}")
                if message.get("role") == "tool" and message.get("tool_call_id") not in known_calls:
                    result.add(f"orphaned tool result in {sample_id}: {message.get('tool_call_id')}")
            privacy = cloud_sensitive_findings(messages)
            if privacy:
                result.privacy_findings += len(privacy)
                result.add(f"privacy finding in {sample_id}: {privacy[:3]}")
            fingerprint = _sha256_bytes(_canonical_bytes({"view": view, "messages": messages}))
            if fingerprint in fingerprints[view]:
                result.duplicate_samples += 1
                result.add(f"duplicate content in {view}: {sample_id}")
            fingerprints[view].add(fingerprint)
            item_lineage = row.get("lineage") or {}
            task_id = str(item_lineage.get("task_id") or "")
            expected = lineage.get(task_id)
            if (
                expected is None
                or item_lineage.get("source_line") != expected[0]
                or item_lineage.get("trace_sha256") != expected[1]
                or item_lineage.get("task_sha256")
                != (manifest.get("task_fingerprints") or {}).get(task_id)
                or not item_lineage.get("run_id")
                or not item_lineage.get("campaign_id")
            ):
                result.lineage_failures += 1
                result.add(f"lineage mismatch: {sample_id}")
            task_observed_splits[task_id].add(split)
            task_views[task_id].add(view)
            if row.get("template_id") != declared_task_templates.get(task_id):
                result.add(f"sample template lineage mismatch: {sample_id}")
            template_splits[str(row.get("template_id") or "")].add(split)
            numeric_splits[str(row.get("numeric_template_id") or "")].add(split)

    for template_id, splits in template_splits.items():
        if len(splits) > 1:
            result.template_leaks += 1
            result.add(f"template leakage {template_id}: {sorted(splits)}")
    for template_id, splits in numeric_splits.items():
        if len(splits) > 1:
            result.numeric_template_leaks += 1
            result.add(f"numeric template leakage {template_id}: {sorted(splits)}")
    for task_id, splits in task_observed_splits.items():
        expected_split = (manifest.get("task_splits") or {}).get(task_id)
        if splits != {expected_split}:
            result.add(f"task split mismatch {task_id}: {sorted(splits)} vs {expected_split}")
    source_task_ids = set(lineage)
    manifest_task_ids = set((manifest.get("task_splits") or {}).keys())
    if manifest_task_ids != source_task_ids:
        result.add("manifest task inventory does not match source")
    if set((manifest.get("task_fingerprints") or {}).keys()) != source_task_ids:
        result.add("task fingerprint inventory does not match source")
    assigned_template_tasks: set[str] = set()
    for template_id, assignment in (manifest.get("template_assignments") or {}).items():
        split = assignment.get("split")
        task_ids = assignment.get("task_ids") or []
        if not template_id or split not in SPLITS or not task_ids:
            result.add(f"invalid template assignment: {template_id}")
            continue
        for task_id in task_ids:
            assigned_template_tasks.add(task_id)
            if (manifest.get("task_splits") or {}).get(task_id) != split:
                result.add(f"template/task split mismatch: {template_id}/{task_id}")
    if assigned_template_tasks != source_task_ids:
        result.add("template assignment task inventory does not match source")
    if len(manifest.get("template_assignments") or {}) != manifest.get("stats", {}).get(
        "template_groups"
    ):
        result.add("template group count does not match stats")
    for task_id in source_task_ids:
        required = {"instruction_to_tool_call", "full_trajectory"}
        if not required.issubset(task_views.get(task_id, set())):
            result.add(f"required views missing for task {task_id}: {sorted(required - task_views.get(task_id, set()))}")
    targets = manifest.get("split_targets") or {}
    if dict(observed_counts) != targets:
        result.add(f"full trajectory split counts mismatch: {dict(observed_counts)} vs {targets}")
    train_tasks = {task for task, split in manifest.get("task_splits", {}).items() if split == "train"}
    holdout_tasks = {task for task, split in manifest.get("task_splits", {}).items() if split == "holdout"}
    if train_tasks.intersection(holdout_tasks):
        result.add("holdout tasks overlap training tasks")
    expected_view_counts = manifest.get("stats", {}).get("view_counts") or {}
    actual_view_counts = {
        split: {view: observed_views[split][view] for view in VIEWS} for split in SPLITS
    }
    if actual_view_counts != expected_view_counts:
        result.add(f"view counts do not match stats: {actual_view_counts} vs {expected_view_counts}")
    if result.samples != manifest.get("stats", {}).get("total_samples"):
        result.add("total sample count does not match stats")
    for view in VIEWS:
        if sum(observed_views[split][view] for split in SPLITS) == 0:
            result.add(f"training view is empty: {view}")
    return result


def render_training_report(manifest: Mapping[str, Any], audit: AuditResult) -> str:
    stats = manifest["stats"]
    lines = [
        "# A5 训练数据管线验收报告",
        "",
        f"结论：**{'通过' if audit.passed else '失败'}**。",
        "",
        "## 数据规模",
        "",
        f"- 黄金源任务：{stats['source_tasks']} 条。",
        f"- 不可拆分模板组：{stats['template_groups']} 组。",
        f"- 导出训练样本：{stats['total_samples']} 条。",
        f"- 清除运行噪声字段：{stats['noise_fields_removed']} 个。",
        f"- 修复历史脱敏占位符造成的参数 JSON：{stats['repaired_tool_arguments']} 处。",
        f"- 去重丢弃：{sum(stats['duplicate_samples_dropped'].values())} 条；超长丢弃："
        f"{sum(stats['samples_dropped_by_length'].values())} 条。",
        f"- 最长样本：{stats['max_sample_chars']} 字符（硬上限 16,384）。",
        "",
        "| 分区 | 源任务 | 指令→工具 | 完整轨迹 | 错误→纠正 | 场景→下一步 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in SPLITS:
        views = stats["view_counts"][split]
        lines.append(
            f"| {split} | {stats['split_task_counts'][split]} | "
            f"{views['instruction_to_tool_call']} | {views['full_trajectory']} | "
            f"{views['error_to_correction']} | {views['scene_to_next_step']} |"
        )
    lines.extend(
        [
            "",
            "## 防泄漏与血缘",
            "",
            "- 分区在源任务层完成，某一任务的全部训练视图始终位于同一区域。",
            "- 数值归一化签名与 campaign/标签模板族通过并查集合并后整体分配，不允许跨区。",
            "- 标签、难度和错误恢复视图参与确定性分层打分；模板不可拆分约束优先于逐标签精确比例。",
            "- 既有 `manifest.json` 是 split lock；未来重建或增量加入任务时，holdout 不会迁入 train。",
            "- 每条样本记录源文件、行号、Trace 哈希、run/task/campaign ID 和 Prompt/工具 Schema 版本。",
            "- manifest 固定源数据、campaign、全部导出文件的 SHA-256、字节数和行数。",
            f"- 源 Trace SHA-256：`{manifest['source']['sha256']}`。",
            f"- Pipeline / split seed：`{manifest['pipeline_version']}` / `{manifest['split_seed']}`。",
            "- 历史 Trace 中未加引号的脱敏坐标/GUID 占位符仅被规范为合法 JSON 字符串；"
            "管线不会猜测或恢复已移除的原值。",
            "",
            "## 审计结果",
            "",
            f"- 模板跨区：{audit.template_leaks}。",
            f"- 数值模板跨区：{audit.numeric_template_leaks}。",
            f"- 重复样本：{audit.duplicate_samples}。",
            f"- 血缘失败：{audit.lineage_failures}。",
            f"- 敏感发现：{audit.privacy_findings}。",
            "",
            "## 复现",
            "",
            "```bash",
            "python tools/build_training_dataset.py build",
            "python tools/build_training_dataset.py audit",
            "python tools/build_training_dataset.py report --output docs/training-data-pipeline.md",
            "```",
            "",
            "训练与验证脚本只能读取 `train/` 和 `validation/`；`holdout/` 标记为锁定保留集，不用于训练或调参。",
            "",
        ]
    )
    if audit.findings:
        lines.extend(["## 发现", "", *[f"- {finding}" for finding in audit.findings], ""])
    return "\n".join(lines)


def audit_as_dict(result: AuditResult) -> dict[str, Any]:
    return asdict(result)
