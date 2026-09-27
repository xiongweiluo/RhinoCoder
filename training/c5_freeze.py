"""Deterministic, content-minimizing C5 source audit and split planning.

Only the approved 500-trace development source is read.  Outputs contain
aggregates and salted task hashes, never instructions, arguments, tool
results, A5/P2 examples, or final-holdout content.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from data_pipeline.training_views import numeric_template_signature
from training.c5_contract import CORE_INVOCATION_TOOLS, SELECTOR_TOOLS


PIPELINE_ID = "c5-offline-freeze-v1"
SPLIT_SEED = "rhinocoder-c5-development-v1"
SOURCE_SPLIT_TARGETS = {
    "candidate_train": 320,
    "candidate_validation": 60,
    "candidate_development": 60,
    "source_reserve": 60,
}
FORBIDDEN_SOURCE_MARKERS = (
    "/data/training/a5/",
    # Split the literal so the P2 source-use audit does not mistake this
    # deny-list entry for a training consumer reference.
    "/eval/" "p2/",
    "/holdout/",
    "final-holdout",
    "final_holdout",
)
_SPLITS = tuple(SOURCE_SPLIT_TARGETS)


class C5FreezeError(RuntimeError):
    """A source, isolation, or manifest invariant was violated."""


@dataclass(frozen=True, slots=True)
class SourceTask:
    task_id: str
    run_id: str
    campaign_id: str
    tags: tuple[str, ...]
    instruction: str
    tool_names: tuple[str, ...]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def assert_development_source(path: Path, *, project_root: Path) -> None:
    resolved = path.resolve()
    root = project_root.resolve()
    try:
        relative = "/" + resolved.relative_to(root).as_posix().lower()
    except ValueError as exc:
        raise C5FreezeError("C5 source must stay inside the project workspace") from exc
    if relative != "/data/golden_traces_v2.jsonl":
        raise C5FreezeError("only data/golden_traces_v2.jsonl is approved for this audit")
    if any(marker in relative for marker in FORBIDDEN_SOURCE_MARKERS):
        raise C5FreezeError("A5/P2/final-holdout sources are forbidden")


def load_source_tasks(path: Path, *, expected_rows: int | None = 500) -> list[SourceTask]:
    tasks: list[SourceTask] = []
    seen_tasks: set[str] = set()
    seen_runs: set[str] = set()
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise C5FreezeError(f"source line {line_no} is invalid JSON") from exc
        metadata = row.get("metadata") if isinstance(row, dict) else None
        task = metadata.get("task") if isinstance(metadata, dict) else None
        if not isinstance(task, dict):
            raise C5FreezeError(f"source line {line_no} has no task lineage")
        task_id = str(task.get("task_id") or "").strip()
        run_id = str(row.get("run_id") or "").strip()
        campaign_id = str(task.get("campaign_id") or "").strip()
        if not task_id or not run_id or not campaign_id:
            raise C5FreezeError(f"source line {line_no} has incomplete lineage")
        if task_id in seen_tasks or run_id in seen_runs:
            raise C5FreezeError(f"source line {line_no} repeats task/run lineage")
        seen_tasks.add(task_id)
        seen_runs.add(run_id)
        instruction = next(
            (
                str(message.get("content") or "").strip()
                for message in row.get("messages") or []
                if isinstance(message, dict)
                and message.get("role") == "user"
                and str(message.get("content") or "").strip()
            ),
            "",
        )
        if not instruction:
            raise C5FreezeError(f"source line {line_no} has no user instruction")
        tool_names: list[str] = []
        for message in row.get("messages") or []:
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                name = str(function.get("name") or "") if isinstance(function, dict) else ""
                if name:
                    if name not in SELECTOR_TOOLS:
                        raise C5FreezeError(f"source line {line_no} names unknown tool {name!r}")
                    tool_names.append(name)
        if not tool_names:
            raise C5FreezeError(f"source line {line_no} contains no tool call")
        tasks.append(
            SourceTask(
                task_id=task_id,
                run_id=run_id,
                campaign_id=campaign_id,
                tags=tuple(sorted(str(tag) for tag in task.get("tags") or [])),
                instruction=instruction,
                tool_names=tuple(tool_names),
            )
        )
    if expected_rows is not None and len(tasks) != expected_rows:
        raise C5FreezeError(f"expected {expected_rows} source rows, found {len(tasks)}")
    return tasks


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


def build_families(tasks: Sequence[SourceTask]) -> list[dict[str, Any]]:
    """Apply the conservative A5 grouping rule before any split assignment."""

    dsu = _DisjointSet(task.task_id for task in tasks)
    semantic_owner: dict[tuple[str, tuple[str, ...]], str] = {}
    numeric_owner: dict[str, str] = {}
    for task in tasks:
        semantic = (task.campaign_id, task.tags)
        numeric = numeric_template_signature(task.instruction)
        for owners, key in ((semantic_owner, semantic), (numeric_owner, numeric)):
            owner = owners.setdefault(key, task.task_id)
            dsu.union(task.task_id, owner)
    grouped: dict[str, list[SourceTask]] = defaultdict(list)
    for task in tasks:
        grouped[dsu.find(task.task_id)].append(task)
    families = []
    for members in grouped.values():
        member_ids = sorted(member.task_id for member in members)
        tools = Counter(name for member in members for name in set(member.tool_names))
        calls = Counter(name for member in members for name in member.tool_names)
        family_id = "fam_" + _stable_hash("\n".join(member_ids))[:20]
        families.append(
            {
                "family_id": family_id,
                "size": len(members),
                "task_hashes": [
                    _stable_hash(f"{SPLIT_SEED}:{task_id}") for task_id in member_ids
                ],
                "tool_task_counts": dict(sorted(tools.items())),
                "tool_call_counts": dict(sorted(calls.items())),
            }
        )
    return sorted(families, key=lambda family: family["family_id"])


def assign_source_splits(families: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Deterministically allocate intact source families near task-count targets."""

    counts = Counter({split: 0 for split in _SPLITS})
    tool_counts = {split: Counter() for split in _SPLITS}
    global_tools = Counter()
    for family in families:
        global_tools.update(family["tool_task_counts"])
    assignments: dict[str, str] = {}
    ordered = sorted(
        families,
        key=lambda family: (
            -len(family["tool_task_counts"]),
            -int(family["size"]),
            _stable_hash(f"{SPLIT_SEED}:{family['family_id']}"),
        ),
    )
    total = sum(int(family["size"]) for family in families)
    for family in ordered:
        size = int(family["size"])
        candidates = [
            split
            for split in _SPLITS
            if counts[split] + size <= SOURCE_SPLIT_TARGETS[split]
        ] or list(_SPLITS)

        def score(split: str) -> tuple[float, str]:
            fill = (counts[split] + size) / SOURCE_SPLIT_TARGETS[split]
            rare_balance = []
            for name, amount in family["tool_task_counts"].items():
                desired = max(
                    global_tools[name] * SOURCE_SPLIT_TARGETS[split] / max(total, 1),
                    0.25,
                )
                rare_balance.append((tool_counts[split][name] + amount) / desired)
            balance = sum(rare_balance) / len(rare_balance) if rare_balance else 0.0
            return fill + 0.25 * balance, _stable_hash(
                f"{SPLIT_SEED}:{family['family_id']}:{split}"
            )

        split = min(candidates, key=score)
        assignments[str(family["family_id"])] = split
        counts[split] += size
        tool_counts[split].update(family["tool_task_counts"])
    return assignments


