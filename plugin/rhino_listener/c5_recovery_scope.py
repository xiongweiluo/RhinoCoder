"""Rhino 3.9-safe per-attempt binding; fixed campaign, no legacy reopening."""
import math
from pathlib import Path
from .c5_reuse_field_scope import canonical,sha,strict,require,exact,is_sha,PROTOCOL,COMPARISON,LIMITS
from .c5_recovery_profile import STUDY,INSTANCE,POLICY,RECOVERY_POLICY

PARENTS={'mac':'/Users/xiongweiluo/RhinoCoder/data/training/c5','gpu':'/data'}
def paths(endpoint,attempt,runtime_sha256=None):
    require(endpoint in PARENTS and type(attempt) is int and 1<=attempt<=3,'recovery_fixed_attempt')
    require(runtime_sha256 is None or is_sha(runtime_sha256),'recovery_revision_path_hash')
    parent=Path(PARENTS[endpoint])
    leaf='attempt-'+str(attempt)+(('-'+runtime_sha256) if runtime_sha256 is not None else '')
    return {'source_root':str(parent/(INSTANCE+'-source')),
            'state_root':str(parent/(INSTANCE+'-state')/leaf),
            'admission_root':str(parent/'c5-reuse-global-admission-v1')}

def campaign_scope(spec,runtime):
    return {'campaign_id':STUDY,'phase':'public_engineering','spec_sha256':sha(spec),
        'runtime_sha256':sha(runtime),'policy_sha256':sha(spec['recovery']['policy']),
        'history_sha256':spec['recovery']['history_sha256'],
        'public_plan_sha256':spec['development_plan_sha256'],'contract_sha256':sha(COMPARISON),
        'development_seconds_max':spec['resources']['development_seconds_max'],
        'generation_cutoff_epoch':spec['resources']['generation_cutoff_epoch']}

def material(spec,runtime,*,endpoint,attempt,now,cleanup_only=False):
    exact(spec,('protocol','study_id','instance_id','phase','comparison','limits','resources','host_policy',
        'development_plan_sha256','recovery','execution_ready','private_formal_data_allowed','default_route_change_allowed'))
    exact(runtime,('protocol','study_id','instance_id','spec_sha256','source_files','environment_sha256',
        'model_assets_sha256','host_readable_files_sha256','resources','recovery','execution_ready'))
    require(spec['protocol']==runtime['protocol']==PROTOCOL and spec['study_id']==runtime['study_id']==STUDY
        and spec['instance_id']==runtime['instance_id']==INSTANCE and spec['phase']=='development'
        and spec['comparison']==COMPARISON and spec['limits']==LIMITS,'recovery_field_identity_contract')
    r=spec['recovery']
    exact(r,('policy','history_sha256','public_attempts_max','minimum_attempt_window_seconds',
        'all_attempts_disclosed','owner_confirmation_before_loading','new_blind_holdout_claimed','previous_campaign_head_sha256'))
    require(r['policy']==RECOVERY_POLICY and r['public_attempts_max']==3
        and r['all_attempts_disclosed'] is r['owner_confirmation_before_loading'] is True
        and r['new_blind_holdout_claimed'] is False and is_sha(r['history_sha256'])
        and (r['previous_campaign_head_sha256'] is None or is_sha(r['previous_campaign_head_sha256']))
        and type(r['minimum_attempt_window_seconds']) is int
        and 60<r['minimum_attempt_window_seconds']<=18000,'recovery_field_retry_boundary')
    require(runtime['recovery']==r and runtime['resources']==spec['resources'] and runtime['spec_sha256']==sha(spec)
        and spec['execution_ready'] is runtime['execution_ready'] is True
        and spec['private_formal_data_allowed'] is spec['default_route_change_allowed'] is False,
        'recovery_field_complete_freeze_required')
    require(all(is_sha(runtime[k]) for k in ('environment_sha256','model_assets_sha256','host_readable_files_sha256'))
        and is_sha(spec['development_plan_sha256']) and type(runtime['source_files']) is dict
        and 1<=len(runtime['source_files'])<=512
        and all(type(n) is str and not Path(n).is_absolute() and '..' not in Path(n).parts
                and str(Path(n))==n and is_sha(h) for n,h in runtime['source_files'].items()),
        'recovery_field_source_closure')
    resources=spec['resources']
    exact(resources,('lease_expiry_epoch','generation_cutoff_epoch','export_reserve_seconds',
        'development_seconds_max','formal_seconds_max','research_seconds_max',
        'historical_cumulative_upper_bound_seconds','original_16_hour_compliance_claimed',
        'old_budget_recredited','unused_development_transferred_to_formal','actual_lease_basis'))
    require(resources['development_seconds_max']==18000 and resources['formal_seconds_max']==64800
        and resources['research_seconds_max']==82800 and resources['export_reserve_seconds']==900
        and resources['historical_cumulative_upper_bound_seconds'] is None
        and all(resources[k] is False for k in ('original_16_hour_compliance_claimed',
                        'old_budget_recredited','unused_development_transferred_to_formal'))
        and all(type(resources[k]) in (int,float) and math.isfinite(resources[k]) and resources[k]>0
                for k in ('lease_expiry_epoch','generation_cutoff_epoch'))
        and resources['lease_expiry_epoch']-resources['generation_cutoff_epoch']==900
        and type(resources['actual_lease_basis']) is str and bool(resources['actual_lease_basis']),
        'recovery_actual_finite_lease_required')
    require(type(now) in (int,float) and math.isfinite(now) and now>0
        and type(cleanup_only) is bool and (cleanup_only or now<resources['generation_cutoff_epoch']),
        'recovery_lease_cutoff')
    host=spec['host_policy']
    exact(host,('instance_id','accepted_by_owner','acceptance_record_sha256','readable_files_frozen',
        'opaque_host_trusted','full_byte_closure_claimed','baseline_before_generation',
        'new_events_after_baseline_allowed','external_readiness_and_final_capture_required'))
    require(host['instance_id']==INSTANCE and is_sha(host['acceptance_record_sha256'])
        and all(host[k] is True for k in ('accepted_by_owner','readable_files_frozen','opaque_host_trusted',
                        'baseline_before_generation','external_readiness_and_final_capture_required'))
        and host['full_byte_closure_claimed'] is host['new_events_after_baseline_allowed'] is False,
        'recovery_host_guarantee')
    binding={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'spec_sha256':sha(spec),
        'runtime_sha256':sha(runtime),'development_plan_sha256':spec['development_plan_sha256'],
        'limits':LIMITS,'endpoint':endpoint,'paths':paths(endpoint,attempt,sha(runtime)),
        'endpoints':{e:paths(e,attempt,sha(runtime)) for e in PARENTS},'recovery':{'scope':campaign_scope(spec,runtime),'attempt':attempt},
        'whole_field_authority_verified':False,'approval_origin_verified':False,'record_binding_verified':True}
    validate(binding)
    return strict(canonical(binding))

