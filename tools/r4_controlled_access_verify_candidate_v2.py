#!/usr/bin/env python3
"""Read-only verifier for one-shot isolated R candidate evidence archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import stat
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import r4_v6_formal_quality as core
from tools.r4_controlled_access_archive_v2 import _ledger_rows, _safe_bytes
from tools.r4_controlled_access_batch_v2 import SOURCE_FILES


class CandidateEvidenceError(RuntimeError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise CandidateEvidenceError(code)


def _json(path: Path) -> dict:
    value = json.loads(_safe_bytes(path))
    _require(isinstance(value, dict), "evidence_json_not_object:" + path.name)
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(output: Path) -> dict:
    output = output.resolve(strict=True)
    manifest = _json(output / "evidence-manifest.json")
    _require(manifest.get("version") == 2
             and manifest.get("candidate") == "r4_controlled_access_candidate_v2"
             and manifest.get("formal_quality_claim") is False,
             "manifest_header_invalid")
    files = manifest.get("files")
    source = manifest.get("source_sha256")
    _require(isinstance(files, dict) and isinstance(source, dict)
             and set(source) == set(SOURCE_FILES), "manifest_maps_invalid")
    actual = {str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()
              and path.name != "evidence-manifest.json"}
    _require(set(files) == actual, "manifest_file_set_changed")
    for name, expected in files.items():
        path = output / name
        _require(not path.is_symlink() and path.resolve().is_relative_to(output)
                 and stat.S_IMODE(path.stat().st_mode) == 0o600
                 and _sha(path) == expected, "manifest_file_mismatch:" + name)
    for name, expected in source.items():
        path = core.ROOT / name
        _require(path.is_file() and path.resolve().is_relative_to(core.ROOT)
                 and core.digest(path) == expected, "source_hash_changed:" + name)
    summary = _json(output / "summary.json")
    preflight = _json(output / "preflight.json")
    grant = _json(output / "operator-grant.json")
    stop = _json(output / "operator-stop.json")
    close = _json(output / "close-receipt.json")
    controller = _json(output / "controller-receipt.json")
    archive = _json(output / "archive-receipt.json")
    case_id = summary.get("case_id")
    _require(summary.get("status") == "candidate_recorded_unverified"
             and summary.get("error") is None
             and summary.get("formal_quality_claim") is False
             and summary.get("fixture_closed") is True
             and summary.get("key_removed") is True
             and summary.get("controller_stopped") is True
             and isinstance(case_id, str)
             and preflight.get("case_id") == case_id
             and preflight.get("task_sha256") == summary.get("task_sha256")
             and preflight.get("v8_original_report_sha256")
             == "f83de1b84a357f9983803fb00b3fed729b0f9361a394b39a023a212af36099c2"
             and grant.get("task_sha256") == summary.get("task_sha256")
             and grant.get("human_interactive_opt_in") is True
             and grant.get("scope") == "isolated_unsaved_headless_mm"
             and grant.get("approved_manifest_sha256") == core.MODEL_SHA
             and grant.get("expected_host_key_sha256") == core.HOST_KEY
             and stop.get("status") == "requested"
             and close.get("status") == "closed"
             and close.get("case_id") == case_id
             and close.get("key_removed") is True
             and controller.get("status") == "stopped"
             and archive.get("case_id") == case_id
             and archive.get("archive_method") == "sqlite_backup_v2",
             "candidate_lifecycle_invalid")
    for seq, action, status in ((1, "open", "opened"), (2, "close", "closed"),
                                (3, "stop", "stopped")):
        request = _json(output / f"request-{seq:03d}.json")
        response = _json(output / f"response-{seq:03d}.json")
        _require(request.get("action") == action and response.get("status") == status,
                 "batch_lifecycle_invalid")
    case = output / "cases" / case_id
    ledger_path = case / "fixture.sqlite3"
    _require(ledger_path.is_file() and not ledger_path.is_symlink()
             and not list(case.glob("fixture.sqlite3-*")), "archived_ledger_missing_or_has_sidecars")
    with closing(sqlite3.connect(ledger_path.as_uri() + "?mode=ro", uri=True)) as db:
        _require(db.execute("PRAGMA quick_check").fetchone() == ("ok",),
                 "archived_ledger_integrity_failed")
    ledger = _ledger_rows(ledger_path)
    _require(ledger == summary.get("ledger") == summary.get("expected_ledger")
             == archive.get("ledger"), "archived_ledger_disagrees")
    plans = list(case.glob("v6-plan-*-receipt.json"))
    _require(len(plans) == 1, "plan_receipt_count_invalid")
    receipt = _json(plans[0])
    steps = receipt.get("steps")
    _require(receipt.get("status") == "controlled_access_candidate_v2_completed_not_formal_quality"
             and receipt.get("active_document_unchanged") is True
             and receipt.get("approved_manifest_sha256") == core.MODEL_SHA
             and receipt.get("host_key_sha256") == core.HOST_KEY
             and receipt.get("original_task_sha256") == summary.get("task_sha256")
             and receipt.get("operator_opt_in_grant_sha256") == _sha(output / "operator-grant.json")
             and isinstance(steps, list) and len(steps) == summary.get("step_count")
             and 1 <= len(steps) <= 6, "plan_receipt_invalid")
    writes = 0
    for index, step in enumerate(steps, 1):
        record = _json(case / f"step-{index}-record.json")
        remote = _json(case / f"step-{index}-remote-result.json")
        metrics = _json(case / f"step-{index}-resource-metrics.json")
        _require(record == step and record.get("index") == index
                 and record.get("readback_verified") is True
                 and record.get("remote_result_sha256")
                 == _sha(case / f"step-{index}-remote-result.json")
                 and remote.get("status") == "contract_passed_no_execution"
                 and remote.get("no_dispatch") is True
                 and remote.get("no_consent") is True
                 and remote.get("approved_manifest_sha256") == core.MODEL_SHA
                 and remote.get("task_sha256") == record.get("explicit_task_sha256")
                 and remote.get("scene_sha256") == record.get("before_scene_sha256")
                 and isinstance(metrics.get("model_roundtrip_seconds"), (int, float)),
                 "step_model_or_readback_invalid:" + str(index))
        operation = record.get("operation")
        if operation in {"create_box", "move_object"}:
            writes += 1
            _require(record.get("ledger_state") == "done"
                     and record.get("approval_mode") == "codex_delegated_headless"
                     and record.get("consent_events") == [
                         "requested", "approved", "consumed", "signed_handoff_issued"]
                     and isinstance(record.get("geometry_readback", {}).get("objects"), list),
                     "write_step_audit_invalid:" + str(index))
        else:
            _require(operation in {"get_scene_summary", "get_selected_objects"}
                     and "ledger_state" not in record
                     and "tool_result" in record,
                     "readonly_step_audit_invalid:" + str(index))
    _require(ledger == ({"done": writes} if writes else {}), "write_ledger_count_invalid")
    requests = [path for path in case.glob("execute-*.json")
                if not path.name.startswith("execute-response-")]
    _require(len(requests) == writes
             and len(list(case.glob("execute-response-*.json"))) == writes,
             "execute_count_invalid")
    for path in case.glob("execute-response-*.json"):
        response = _json(path)
        _require(response.get("status") == "done"
                 and response.get("ledger_state") == "done"
                 and response.get("active_document_unchanged") is True,
                 "rhino_response_invalid")
    return {"status": "candidate_evidence_verified_not_formal_quality",
            "case_id": case_id, "step_count": len(steps), "writes": writes,
            "ledger": ledger, "v8_original_formal_status": "formal_quality_fail"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_archive(args.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()
