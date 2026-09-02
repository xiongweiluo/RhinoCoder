import tools.audit_trace_data as audit_module
from agent.trace_store import AI_REVIEWED


def test_audit_skips_superseded_ai_candidate_gate_but_still_counts_history(monkeypatch):
    golden = {
        "metadata": {"task": {"campaign_id": "phase2", "task_id": "task-1"}}
    }
    candidate = {
        "task": {"campaign_id": "phase2", "task_id": "task-1"},
        "disposition": AI_REVIEWED,
    }

    def fake_read(_path, audit, label):
        rows = {
            "golden_v2": [golden],
            "ai_reviewed_candidate_history": [candidate],
        }.get(label, [])
        audit.counts[label] = len(rows)
        return rows

    monkeypatch.setattr(audit_module, "_read_jsonl", fake_read)
    monkeypatch.setattr(audit_module, "validate_saved_golden_record", lambda _row: [])
    monkeypatch.setattr(audit_module, "contains_sensitive_data", lambda _row: False)

    def unexpected_gate(_row):
        raise AssertionError("已晋级候选不应再按活跃候选门禁复核")

    monkeypatch.setattr(audit_module, "validate_ai_review_candidate", unexpected_gate)

    audit = audit_module.audit_trace_data()

    assert audit.passed
    assert audit.counts["ai_reviewed_candidate_history"] == 1
    assert audit.counts["ai_reviewed_candidate"] == 0
