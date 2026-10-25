"""Complete D public material assembly; never a grant/state/admission maker."""
import hashlib
from pathlib import Path
from training.c5_reuse_freeze_materials import source_payload,write_review
from training.c5_reuse_evidence import canonical,sha,require
from plugin.rhino_listener.c5_followup_profile import STUDY,INSTANCE,SPEC,PLAN,RUNTIME,CONTINUATION,GENESIS
from plugin.rhino_listener.c5_followup_runtime_scope import fixed_paths
from plugin.rhino_listener.c5_followup_scope import resources
from plugin.rhino_listener.c5_followup_predecessor import FAILURES,POLICIES
from training.c5_reuse_field_scope import PROTOCOL,COMPARISON,LIMITS
from training.c5_reuse_development_plan import public_plan
PUBLIC_RECORDS=FAILURES+tuple('eval/c5/reuse-followup-'+x+'-20261012-d.json' for x in
    ('owner-preparation-acceptance','resource-acceptance','admission-genesis','compatible-runtime'))

def build(root,*,environment,model_assets,host_files,host_acceptance,gpu_process,transport,compatible_info):
    root=Path(root);payload=source_payload(root)
    for name in PUBLIC_RECORDS:
        if name.endswith('compatible-runtime-20261012-d.json'):payload[name]=canonical(compatible_info)+b'\n'
        else:payload[name]=(root/name).read_bytes()
    for failure,policy in zip(FAILURES,POLICIES):
        require(hashlib.sha256(payload[failure]).hexdigest()==policy['public_failure_record_raw_sha256'],'followup_original_failure_bytes')
    public=public_plan(root);boundary=resources()
    host={'instance_id':INSTANCE,'accepted_by_owner':True,'acceptance_record_sha256':sha(host_acceptance),
        'readable_files_frozen':True,'opaque_host_trusted':True,'full_byte_closure_claimed':False,
        'baseline_before_generation':True,'new_events_after_baseline_allowed':False,'external_readiness_and_final_capture_required':True}
    spec={'protocol':PROTOCOL,'study_id':STUDY,'phase':'development','instance_id':INSTANCE,'comparison':COMPARISON,
        'limits':LIMITS,'resources':boundary,'host_policy':host,'execution_ready':True,'automatic_retry_allowed':False,
        'private_formal_data_allowed':False,'default_route_change_allowed':False,'development_plan_sha256':public['development_plan_sha256'],
        'continuation':CONTINUATION}
    from plugin.rhino_listener.c5_followup_profile import RESOURCE_ACCEPTANCE
    from training.c5_followup_gpu_loader import LOADER_POLICY
    plan={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'environment':environment,'model_assets':model_assets,
        'host_readable_files':host_files,'host_acceptance':host_acceptance,'gpu_process':gpu_process,'loader_policy':LOADER_POLICY,
        'transport':transport,'resource_basis':{'platform_hour_quota':None,'remaining_gpu_seconds_meaning':'incremental_research_reservation_not_platform_balance',
            'prior_cumulative_upper_bound_basis':'owner_reported_unknown_not_original_16_hour_compliance','resource_revision_acceptance':RESOURCE_ACCEPTANCE},
        'predecessor':POLICIES,'continuation':{'binding':CONTINUATION,'genesis':GENESIS}}
    payload[SPEC]=canonical(spec)+b'\n';payload[PLAN]=canonical(plan)+b'\n'
    files={n:hashlib.sha256(raw).hexdigest() for n,raw in sorted(payload.items())}
    runtime={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'spec_sha256':sha(spec),
        'endpoints':{e:fixed_paths(e) for e in ('mac','gpu')},'source_files':files,'environment_sha256':sha(environment),
        'model_assets_sha256':sha(model_assets),'host_readable_files_sha256':sha(host_files),'host_policy':host,
        'resources':boundary,'execution_ready':True,'continuation':CONTINUATION}
    payload[RUNTIME]=canonical(runtime)+b'\n'
    review={'study_id':STUDY,'instance_id':INSTANCE,'spec_sha256':sha(spec),'runtime_sha256':sha(runtime),
        'source_files':files,'payload_bytes':sum(map(len,payload.values())),'status':'complete_materials_await_independent_deployment_checks_and_exact_approval',
        'owner_exact_execution_approval_received':False,'state_grant_registry_or_model_created':False,'execution_authority':False}
    require(len(files)<=512 and all(len(raw)<=2097152 for raw in payload.values()),'followup_complete_public_packet_bounds')
    return spec,runtime,plan,payload,review
