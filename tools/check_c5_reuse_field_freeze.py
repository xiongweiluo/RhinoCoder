#!/usr/bin/env python3
"""Independent stdlib source/spec/plan/runtime byte and population check.

Run from reviewed checkout, never import staged target code. No grant/state
creation or environment/model loading. Actual installed assets have a separate
read-only receipt check; this tool cannot fabricate missing resource facts.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat

SPEC='eval/c5/reuse-development-spec-20261012-c.json'
RUNTIME='eval/c5/reuse-development-runtime-freeze-20261012-c.json'
PLAN='eval/c5/reuse-field-environment-plan-20261012-c.json'


def require(ok,code):
    if not ok:raise ValueError(code)


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(v):return hashlib.sha256(canonical(v)).hexdigest()


def read(p):
    require(p.is_absolute() and p.resolve()==p,'field_freeze_alias')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd);require(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and a.st_uid==os.getuid()
            and not a.st_mode&0o022 and 0<a.st_size<=2*1024*1024,'field_freeze_file')
        raw=os.pread(fd,a.st_size+1,0);b=os.fstat(fd);c=p.lstat()
        require(len(raw)==a.st_size and all(getattr(a,k)==getattr(b,k)==getattr(c,k)
            for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_nlink')),'field_freeze_race')
        return raw
    finally:os.close(fd)


def decode(raw):
    def pairs(items):
        v={}
        for k,x in items:require(k not in v,'field_freeze_duplicate');v[k]=x
        return v
    def constant(v):raise ValueError('field_freeze_nonfinite')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)


def check(root,spec_sha,runtime_sha,*,review=False):
    root=Path(root);require(root.is_absolute() and root.resolve()==root,'field_freeze_root')
    sraw,rraw,praw=(read(root/n) for n in (SPEC,RUNTIME,PLAN));s,r,p=map(decode,(sraw,rraw,praw))
    require(sha(s)==spec_sha==r['spec_sha256'] and sha(r)==runtime_sha,'field_freeze_two_hash_binding')
    files=r['source_files'];require(type(files) is dict and 0<len(files)<=512,'field_freeze_population')
    expected=set(files)|{RUNTIME}|({'review-materials.json'} if review else set())
    observed=set()
    for directory,dirs,names in os.walk(root,followlinks=False):
        require(all(not (Path(directory)/d).is_symlink() for d in dirs),'field_freeze_symlink_directory')
        observed.update((Path(directory)/n).relative_to(root).as_posix() for n in names)
    require(observed==expected,'field_freeze_extra_or_missing_source')
    for n,value in files.items():
        path=Path(n);require(not path.is_absolute() and '..' not in path.parts and str(path)==n,'field_freeze_name')
        raw=read(root/path);require(hashlib.sha256(raw).hexdigest()==value,'field_freeze_byte_drift')
        if path.suffix=='.py':ast.parse(raw,filename=n,feature_version=(3,9) if n.startswith('plugin/rhino_listener/')
                                      or n in ('tools/run_c5_reuse_rhino_entry.py','tools/run_c5_reuse_rhino_wrapper.py') else (3,11))
    require(hashlib.sha256(sraw).hexdigest()==files[SPEC] and hashlib.sha256(praw).hexdigest()==files[PLAN]
            and sha(p['environment'])==r['environment_sha256'] and sha(p['model_assets'])==r['model_assets_sha256']
            and sha(p['host_readable_files'])==r['host_readable_files_sha256']
            and sha(p['host_acceptance'])==s['host_policy']['acceptance_record_sha256']
            and s['resources']==r['resources'] and s['host_policy']==r['host_policy'],'field_freeze_complete_closures')
    require(all(s[k] is False for k in ('automatic_retry_allowed','private_formal_data_allowed','default_route_change_allowed'))
            and s['host_policy']['full_byte_closure_claimed'] is False,'field_freeze_guarantee_drift')
    if s['instance_id']=='reuse-dev-20261012-c':
        policies=p['predecessor'];require(type(policies) is list and len(policies)==2,'field_freeze_predecessor_population')
        for predecessor,f,status in zip(policies,('eval/c5/reuse-development-startup-failure-20261012.json',
            'eval/c5/reuse-development-preparation-failure-20261012-b.json'),
            ('STARTUP_FAILED_RETIRED_NO_RETRY','PREPARATION_PREFLIGHT_FAILED_RETIRED_NO_RETRY')):
            old=decode(read(root/f))
            require(hashlib.sha256(read(root/f)).hexdigest()==predecessor['public_failure_record_raw_sha256']
                and old['study_id']==predecessor['study_id'] and old['instance_id']==predecessor['instance_id']
                and old['status']==status and old['spec_sha256']==predecessor['spec_sha256']
                and old['runtime_sha256']==predecessor['runtime_sha256']
                and old['pipeline_counts']['model_requests_recorded']==predecessor['recorded_model_requests']==0
                and old['pipeline_counts']['model_native_slots_started']==predecessor['recorded_slots_started']==0
                and old['pipeline_counts']['model_native_slots_completed']==predecessor['recorded_slots_completed']==0
                and predecessor['retired_execution_restore_allowed'] is False
                and predecessor['new_development_requires_new_exact_two_hash_approval'] is True
                and predecessor['formal_consumption_authorized'] is False,'field_freeze_retired_predecessor_binding')
    if s['execution_ready'] is True:
        a=p['resource_basis']['resource_revision_acceptance'];q=s['resources']
        models=p['model_assets'];names={'config.json','generation_config.json','merges.txt','tokenizer.json','tokenizer_config.json','vocab.json'}
        require(models['audit_tokenizer_dir']=='/Users/xiongweiluo/RhinoCoder/data/training/c5/modelbridge-tokenizer/'+s['comparison']['base_revision']
            and set(models['audit_tokenizer_files'])==names
            and models['audit_tokenizer_files']=={n:models['base_files'][n] for n in names},
            'field_freeze_complete_audit_tokenizer_binding')
        require(q['resource_policy']=='incremental_reuse_unknown_history_v1'
            and q['resource_revision_acceptance_sha256']==sha(a)
            and a['scope']=='resource_revision_only_not_execution' and a['accepted'] is True
            and a['exact_two_hash_execution_approval_received'] is False
            and q['prior_cumulative_upper_bound_seconds'] is a['historical_cumulative_upper_bound_seconds'] is None
            and q['original_cumulative_compliance_claimed'] is a['original_16_hour_compliance_claimed'] is False
            and q['development_seconds_max']==a['development_seconds_max']==18000
            and q['formal_seconds_max']==a['formal_seconds_max']==64800
            and q['research_seconds_max']==a['research_seconds_max']==82800
            and q['remaining_gpu_seconds']==82800
            and all(q[k]==a[k] for k in ('lease_expiry_epoch','generation_cutoff_epoch','export_reserve_seconds')),
            'field_freeze_resource_revision_binding')
    return {'source_files_individually_verified':len(files),'source_population_exact':True,
            'complete_closure_binding_verified':True,'candidate_execution_ready':s['execution_ready'] is r['execution_ready'] is True,
            'actual_installed_assets_verified':False,'human_approval_origin_verified':False,'execution_ready':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--spec-sha256',required=True);p.add_argument('--runtime-sha256',required=True)
    p.add_argument('--review',action='store_true');a=p.parse_args()
    print(json.dumps(check(a.root,a.spec_sha256,a.runtime_sha256,review=a.review),sort_keys=True))


if __name__=='__main__':main()
