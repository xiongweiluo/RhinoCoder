"""Complete public source material builder; unknown facts remain disabled.

No state, owner grant, keys, model loading, host subscription or remote write.
Only public code/assets receipts are supplied. Staging and independent actual
byte recheck are separate; a candidate package never certifies live readiness.
"""
import hashlib
import math
from pathlib import Path
import subprocess
from plugin.rhino_listener.c5_reuse_runtime_scope import INSTANCE,SPEC,RUNTIME,PLAN,fixed_paths,read_bytes
from plugin.rhino_listener.c5_reuse_public_plan import public_plan,SOURCE
from training.c5_reuse_field_scope import STUDY,PROTOCOL,COMPARISON,LIMITS,RESOURCE_POLICY,RESOURCE_ACCEPTANCE
from training.c5_reuse_evidence import canonical,require,sha,strict
from training.c5_reuse_gpu_loader import PYTHON,ENTRY,LOADER_POLICY,ADAPTER,SNAPSHOT,MANIFEST_SHA,ADAPTER_FILES
from training.c5_reuse_owned_child import POLICY as STOP

from plugin.rhino_listener.c5_reuse_predecessor import FAILURES,POLICIES as PREDECESSOR

JSON_FILES=(SOURCE,'eval/c5/rhino-runtime-schema-v1.json','eval/c5/c5-engineering-config.json')+FAILURES
ENTRIES=('tools/run_c5_reuse_gpu_entry.py','tools/run_c5_reuse_mac_entry.py',
         'tools/run_c5_reuse_rhino_entry.py','tools/run_c5_reuse_rhino_wrapper.py')


def source_payload(root):
    root=Path(root)
    result=subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard','--',
        'agent/*.py','training/*.py','plugin/*.py','tools/*.py','data_pipeline/*.py'],cwd=root,capture_output=True,check=True)
    names=set(result.stdout.decode().rstrip('\0').split('\0'))|set(JSON_FILES)|{'requirements.txt','requirements-training.txt'}
    require(set(ENTRIES)<=names and 0<len(names)<=510,'reuse_freeze_source_population')
    return {name:read_bytes(root/name) for name in sorted(names)}


def build(root,*,environment,model_assets,host_files,host_acceptance,gpu_process,transport,
          prior_upper=None,prior_basis=None,current_gpu_independently_rechecked=False,resource_acceptance=None):
    require(type(current_gpu_independently_rechecked) is bool,'reuse_freeze_fact_flag')
    require(prior_upper is prior_basis is None,'reuse_freeze_history_remains_unknown')
    if resource_acceptance is not None:
        require(canonical(resource_acceptance)==canonical(RESOURCE_ACCEPTANCE),'reuse_freeze_resource_acceptance')
    payload=source_payload(root);public=public_plan(Path(root))
    for failure,policy in zip(FAILURES,PREDECESSOR):
        require(hashlib.sha256(payload[failure]).hexdigest()==policy['public_failure_record_raw_sha256'],
                'reuse_freeze_original_failure_bytes')
    resources={'lease_expiry_epoch':1791914400,'generation_cutoff_epoch':1791913500,'export_reserve_seconds':900,
        'prior_cumulative_upper_bound_seconds':None,'remaining_gpu_seconds':82800,
        'development_seconds_max':18000,'formal_seconds_max':64800,'research_seconds_max':82800,
        'original_cumulative_seconds_max':57600,'resource_policy':RESOURCE_POLICY,
        'resource_revision_acceptance_sha256':sha(RESOURCE_ACCEPTANCE),'original_cumulative_compliance_claimed':False}
    host={'instance_id':INSTANCE,'accepted_by_owner':True,'acceptance_record_sha256':sha(host_acceptance),
        'readable_files_frozen':True,'opaque_host_trusted':True,'full_byte_closure_claimed':False,
        'baseline_before_generation':True,'new_events_after_baseline_allowed':False,
        'external_readiness_and_final_capture_required':True}
    ready=resource_acceptance is not None and current_gpu_independently_rechecked
    spec={'protocol':PROTOCOL,'study_id':STUDY,'phase':'development','instance_id':INSTANCE,
        'comparison':COMPARISON,'limits':LIMITS,'resources':resources,'host_policy':host,
        'execution_ready':ready,'automatic_retry_allowed':False,'private_formal_data_allowed':False,
        'default_route_change_allowed':False,'development_plan_sha256':public['development_plan_sha256']}
    plan={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'environment':environment,
        'model_assets':model_assets,'host_readable_files':host_files,'gpu_process':gpu_process,
        'loader_policy':LOADER_POLICY,'transport':transport,'host_acceptance':host_acceptance,
        'resource_basis':{'platform_hour_quota':None,
            'remaining_gpu_seconds_meaning':'incremental_research_reservation_not_platform_balance',
            'prior_cumulative_upper_bound_basis':'owner_reported_unknown_not_original_16_hour_compliance',
            'resource_revision_acceptance':resource_acceptance},'predecessor':PREDECESSOR}
    payload[SPEC]=canonical(spec)+b'\n';payload[PLAN]=canonical(plan)+b'\n'
    source={n:hashlib.sha256(raw).hexdigest() for n,raw in sorted(payload.items())}
    runtime={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':INSTANCE,'spec_sha256':sha(spec),
        'endpoints':{e:fixed_paths(e) for e in ('mac','gpu')},'source_files':source,
        'environment_sha256':sha(environment),'model_assets_sha256':sha(model_assets),
        'host_readable_files_sha256':sha(host_files),'host_policy':host,'resources':resources,'execution_ready':ready}
    payload[RUNTIME]=canonical(runtime)+b'\n'
    packet={'study_id':STUDY,'instance_id':INSTANCE,'status':'candidate_materials_not_execution_approval',
        'spec_sha256':sha(spec),'runtime_sha256':sha(runtime),'spec_raw_sha256':source[SPEC],
        'runtime_raw_sha256':hashlib.sha256(payload[RUNTIME]).hexdigest(),
        'source_files':source,'payload_bytes':sum(len(v) for v in payload.values()),
        'pending_facts':(['explicit_resource_revision_acceptance'] if resource_acceptance is None else [])+
                        ([] if current_gpu_independently_rechecked else ['fresh_actual_gpu_bytes_and_deployment']),
        'actual_mac_and_gpu_deployment_independently_checked':False,'exact_owner_approval_received':False,
        'model_calls':0,'rhino_calls':0,'private_formal_reads':0,'execution_ready':False}
    return spec,runtime,plan,payload,packet


def write_review(destination,payload,packet):
    destination=Path(destination);require(destination.is_absolute() and destination.resolve()==destination,'reuse_review_path')
    destination.mkdir(mode=0o700)
    for name,raw in payload.items():
        p=destination/name;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as stream:stream.write(raw)
        p.chmod(0o600)
    p=destination/'review-materials.json'
    with p.open('xb') as stream:stream.write(canonical(packet)+b'\n')
    p.chmod(0o600)
    return destination
