#!/usr/bin/env python3
"""Inert package/freeze assembler and checker. Never grants or launches actors.

Missing remote exit/asset evidence stays disabled. Historical r1 material is
read verbatim; only new package documents are written.
"""
import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_run_package_policy import POLICY,LAYOUT_FILE,validate_layout,validate_migration
from plugin.rhino_listener.c5_research_native import digest,require,NativeError

PACKAGE='reuse-formal-20261023-r2'
SPEC='eval/c5/'+PACKAGE+'-spec.json'
RUNTIME='eval/c5/'+PACKAGE+'-runtime.json'
REVIEW='eval/c5/formal-run-package-review-20261023.json'
FACTS='eval/c5/formal-run-package-facts-20261023.json'
PREVIOUS='eval/c5/formal-run-package-prior-public-evidence-20261023.json'


def encoded(value):
    return (json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()


def read(name):return json.loads((ROOT/name).read_bytes())


def assemble():
    spec=copy.deepcopy(read('eval/c5/formal-reuse-spec-20261022-r1.json'))
    freeze=copy.deepcopy(read('eval/c5/formal-reuse-runtime-freeze-20261022-r1.json'))
    facts=read(FACTS);previous=read(PREVIOUS)
    layout={'schema_version':1,'package_id':PACKAGE,'study_id':POLICY['study_id'],
        'mac_source_root':'/Users/xiongweiluo/RhinoCoder/data/training/c5/'+PACKAGE+'-source',
        'gpu_source_root':'/data/'+PACKAGE+'-source',
        'mac_state_root':'/Users/xiongweiluo/RhinoCoder/data/training/c5/'+PACKAGE+'-state',
        'gpu_state_root':'/data/'+PACKAGE+'-state','spec_file':SPEC,'runtime_file':RUNTIME,
        'policy_sha256':digest(POLICY)}
    validate_layout(layout)
    package={'policy':POLICY,'layout':layout,'timing_migration':previous['timing_migration'],
        'prior_campaign_events':previous['prior_campaign_events'],
        'previous_mac_source_root':previous['mac_source_root'],
        'previous_gpu_source_root':previous['gpu_source_root'],
        'previous_mac_attempt_root':previous['mac_attempt_root'],
        'previous_public_source_files':previous['public_source_files'],
        'previous_release_observation_file_sha256':previous.get('release_observation_file_sha256'),
        'lease_expiry_epoch':spec['lease_expiry_epoch']}
    blockers=[key for key in ('previous_qualified_exit_and_raw_audit','current_idle_gpu_full_assets',
        'new_loader_cpu_closure','new_mac_cpu_closure','both_public_deployments','independent_public_readback')
        if facts.get(key) is not True]
    try:validate_migration(package['timing_migration'])
    except (ValueError,AssertionError,NativeError):blockers.append('complete_nonretroactive_timing_migration')
    ready=not blockers
    code_revision=facts.get('source_code_revision')
    spec.update(instance_id=PACKAGE,run_package=package,automatic_retry_allowed=True,
        execution_ready=ready,state='complete_run_package_awaiting_owner_approval' if ready else 'disabled_run_package_preparation',
        formal_gpu_seconds_max=POLICY['gpu_residency_seconds_max'],
        preexposure_operational_attempts_max=POLICY['global_preexposure_loads_max'],
        next_preexposure_attempt=previous['attempts_consumed']+1,
        mac_source_root=layout['mac_source_root'],remote_source_root=layout['gpu_source_root'],
        mac_state_root=layout['mac_state_root'],remote_state_root=layout['gpu_state_root'],
        deployment_revision=code_revision)
    spec['observer_backend']['code_read_roots']=[layout['mac_source_root'] if x.startswith(
        '/Users/xiongweiluo/RhinoCoder/data/training/c5/') else x for x in spec['observer_backend']['code_read_roots']]
    spec['entry_return_wrapper']='#! python 3\nimport runpy\nrunpy.run_path('+repr(layout['mac_source_root']+
        '/tools/c5_rhino_run_package.py')+', run_name="__main__")\n'
    spec['entry_return_wrapper_template']=spec['entry_return_wrapper']
    docs={SPEC:spec,LAYOUT_FILE:layout}
    source=set(freeze['source_files'])|{SPEC,LAYOUT_FILE,PREVIOUS,FACTS}
    source|={p.relative_to(ROOT).as_posix() for folder in ('training','tools','plugin/rhino_listener')
        for p in (ROOT/folder).glob('*.py') if any(x in p.name for x in ('formal_reuse','formal_run','run_package'))}
    # Source revision is checked against actual Python bytes, not an arbitrary SHA string.
    for name in sorted(source):
        if name.endswith('.py'):
            p=subprocess.run(['git','show',str(code_revision)+':'+name],cwd=ROOT,capture_output=True)
            if p.returncode or p.stdout!=(ROOT/name).read_bytes():
                blockers.append('source_code_commit');break
    ready=not blockers;spec.update(execution_ready=ready,state='complete_run_package_awaiting_owner_approval'
        if ready else 'disabled_run_package_preparation')
    pins={n:hashlib.sha256(encoded(docs[n]) if n in docs else (ROOT/n).read_bytes()).hexdigest() for n in sorted(source)}
    freeze.update(instance_id=PACKAGE,run_package=package,execution_ready=ready,
        spec_sha256=digest(spec),spec_file_sha256=pins[SPEC],source_files=pins,
        source_inventory_sha256=digest(pins),source_revision=code_revision,
        mac_source_root=layout['mac_source_root'],remote_source_root=layout['gpu_source_root'],
        current_gpu_full_bytes_verified=facts.get('current_idle_gpu_full_assets') is True,
        current_mac_full_bytes_verified=facts.get('new_mac_cpu_closure') is True,
        actual_public_deployment_both_endpoints_verified=facts.get('both_public_deployments') is True)
    freeze['fixed_public_files']={n:pins[n] for n in set(freeze['fixed_public_files'])|{SPEC,LAYOUT_FILE,PREVIOUS,FACTS}}
    from training.c5_formal_reuse_control import code_closure
    freeze['control_source_files']=code_closure(ROOT,'tools/c5_formal_reuse_control.py',pins)
    docs[RUNTIME]=freeze
    docs[REVIEW]={'schema_version':1,'status':'COMPLETE_AWAITING_SINGLE_RULE_PACKAGE_HASH_REVIEW' if ready else
        'DISABLED_PREPARATION_PENDING_ACTUAL_EVIDENCE','package_id':PACKAGE,'study_id':POLICY['study_id'],
        'spec_sha256':digest(spec),'runtime_sha256':digest(freeze),'source_inventory_sha256':digest(pins),
        'source_files':len(pins),'source_revision':code_revision,'blockers':sorted(set(blockers)),
        'hashes_are_execution_approval_objects':ready,'rule_package_approval_received':False,
        'actual_execution_separately_approved':False,'new_grant_or_campaign_created':False,
        'old_sources_modified':False,'private_formal_reads':0,'ci_policy':'one_PR_run_impact_selected; main_full',
        'legacy_first_load_epoch':previous['timing_migration']['legacy_first_load_epoch'],
        'attempts_consumed':previous['attempts_consumed'],'global_attempts_max_proposed':5,
        'package_attempts_max_proposed':3,'new_independent_holdout_claimed':False}
    return docs


def verify_historical_package():
    """r2 was executed and frozen: check its bytes, never regenerate with new code."""
    spec,freeze=read(SPEC),read(RUNTIME)
    require(digest(spec)=='dff43f351b64159341c363c5156578c9da0ad3820a20d8a9baa46c7cde18d9c1'
        and digest(freeze)=='8f946c2efd02397e04e1fbc143410785371d82748a84c1939f334ba866e495ed',
        'run_package_historical_approved_pair_changed')
    for name,sha in freeze['source_files'].items():
        if name.endswith('.py'):
            result=subprocess.run(['git','show',freeze['source_revision']+':'+name],cwd=ROOT,capture_output=True)
            require(result.returncode==0,'run_package_historical_commit_missing')
            raw=result.stdout
        else:
            path=ROOT/('eval/c5/formal-run-package-layout-20261023.json' if name==LAYOUT_FILE else name)
            raw=path.read_bytes()
        require(hashlib.sha256(raw).hexdigest()==sha,'run_package_historical_source_bytes:'+name)
    return {'status':'original_executed_r2_artifacts_verified_without_regeneration',
        'spec_sha256':digest(spec),'runtime_sha256':digest(freeze),
        'historical_source_revision':freeze['source_revision'],'field_execution_authority':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');a=p.parse_args()
    if a.check:
        print(json.dumps(verify_historical_package(),sort_keys=True));return
    docs=assemble()
    for name,value in docs.items():
        path=ROOT/('eval/c5/formal-run-package-layout-20261023.json' if name==LAYOUT_FILE else name);raw=encoded(value)
        if a.check:require(path.read_bytes()==raw,'run_package_saved_candidate_drift:'+name)
        else:path.write_bytes(raw)
    print(json.dumps(docs[REVIEW],sort_keys=True))


if __name__=='__main__':main()
