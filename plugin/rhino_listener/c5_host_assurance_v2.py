"""Proposed explicitly weaker host-trust policy; no default gate integration.

Pure independent metadata replay. No file/CLR/model/fixture/holdout on import
or check. Exact transition approval is NOT a study execution authorization.
Opaque baseline trust is an owner assumption, never a name-based byte proof.
"""
from __future__ import annotations

from .c5_research_native import digest,require
from .c5_host_observer import validate_snapshot

POLICY='c5-frozen-source-trusted-host-visible-continuity-v2'
ASSUMPTIONS={
    'entire_baseline_host_process_including_opaque_artifacts_is_trusted':True,
    'no_untrusted_or_adversarial_inprocess_code_assumed':True,
    'operator_research_exclusivity_is_required_not_technically_proven':True,
    'reflection_does_not_prove_emitted_bytes_or_causal_origin':True,
    'snapshot_checks_do_not_exclude_transient_between_checkpoint_changes':True,
    'native_image_unverified_categories_are_not_automatically_os_or_benign':True,
    'legacy_complete_byte_closure_remains_false':True,
    'no_product_security_or_default_route_switch_authorized':True,
}


def validate_transition(spec, approval):
    require(isinstance(spec,dict) and spec.get('policy_id')==POLICY
        and spec.get('purpose')=='guarantee_transition_preparation_only_no_execution'
        and spec.get('assumptions')==ASSUMPTIONS
        and all(type(v) is bool for v in spec['assumptions'].values())
        and spec.get('default_admission_enabled') is False
        and spec.get('model_or_fixture_or_holdout_authorized') is False,
        'explicit bounded host-trust transition scope differs')
    require(approval=={'actor':'repository_owner','approved':True,'policy_id':POLICY,
        'transition_spec_sha256':digest(spec),
        'approval_basis':'direct owner acceptance of weaker host assurance and research-exclusive preparation; no study execution'},
        'new direct guarantee transition approval required')
    return {'transition_spec_sha256':digest(spec),'policy_id':POLICY,
        'model_or_fixture_or_holdout_authorized':False,'legacy_byte_closure_verified':False}


def _snapshot(value):
    value=validate_snapshot(value)
    rows=value['assemblies']
    require(len({r['instance_id'] for r in rows})==len(rows),'duplicate baseline CLR instances')
    require(all(r['surface_sha256']==digest({k:v for k,v in r.items() if k!='surface_sha256'})
        for r in rows),'raw assembly surface digest differs')
    return value


def compare_visible_continuity(baseline, observation, events):
    """No new names/instances/surfaces allowed after declared warmup sealing.

    Inputs are raw independently collected records; this verifies internal
    coherence only. Caller still needs actual frozen observer provenance,
    source/host-file byte checks and separately approved study authority.
    """
    baseline,observation=_snapshot(baseline),_snapshot(observation)
    require(isinstance(events,dict) and set(events)=={'events','dropped','errors'}
        and events['events']==[] and type(events['dropped']) is int and events['dropped']==0
        and events['errors']==[],'new/unknown/missing host event after sealed baseline')
    require((baseline['process_identity'],baseline['active_sha256'],baseline['active_serial'])==
        (observation['process_identity'],observation['active_sha256'],observation['active_serial']),
        'trusted host process/document changed')
    for key in ('python_origins','assemblies','native_images','inspection_limits'):
        require(digest(baseline[key])==digest(observation[key]),'visible host continuity changed: '+key)
    require(any(row.get('module')=='clr' for row in baseline['python_origins'])
        and any(row.get('module')=='CLR' for row in baseline['python_origins']),
        'raw CLR bindings missing, not inferable from names')
    return {'policy_id':POLICY,'visible_checkpoint_continuity_verified':True,
        'baseline_snapshot_sha256':digest(baseline),'observed_snapshot_sha256':digest(observation),
        'causal_origin_or_emitted_bytes_proven':False,'legacy_byte_closure_verified':False,
        'continuous_between_checkpoint_integrity_proven':False,'execution_authority':False}