def validate(value):
    exact(value,('protocol','study_id','instance_id','spec_sha256','runtime_sha256','paths','limits',
        'development_plan_sha256','whole_field_authority_verified','approval_origin_verified',
        'record_binding_verified','endpoint','endpoints','recovery'))
    r=value['recovery'];exact(r,('scope','attempt'));s=r['scope']
    exact(s,('campaign_id','phase','spec_sha256','runtime_sha256','policy_sha256','history_sha256',
        'public_plan_sha256','contract_sha256','development_seconds_max','generation_cutoff_epoch'))
    require(value['protocol']==PROTOCOL and value['study_id']==s['campaign_id']==STUDY
        and value['instance_id']==INSTANCE and s['phase']=='public_engineering'
        and s['spec_sha256']==value['spec_sha256'] and s['runtime_sha256']==value['runtime_sha256']
        and s['public_plan_sha256']==value['development_plan_sha256'] and s['contract_sha256']==sha(COMPARISON) and s['policy_sha256']==sha(RECOVERY_POLICY)
        and all(is_sha(s[k]) for k in ('spec_sha256','runtime_sha256','policy_sha256','history_sha256',
                'public_plan_sha256','contract_sha256')) and s['development_seconds_max']==18000
        and type(s['generation_cutoff_epoch']) in (int,float) and math.isfinite(s['generation_cutoff_epoch'])
        and s['generation_cutoff_epoch']>0 and value['limits']==LIMITS
        and value['whole_field_authority_verified'] is value['approval_origin_verified'] is False
        and value['record_binding_verified'] is True and value['endpoint'] in PARENTS
        and value['endpoints']=={e:paths(e,r['attempt'],value['runtime_sha256']) for e in PARENTS}
        and value['paths']==paths(value['endpoint'],r['attempt'],value['runtime_sha256']),'recovery_field_binding')

def validate_preload_begin(binding,value):
    """Machine ready join under PRE-LOAD human permission; no owner ready forged."""
    validate(binding)
    exact(value,('kind','protocol','scope_sha256','preload_snapshot','preload_receipt',
                 'host_baseline_head_sha256','worker_readiness_sha256'))
    from .c5_reuse_field_scope import common_scope
    snap=value['preload_snapshot'];receipt=value['preload_receipt']
    exact(snap,('scope_sha256','host_preload_anchor_sha256','nonce_sha256'))
    expected={'actor':'repository_owner',**snap,'before_model_loading':True,
              'public_attempts_authorized':3,'human_origin_cryptographically_proven':False}
    require(value['kind']=='reuse_begin_after_preload_confirmation' and value['protocol']==PROTOCOL
        and value['scope_sha256']==sha(common_scope(binding))
        and snap['scope_sha256']==sha(binding['recovery']['scope'])
        and all(is_sha(h) for h in snap.values()) and receipt==expected
        and is_sha(value['host_baseline_head_sha256']) and is_sha(value['worker_readiness_sha256']),
        'recovery_preload_begin_binding')
    return receipt
