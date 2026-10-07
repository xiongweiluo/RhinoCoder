"""Accepted formal preparation scope; pure checks, NOT an execution grant."""
from .c5_research_native import digest, require
from .c5_host_assurance_session import host_policy, DEV_C_ID
from .c5_host_assurance_v2 import validate_transition
from .c5_formal20_observation_capacity import LIMITS, validate_limits

PROPOSAL_SHA = '81b799b1e936c588f51ac41ea11c2d9975044302d9d2f5c037866b78ec349efb'
PROPOSAL_ID = 'C5FORMAL20-OBSERVATION-CAPACITY-20261007-V2'
STUDY_ID = 'c5-rhino-paired-20-v1'
APPROVAL_BASIS = 'direct repository_owner approval of complete C5-6 formal20 spec and runtime freeze'
LIFECYCLE = {'protocol':'c5-native-completion-timing-v1','native_ack_seconds':120,
    'settle_seconds':60,'timer_before_client_guard':True,'full_decode_validation_in_window':True,
    'post_publication_service_record_required':True,'settle_entry_and_completion_checked':True,
    'source_checks_retained_without_cache':True,'failure_unknown_no_retry':True,
    'logical_deadline_not_CLR_preemption':True}


def validate_acceptance(proposal, acceptance):
    require(type(acceptance.get('accepted')) is bool and digest(proposal) == PROPOSAL_SHA and acceptance == {
        'proposal_id':PROPOSAL_ID,'proposal_sha256':PROPOSAL_SHA,'actor':'repository_owner',
        'accepted':True,'scope':'formal_adapter_cpu_audit_and_freeze_preparation_only_no_execution'},
        'new exact formal preparation scope acceptance required')
    validate_limits(proposal['proposed_limits'])
    return dict(acceptance)


def formal_host_policy(transition, consent, proposal, acceptance):
    validate_transition(transition, consent)
    validate_acceptance(proposal, acceptance)
    old = host_policy(transition, consent, study_id=DEV_C_ID)
    return {key:value for key,value in old.items() if key != 'checkpoint_limit'} | {
        'normal_checkpoint_limit':LIMITS['normal_checkpoints'],
        'cleanup_checkpoint_limit':LIMITS['cleanup_checkpoints'],
        'journal_limit':LIMITS['journal_records'],
        'settle_samples_per_execute':LIMITS['settle_samples_per_execute'],
        'capacity_proposal_sha256':PROPOSAL_SHA}


def validate_formal_binding(spec, freeze, approval):
    require(spec.get('field_protocol_version') == freeze.get('field_protocol_version') == 2
        and type(spec['field_protocol_version']) is int and type(freeze['field_protocol_version']) is int
        and spec.get('study_id') == freeze.get('study_id') == STUDY_ID
        and spec.get('execution_ready') is True and freeze.get('execution_ready') is True
        and freeze.get('spec_sha256') == digest(spec), 'new complete formal v2 freeze required')
    require(type(approval.get('approved')) is bool and approval == {'study_id':STUDY_ID,'actor':'repository_owner','approved':True,
        'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),'approval_basis':APPROVAL_BASIS},
        'capacity acceptance or development grant cannot execute formal20')
    proposal, accepted = freeze['capacity_proposal'], freeze['capacity_acceptance']
    selected = validate_transition(freeze['host_transition_spec'], freeze['host_transition_consent'])
    policy = formal_host_policy(freeze['host_transition_spec'],freeze['host_transition_consent'],proposal,accepted)
    require(digest(spec.get('host_assurance')) == digest(freeze.get('host_assurance')) == digest(policy)
        and digest(spec.get('lifecycle_protocol')) == digest(freeze.get('lifecycle_protocol')) == digest(LIFECYCLE)
        and spec.get('zero_consumption_readiness_before_private_loader') is True
        and spec.get('automatic_retry_allowed') is False and spec.get('default_route_change_allowed') is False,
        'formal host/timing/readiness/no-retry contract differs')
    return {**selected,'study_id':STUDY_ID,'runtime_freeze_sha256':digest(freeze),
        'policy_binding_verified':True,'whole_field_authority_verified':False,
        'formal_capacity_verified':True}
