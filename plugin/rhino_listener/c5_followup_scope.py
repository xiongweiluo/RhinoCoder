"""Exact D-only material binding. Preparation is never an execution grant."""
import math
from pathlib import Path
from .c5_reuse_field_scope import canonical,sha,strict,require,exact,is_sha,PROTOCOL,COMPARISON,LIMITS,APPROVAL_BASIS,endpoint_paths
from .c5_followup_profile import STUDY,INSTANCE,CONTINUATION,RESOURCE_POLICY,RESOURCE_ACCEPTANCE,GENESIS

def resources():
    a=RESOURCE_ACCEPTANCE
    return {'lease_expiry_epoch':a['lease_expiry_epoch'],'generation_cutoff_epoch':a['generation_cutoff_epoch'],
        'export_reserve_seconds':900,'prior_cumulative_upper_bound_seconds':None,'remaining_gpu_seconds':82800,
        'development_seconds_max':18000,'formal_seconds_max':64800,'research_seconds_max':82800,
        'original_cumulative_seconds_max':57600,'resource_policy':RESOURCE_POLICY,
        'resource_revision_acceptance_sha256':sha(a),'original_cumulative_compliance_claimed':False}

def material(spec,runtime,*,now,endpoint,cleanup_only=False):
    exact(spec,('protocol','study_id','phase','instance_id','comparison','limits','resources','host_policy','execution_ready',
        'automatic_retry_allowed','private_formal_data_allowed','default_route_change_allowed','development_plan_sha256','continuation'))
    exact(runtime,('protocol','study_id','instance_id','spec_sha256','endpoints','source_files','environment_sha256',
        'model_assets_sha256','host_readable_files_sha256','host_policy','resources','execution_ready','continuation'))
    require(spec['protocol']==runtime['protocol']==PROTOCOL and spec['study_id']==runtime['study_id']==STUDY
        and spec['instance_id']==runtime['instance_id']==INSTANCE and spec['phase']=='development','followup_fixed_identity')
    require(canonical(spec['comparison'])==canonical(COMPARISON) and canonical(spec['limits'])==canonical(LIMITS)
        and canonical(spec['continuation'])==canonical(runtime['continuation'])==canonical(CONTINUATION),'followup_contract_and_history')
    require(spec['execution_ready'] is runtime['execution_ready'] is True and all(spec[k] is False for k in
        ('automatic_retry_allowed','private_formal_data_allowed','default_route_change_allowed')),'followup_freeze_not_ready')
    require(runtime['spec_sha256']==sha(spec) and is_sha(spec['development_plan_sha256']),'followup_spec_binding')
    require(type(now) in (int,float) and math.isfinite(now) and now>0 and type(cleanup_only) is bool
        and (cleanup_only or now<resources()['generation_cutoff_epoch'])
        and canonical(spec['resources'])==canonical(runtime['resources'])==canonical(resources()),'followup_finite_resource_boundary')
    require(type(runtime['source_files']) is dict and 0<len(runtime['source_files'])<=512
        and all(type(n) is str and not Path(n).is_absolute() and '..' not in Path(n).parts and is_sha(v)
            for n,v in runtime['source_files'].items())
        and all(is_sha(runtime[k]) for k in ('environment_sha256','model_assets_sha256','host_readable_files_sha256')),'followup_complete_freeze')
    h=spec['host_policy'];exact(h,('instance_id','accepted_by_owner','acceptance_record_sha256','readable_files_frozen',
        'opaque_host_trusted','full_byte_closure_claimed','baseline_before_generation','new_events_after_baseline_allowed',
        'external_readiness_and_final_capture_required'))
    require(h['instance_id']==INSTANCE and h['accepted_by_owner'] is h['readable_files_frozen'] is h['opaque_host_trusted'] is True
        and h['baseline_before_generation'] is h['external_readiness_and_final_capture_required'] is True
        and h['full_byte_closure_claimed'] is h['new_events_after_baseline_allowed'] is False
        and is_sha(h['acceptance_record_sha256']) and canonical(runtime['host_policy'])==canonical(h),'followup_host_guarantee')
    require(endpoint in ('mac','gpu'),'followup_endpoint');endpoint_paths(INSTANCE,runtime['endpoints'])
    require({e:runtime['endpoints'][e]['admission_root'] for e in ('mac','gpu')}==GENESIS['global_roots'],'followup_same_global_roots')
    value={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'spec_sha256':sha(spec),'runtime_sha256':sha(runtime),
        'paths':runtime['endpoints'][endpoint],'endpoint':endpoint,'endpoints':runtime['endpoints'],'limits':LIMITS,
        'development_plan_sha256':spec['development_plan_sha256'],'continuation':CONTINUATION,
        'whole_field_authority_verified':False,'approval_origin_verified':False,'record_binding_verified':True}
    return strict(canonical(value))

def bind(spec,runtime,approval,*,now,endpoint,cleanup_only=False):
    value=material(spec,runtime,now=now,endpoint=endpoint,cleanup_only=cleanup_only)
    expected={'study_id':STUDY,'instance_id':INSTANCE,'actor':'repository_owner','approved':True,
        'spec_sha256':sha(spec),'runtime_sha256':sha(runtime),'approval_basis':APPROVAL_BASIS}
    require(canonical(approval)==canonical(expected),'followup_new_exact_owner_approval');return value

def validate(value):
    exact(value,('protocol','study_id','instance_id','spec_sha256','runtime_sha256','paths','limits','development_plan_sha256',
        'whole_field_authority_verified','approval_origin_verified','record_binding_verified','endpoint','endpoints','continuation'))
    require(value['protocol']==PROTOCOL and value['study_id']==STUDY and value['instance_id']==INSTANCE
        and canonical(value['continuation'])==canonical(CONTINUATION) and canonical(value['limits'])==canonical(LIMITS)
        and all(is_sha(value[k]) for k in ('spec_sha256','runtime_sha256','development_plan_sha256'))
        and value['whole_field_authority_verified'] is value['approval_origin_verified'] is False
        and value['record_binding_verified'] is True and value['endpoint'] in ('mac','gpu'),'followup_binding')
    endpoint_paths(INSTANCE,value['endpoints'])
    require(value['paths']==value['endpoints'][value['endpoint']] and
        {e:value['endpoints'][e]['admission_root'] for e in ('mac','gpu')}==GENESIS['global_roots'],'followup_binding_global_roots')
