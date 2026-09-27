#!/usr/bin/env python3
"""Create and verify the CPU-only C5 contract/source freeze artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_tool_contract_candidate import TOKENIZER_SNAPSHOT  # noqa: E402
from training.c5_contract import (  # noqa: E402
    BASE_MODEL,
    BASE_MODEL_REVISION,
    CONTRACT_ID,
    CORE_INVOCATION_TOOLS,
    DECODE_CONFIG,
    EXPERIMENT_ID,
    INVOCATION_SYSTEM,
    MAX_SEQUENCE_TOKENS,
    SELECTOR_SYSTEM,
    SELECTOR_TOOLS,
    parse_invocation,
    parse_selection,
    render_invocation,
    render_selection,
    selection_route,
)
from training.c5_freeze import (  # noqa: E402
    C5FreezeError,
    PIPELINE_ID,
    assert_development_source,
    build_source_manifest,
    canonical_bytes,
    load_source_tasks,
    sha256_bytes,
    sha256_file,
    validate_public_manifest,
)
from training.tool_schema_inventory import load_public_mcp_tools  # noqa: E402


DEFAULT_SOURCE = ROOT / "data/golden_traces_v2.jsonl"
DEFAULT_OUTPUT = ROOT / "eval/c5"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _schema_hash(tools: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(tools))


def contract_audit() -> dict[str, Any]:
    from transformers import AutoTokenizer

    if not TOKENIZER_SNAPSHOT.is_dir():
        raise C5FreezeError("pinned tokenizer is unavailable locally; no download attempted")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_SNAPSHOT, local_files_only=True)
    tools = load_public_mcp_tools()
    step = "在隔离的合成毫米场景中，创建宽 20、深 10、高 5 的长方体。"
    selector_prompt = render_selection(tokenizer, step, tools)
    selector_target = render_selection(tokenizer, step, tools, selected_tool="create_box")
    selector_null = render_selection(tokenizer, "尺寸尚未决定，请先等等。", tools, selected_tool=None)
    if selector_prompt.prompt != selector_target.prompt:
        raise C5FreezeError("selector training and inference prefixes differ")
    invocation_tokens = {
        name: render_invocation(tokenizer, step, tools, name).prompt_tokens
        for name in CORE_INVOCATION_TOOLS
    }
    invocation_prompt = render_invocation(tokenizer, step, tools, "create_box")
    invocation_target = render_invocation(
        tokenizer,
        step,
        tools,
        "create_box",
        arguments={"width": 20, "depth": 10, "height": 5},
    )
    if invocation_prompt.prompt != invocation_target.prompt:
        raise C5FreezeError("invocation training and inference prefixes differ")
    selector_text = selector_target.full[len(selector_target.prompt) :]  # type: ignore[index]
    invocation_text = invocation_target.full[len(invocation_target.prompt) :]  # type: ignore[index]
    if parse_selection(selector_text, tools) != "create_box":
        raise C5FreezeError("selector target did not round-trip")
    parsed = parse_invocation(invocation_text, "create_box", tools)
    if parsed["arguments"] != {"width": 20, "depth": 10, "height": 5}:
        raise C5FreezeError("invocation target did not round-trip")
    if selection_route("get_object_info") != "unsupported_for_c5":
        raise C5FreezeError("non-core selector route is not fail-closed")
    implementation_paths = (
        ROOT / "training/c5_contract.py",
        ROOT / "training/tool_selector_v4_candidate.py",
        ROOT / "training/tool_contract_v3_candidate.py",
    )
    return {
        "contract_id": CONTRACT_ID,
        "experiment_id": EXPERIMENT_ID,
        "base_model": BASE_MODEL,
        "base_revision": BASE_MODEL_REVISION,
        "tokenizer_snapshot_sha256": sha256_file(TOKENIZER_SNAPSHOT / "tokenizer_config.json"),
        "public_tool_schema_sha256": _schema_hash(tools),
        "selector_system_sha256": sha256_bytes(SELECTOR_SYSTEM.encode("utf-8")),
        "invocation_system_sha256": sha256_bytes(INVOCATION_SYSTEM.encode("utf-8")),
        "selector_rendered_prefix_sha256": sha256_bytes(selector_prompt.prompt.encode("utf-8")),
        "invocation_rendered_prefix_sha256": sha256_bytes(
            invocation_prompt.prompt.encode("utf-8")
        ),
        "implementation_sha256": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in implementation_paths
        },
        "selector_tools": list(SELECTOR_TOOLS),
        "core_invocation_tools": list(CORE_INVOCATION_TOOLS),
        "sequence_tokens": MAX_SEQUENCE_TOKENS,
        "decode": DECODE_CONFIG,
        "selector_prompt_tokens": selector_prompt.prompt_tokens,
        "selector_target_tokens": selector_target.full_tokens,
        "selector_null_target_tokens": selector_null.full_tokens,
        "invocation_prompt_min_tokens": min(invocation_tokens.values()),
        "invocation_prompt_max_tokens": max(invocation_tokens.values()),
        "invocation_prompt_tokens": dict(sorted(invocation_tokens.items())),
        "invocation_target_tokens": invocation_target.full_tokens,
        "all_core_invocations_fit_reserved_budget": True,
        "train_inference_prefix_exact": True,
        "strict_roundtrips": 3,
        "parser_repair_allowed": False,
        "model_weights_loaded": False,
        "gpu_used": False,
        "rhino_contacted": False,
        "holdout_read": False,
    }


def freeze_spec(contract: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "status": "offline_freeze_complete_training_not_authorized",
        "experiment_id": EXPERIMENT_ID,
        "repository_governance": {
            "revision": "2026-09-27-owner-only-v1",
            "authority_identity": "repository_owner",
            "pull_requests": {
                "required_reviewer_count": 1,
                "reviewer_1_identity": "repository_owner",
                "reviewer_2_required": False,
                "agent_self_approval_allowed": False,
            },
            "git_operations": {
                "automatic_branch_push_authorized": True,
                "automatic_pull_request_create_or_update_authorized": True,
                "automatic_merge_authorized": False,
            },
        },
        "contract": contract,
        "dataset": {
            "pipeline_id": PIPELINE_ID,
            "accepted_family_targets": {
                "train": 320,
                "validation": 60,
                "development": 60,
                "final_holdout": 80,
            },
            "source_audit_sha256": sha256_bytes(canonical_bytes(source_manifest)),
            "source_family_count": source_manifest["audit"]["conservative_family_count"],
            "new_development_families_required": source_manifest["audit"][
                "new_development_families_required"
            ],
            "grouping": [
                "campaign_and_exact_tag_set",
                "numeric_normalized_instruction",
                "shared_source_trace",
                "future_semantic_near_duplicate_cluster",
            ],
            "existing_source_assignment_is_planning_only": True,
            "a5_p2_exclusion_map_required_before_dataset_acceptance": True,
            "required_reviewer_count": 1,
            "reviewer_1_identity": "repository_owner",
            "reviewer_2_required": False,
            "agent_self_approval_allowed": False,
            "unrestricted_natural_language_targets_allowed": False,
        },
        "holdout_custody": {
            "status": "protocol_frozen_repository_owner_custodian",
            "expected_families": 80,
            "content_created_by_this_command": False,
            "content_path_recorded_in_repository": False,
            "developer_read_allowed_before_consumption": False,
            "rows_read": 0,
            "custodian_identity": "repository_owner",
            "custodian_role": "repository_owner_independent_from_agent",
            "commitment_required": [
                "encrypted_artifact_sha256",
                "expected_family_count",
                "strata_counts",
                "exclusion_corpus_sha256_set",
                "author_and_reviewer_role_attestations",
            ],
            "single_use_gate": "append_only_consumption_receipt_before_decryption",
        },
        "historical_exclusions": {
            "a5": "diagnosis_only_never_c5_split",
            "p2": "diagnosis_only_never_c5_split",
            "r_consumed_cases": "exclusion_corpus_only_never_c5_split",
            "c4_result": "NO-GO",
            "v8_result": "formal_quality_fail_59_of_60",
        },
        "training": {
            "authorized": False,
            "gpu_authorized": False,
            "formal_runs": 1,
            "development_runs_max": 2,
            "gpu_hour_ceiling": 16,
            "selection_metric": [
                "validation_sequence_exact",
                "validation_arguments_exact",
                "validation_parse_exact",
                "validation_loss",
            ],
        },
        "final_decision": {
            "allowed": ["GO", "MORE-DATA", "NO-GO"],
            "go_does_not_switch_default_route": True,
            "thresholds_frozen_before_holdout": True,
            "offline": {
                "lora_parse_exact_min": 0.90,
                "sequence_exact_delta_min": 0.10,
                "paired_net_wins_min_of_80": 8,
                "mcnemar_two_sided_p_max_exclusive": 0.05,
                "tool_name_exact_delta_min": 0.05,
                "arguments_exact_delta_min": 0.05,
                "clarify_accuracy_min": 0.85,
                "refuse_accuracy_min": 0.85,
                "critical_safety_errors_max": 0,
            },
        },
    }


def build(output_dir: Path) -> dict[str, Any]:
    assert_development_source(DEFAULT_SOURCE, project_root=ROOT)
    tasks = load_source_tasks(DEFAULT_SOURCE)
    source = build_source_manifest(DEFAULT_SOURCE, tasks)
    source["implementation_sha256"] = {
        "training/c5_freeze.py": sha256_file(ROOT / "training/c5_freeze.py"),
        "tools/freeze_c5_offline.py": sha256_file(ROOT / "tools/freeze_c5_offline.py"),
    }
    findings = validate_public_manifest(source)
    if findings:
        raise C5FreezeError("; ".join(findings))
    contract = contract_audit()
    spec = freeze_spec(contract, source)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "source-audit.json", source)
    _write_json(output_dir / "offline-freeze-spec.json", spec)
    index = {
        "schema_version": "1.0",
        "artifacts": [
            {
                "path": "offline-freeze-spec.json",
                "sha256": sha256_file(output_dir / "offline-freeze-spec.json"),
            },
            {
                "path": "source-audit.json",
                "sha256": sha256_file(output_dir / "source-audit.json"),
            },
        ],
        "holdout_content_present": False,
        "training_authorized": False,
    }
    _write_json(output_dir / "manifest.json", index)
    return index


def verify(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        raise C5FreezeError("C5 manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in manifest.get("artifacts") or []:
        path = output_dir / str(artifact.get("path") or "")
        if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
            raise C5FreezeError(f"C5 artifact mismatch: {path.name}")
    source = json.loads((output_dir / "source-audit.json").read_text(encoding="utf-8"))
    findings = validate_public_manifest(source)
    if findings:
        raise C5FreezeError("; ".join(findings))
    assert_development_source(DEFAULT_SOURCE, project_root=ROOT)
    if source.get("source", {}).get("sha256") != sha256_file(DEFAULT_SOURCE):
        raise C5FreezeError("approved 500-trace source drifted from the freeze")
    for relative, expected in (source.get("implementation_sha256") or {}).items():
        implementation = (ROOT / str(relative)).resolve()
        try:
            implementation.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise C5FreezeError("implementation hash names a path outside the project") from exc
        if not implementation.is_file() or sha256_file(implementation) != expected:
            raise C5FreezeError(f"C5 source-audit implementation drifted: {relative}")
    spec = json.loads((output_dir / "offline-freeze-spec.json").read_text(encoding="utf-8"))
    for relative, expected in (spec.get("contract", {}).get("implementation_sha256") or {}).items():
        implementation = (ROOT / str(relative)).resolve()
        try:
            implementation.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise C5FreezeError("contract hash names a path outside the project") from exc
        if not implementation.is_file() or sha256_file(implementation) != expected:
            raise C5FreezeError(f"C5 contract implementation drifted: {relative}")
    if spec.get("training", {}).get("authorized") is not False:
        raise C5FreezeError("offline freeze unexpectedly authorizes training")
    if spec.get("holdout_custody", {}).get("rows_read") != 0:
        raise C5FreezeError("offline freeze consumed final holdout rows")
    governance = spec.get("repository_governance", {})
    pull_requests = governance.get("pull_requests", {})
    git_operations = governance.get("git_operations", {})
    if governance.get("authority_identity") != "repository_owner":
        raise C5FreezeError("repository owner authority is not frozen")
    if pull_requests.get("required_reviewer_count") != 1:
        raise C5FreezeError("pull-request reviewer count drifted")
    if pull_requests.get("reviewer_1_identity") != "repository_owner":
        raise C5FreezeError("pull-request reviewer 1 identity drifted")
    if pull_requests.get("reviewer_2_required") is not False:
        raise C5FreezeError("pull-request reviewer 2 was unexpectedly required")
    if git_operations.get("automatic_branch_push_authorized") is not True:
        raise C5FreezeError("automatic branch push authorization is missing")
    if git_operations.get("automatic_pull_request_create_or_update_authorized") is not True:
        raise C5FreezeError("automatic pull-request authorization is missing")
    if git_operations.get("automatic_merge_authorized") is not False:
        raise C5FreezeError("automatic merge was unexpectedly authorized")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    try:
        result = build(output) if args.command == "build" else verify(output)
    except (C5FreezeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"C5 offline freeze error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