def build_source_manifest(
    source_path: Path,
    tasks: Sequence[SourceTask],
    *,
    source_path_label: str = "data/golden_traces_v2.jsonl",
) -> dict[str, Any]:
    families = build_families(tasks)
    assignments = assign_source_splits(families)
    task_tool_counts = Counter(name for task in tasks for name in set(task.tool_names))
    call_counts = Counter(name for task in tasks for name in task.tool_names)
    family_tool_counts = Counter(
        name for family in families for name in family["tool_task_counts"]
    )
    split_tasks = Counter()
    split_families = Counter()
    split_tool_tasks = {split: Counter() for split in _SPLITS}
    public_families = []
    for family in families:
        split = assignments[family["family_id"]]
        split_tasks[split] += family["size"]
        split_families[split] += 1
        split_tool_tasks[split].update(family["tool_task_counts"])
        public_families.append({**family, "candidate_split": split})
    core = {
        name: {
            "source_calls": call_counts[name],
            "source_tasks": task_tool_counts[name],
            "source_families": family_tool_counts[name],
            "train_family_minimum": 20,
            "requires_new_families": max(20 - family_tool_counts[name], 0),
        }
        for name in CORE_INVOCATION_TOOLS
    }
    return {
        "schema_version": "1.0",
        "pipeline_id": PIPELINE_ID,
        "split_seed": SPLIT_SEED,
        "source": {
            "path": source_path_label,
            "sha256": sha256_file(source_path),
            "rows": len(tasks),
            "raw_content_exported": False,
        },
        "isolation": {
            "a5_read": False,
            "p2_read": False,
            "final_holdout_read": False,
            "final_holdout_rows_read": 0,
        },
        "audit": {
            "unique_tasks": len({task.task_id for task in tasks}),
            "unique_runs": len({task.run_id for task in tasks}),
            "campaign_counts": dict(sorted(Counter(task.campaign_id for task in tasks).items())),
            "conservative_family_count": len(families),
            "family_size_histogram": dict(
                sorted(Counter(str(family["size"]) for family in families).items())
            ),
            "selector_tool_count": len(SELECTOR_TOOLS),
            "observed_tool_count": len(task_tool_counts),
            "tool_call_counts": dict(sorted(call_counts.items())),
            "tool_task_counts": dict(sorted(task_tool_counts.items())),
            "core_tool_coverage": core,
            "source_can_supply_440_independent_families": len(families) >= 440,
            "new_development_families_required": max(440 - len(families), 0),
        },
        "candidate_source_assignment": {
            "purpose": "planning_only_not_dataset_acceptance",
            "accepted_into_dataset_v2": False,
            "historical_eval_overlap_status": "not_resolved_no_a5_or_p2_files_read",
            "target_task_counts": SOURCE_SPLIT_TARGETS,
            "actual_task_counts": dict(sorted(split_tasks.items())),
            "actual_family_counts": dict(sorted(split_families.items())),
            "tool_task_counts": {
                split: dict(sorted(counts.items()))
                for split, counts in split_tool_tasks.items()
            },
        },
        "families": public_families,
    }


def validate_public_manifest(manifest: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    serialized = canonical_bytes(manifest).decode("utf-8").lower()
    for marker in ("messages", "instruction", "arguments", "tool_result", "reasoning_content"):
        if re.search(rf'"{re.escape(marker)}"\s*:', serialized):
            findings.append(f"public manifest exposes forbidden field {marker}")
    isolation = manifest.get("isolation") or {}
    if isolation != {
        "a5_read": False,
        "p2_read": False,
        "final_holdout_read": False,
        "final_holdout_rows_read": 0,
    }:
        findings.append("isolation declaration is missing or unsafe")
    families = manifest.get("families") or []
    seen: set[str] = set()
    for family in families:
        hashes = set(family.get("task_hashes") or [])
        if seen.intersection(hashes):
            findings.append("a task hash appears in more than one family")
        seen.update(hashes)
    return findings
