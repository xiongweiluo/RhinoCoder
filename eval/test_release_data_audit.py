from __future__ import annotations

import hashlib
import json

from tools.audit_release_data import EXPECTED_ARTIFACTS, audit_release_data


def _write_release_fixture(tmp_path, *, real_guid: bool = False):
    report = tmp_path / "docs" / "benchmark-report.md"
    report.parent.mkdir(parents=True)
    report.write_text("# Public aggregate\n", encoding="utf-8")

    artifact_rows = []
    for relative in sorted(EXPECTED_ARTIFACTS - {"docs/benchmark-report.md"}):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        object_id = "22222222-2222-4222-8222-222222222222" if real_guid else "sample-object"
        payload = {
            "name": "Synthetic",
            "sample": True,
            "provenance": "synthetic",
            "privacy": {
                "reviewed": True,
                "contains_real_trace_data": False,
                "coordinates": "synthetic",
                "object_ids": "synthetic",
                "layers": "generic",
            },
            "events": [
                {"type": "scene.checked", "run_id": "replay-test", "seq": 1, "timestamp": "fixed", "payload": {"scene_summary": {"objects": [{"object_id": object_id, "layer": "Sample", "center": [1, 2, 3]}]}}},
                {"type": "run.completed", "run_id": "replay-test", "seq": 2, "timestamp": "fixed", "payload": {}},
            ],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    for relative in sorted(EXPECTED_ARTIFACTS):
        path = tmp_path / relative
        artifact_rows.append({"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {
        "schema_version": "1.0",
        "review": {"method": "automated_scan_and_artifact_review"},
        "artifacts": artifact_rows,
    }
    manifest_path = tmp_path / "docs" / "release-data-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_release_data_audit_accepts_locked_synthetic_artifacts(tmp_path):
    _write_release_fixture(tmp_path)
    result = audit_release_data(tmp_path)
    assert result.passed, result.findings
    assert set(result.checked) == EXPECTED_ARTIFACTS


def test_release_data_audit_rejects_real_guid_and_hash_drift(tmp_path):
    _write_release_fixture(tmp_path, real_guid=True)
    report = tmp_path / "docs" / "benchmark-report.md"
    report.write_text(report.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    result = audit_release_data(tmp_path)
    assert not result.passed
    assert any("GUID" in finding for finding in result.findings)
    assert any("SHA-256" in finding for finding in result.findings)
