"""Distinct D binding; old A/B/C registry and frozen byte sources unchanged."""
import time
from .c5_host_assurance_session import HostAssuranceSession, host_policy, DEV_C_ID
from .c5_host_assurance_v2 import POLICY, validate_transition
from .c5_research_native import digest, require

DEV_D_ID = "C5DEV-HOSTASSURANCE-20261007-D"
APPROVAL_BASIS = "direct repository_owner approval of new D lifecycle spec and complete runtime freeze"


def validate_study_binding(spec, freeze, approval, transition, consent):
    selected = validate_transition(transition, consent)
    require(spec.get("study_id") == freeze.get("study_id") == DEV_D_ID
            and spec.get("execution_ready") is True and freeze.get("execution_ready") is True
            and freeze.get("spec_sha256") == digest(spec), "new D complete freeze required")
    require(type(approval.get("approved")) is bool and approval == {
        "study_id": DEV_D_ID, "actor": "repository_owner", "approved": True,
        "spec_sha256": digest(spec), "runtime_freeze_sha256": digest(freeze),
        "approval_basis": APPROVAL_BASIS}, "preparation or retired grant cannot execute D")
    policy = host_policy(transition, consent, study_id=DEV_C_ID)
    require(digest(spec.get("host_assurance")) == digest(freeze.get("host_assurance")) == digest(policy)
            and spec.get("automatic_retry_allowed") is False
            and spec.get("default_route_change_allowed") is False, "D limited continuity policy unchanged")
    return {**selected, "study_id": DEV_D_ID, "runtime_freeze_sha256": digest(freeze),
            "policy_binding_verified": True, "whole_field_authority_verified": False}


class HostAssuranceSessionD(HostAssuranceSession):
    def __init__(self, state, binding, backend, source_guard, source_sha, *, clock=time.monotonic):
        require(binding.get("study_id") == DEV_D_ID and binding.get("policy_binding_verified") is True
                and binding.get("whole_field_authority_verified") is False
                and binding.get("policy_id") == POLICY, "exact new D host binding required")
        self.state, self.binding, self.backend = state, binding, backend
        self.source_guard, self.source_sha, self.clock = source_guard, source_sha, clock
        self.start_time = clock()
        self.genesis = digest({"study_id": DEV_D_ID, "runtime_freeze_sha256": binding["runtime_freeze_sha256"],
            "policy_id": POLICY, "source_inventory_sha256": source_sha})
        self.head, self.sequence, self.checkpoints = self.genesis, 0, 0
        self.started, self.subscribe_attempted, self.detached, self.finished = False, False, False, False
        self.baseline, self.blocked = None, False
