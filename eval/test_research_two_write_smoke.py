import copy

import pytest

from plugin.rhino_listener.research_safety import ResearchSafetyError, canonical_hash
from tools.r_research_two_write_smoke import SPEC, run, verify_owner_approval


def approval():
    return {"authorized_by": "repository_owner", "probe_spec_sha256": canonical_hash(SPEC), "approved": True,
            "authorization_basis": "explicit owner reply approving fixed two-write research safety probe"}


@pytest.mark.parametrize("field,value", [("authorized_by", "codex"), ("approved", False),
                                         ("probe_spec_sha256", "a"*64), ("authorization_basis", "agent thinks so")])
def test_agent_or_changed_spec_cannot_open_fixture(tmp_path, field, value):
    value_record = approval()
    value_record[field] = value
    with pytest.raises(ResearchSafetyError):
        run(tmp_path/"nonexistent-batch", tmp_path/"output", value_record)
    assert not (tmp_path/"output").exists()


def test_exact_external_approval_not_a_general_model_quality_grant():
    verify_owner_approval(approval())
    changed = copy.deepcopy(SPEC)
    changed["steps"][0]["width"] += 1
    with pytest.raises(ResearchSafetyError):
        verify_owner_approval({**approval(), "probe_spec_sha256": canonical_hash(changed)})
    assert SPEC["model_calls"] == 0 and SPEC["max_write_requests"] == 2 and not SPEC["formal_quality_claim"]
