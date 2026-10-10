"""Fixed public aggregates only, never private state/weights/host execution."""
import copy
import json
from pathlib import Path

import pytest
from tools.audit_c5_final_decision import check, check_values, FILES

ROOT = Path(__file__).resolve().parents[1]


def values():
    return [json.loads((ROOT / name).read_bytes()) for name in FILES]


def test_registered_no_go_has_no_fabricated_quality_or_cleanup():
    result = check()
    assert result['decision'] == 'NO-GO'
    assert not result['full_formal_audit_or_host_cleanup_claim']
    assert not result['whole_goal_complete']


@pytest.mark.parametrize('field,value', [
    ('decision', 'GO'), ('decision', 'MORE-DATA'), ('whole_goal_complete', True),
    ('formal_40_slot_evaluation_or_full_audit_retroactively_completed', True),
    ('pr_and_main_closeout_complete', True), ('private_content_included', True),
    ('schema_version', True), ('agent_private_cases_or_keys_or_raw_model_frames_read', False)])
def test_unsupported_promotion_or_completion_refused(field, value):
    artifacts = values(); artifacts[0][field] = value
    with pytest.raises(ValueError):
        check_values(*artifacts, (ROOT/'docs/c5-contract-aligned-qlora-plan.md').read_text())


@pytest.mark.parametrize('field', ['base_success', 'lora_success', 'critical_safety_errors',
    'duplicate_writes', 'unverified_cleanup_count', 'actual_generation_total'])
def test_unknown_is_not_zero(field):
    artifacts = values(); artifacts[0]['formal_metrics'][field] = 0
    with pytest.raises(ValueError):
        check_values(*artifacts, (ROOT/'docs/c5-contract-aligned-qlora-plan.md').read_text())


def test_custodian_summary_or_threshold_rewrite_refused():
    baseline = values()
    for index in (0, 1):
        artifacts = copy.deepcopy(baseline)
        if index == 0: artifacts[0]['thresholds']['lora_success_min'] = 13
        else: artifacts[1]['full_joint_audit_complete'] = True
        with pytest.raises(ValueError):
            check_values(*artifacts, (ROOT/'docs/c5-contract-aligned-qlora-plan.md').read_text())
