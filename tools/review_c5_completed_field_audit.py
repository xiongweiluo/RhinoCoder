#!/usr/bin/env python3
"""Separate post-execution audit; original frozen verifier/source remain intact.

A reviewed GPU validator checks the actual elapsed/minimum bounds. The joint
validator is detached with copied globals; no frozen module is monkeypatched.
Original rejection is retained, and supplemental PASS is NOT original PASS.
Owner acceptance remains necessary before using this revision as a formal gate.
No SSH, model, Rhino operation, grant, consumption or producer write exists.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import FunctionType
REVIEW=Path(__file__).resolve().parents[1]
FIELD=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-recovery-20261013-source')
MANIFEST='eval/c5/recovery-completed-audit-source-review-20261014.json'
SPEC_SHA='82b919bc1aca6c9d35436b374009d23ecb50ec3b9c91cae75d62eb2e6fcae6dc'
RUNTIME_SHA='c0dfc0e1e0499966af2f24bc095bc447a71e3ebccb88568cba19d7d14d35dcd2'
def read(p):return json.loads(Path(p).read_bytes())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def origin_path(module,modules,require):
    """Bind the two real PyTorch virtual namespaces to their defining source.

    These are exact typed singleton objects, not arbitrary relative origins.
    The defining Python and every loaded native module remain byte-checked.
    """
    name=vars(module).get('__name__')
    rules={'torch.ops':('torch._ops','_Ops','_ops.py','ops'),
           'torch.classes':('torch._classes','_Classes','_classes.py','classes')}
    if name in rules:
        owner_name,cls,sentinel,attribute=rules[name];owner=modules.get(owner_name);torch=modules.get('torch')
        require(owner is not None and torch is not None and modules.get(name) is module
            and type(module) is vars(owner).get(cls) and vars(torch).get(attribute) is module
            and getattr(module,'__file__',None)==sentinel,'review_virtual_namespace_identity')
        origin=getattr(owner,'__file__',None)
    else:origin=getattr(module,'__file__',None)
    if not origin or str(origin).startswith('<'):return None
    p=Path(origin)
    if p.suffix=='.pyc':p=Path(importlib.util.source_from_cache(str(p)))
    require(p.is_absolute(),'review_unresolved_loaded_origin');return p.resolve()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--components',action='store_true');args=parser.parse_args()
    sys.path.insert(0,str(FIELD))
    from plugin.rhino_listener.c5_recovery_runtime_scope import approved_entry
    from plugin.rhino_listener.c5_recovery_scope import material
    from plugin.rhino_listener.c5_followup_mac_scope import code_sha,verify_process_identity,verify_audit_tokenizer,MAC_CACHE
    from plugin.rhino_listener.c5_reuse_public_plan import public_plan,SOURCE
    from plugin.rhino_listener.c5_research_channel import read_json
    from training.c5_reuse_evidence import sha,require,canonical
    from training.c5_reuse_field_journal import read_record,read_journal
    from training.c5_reuse_control_journal import read_control
    from training.c5_reuse_native_audit import audit_native_eight
    from training.c5_recovery_field_gpu_audit import audit_gpu_entry as frozen_gpu
    from training.c5_reuse_field_transport_audit import audit_join
    from training.c5_recovery_field_eight_audit import audit_field_eight as frozen_joint
    from training.c5_execution import load_pinned_tokenizer,load_config
    s,r,b,plan,h,grant,field_guard=approved_entry(FIELD,'mac',3,cleanup_only=True)
    require(sha(s)==SPEC_SHA and sha(r)==RUNTIME_SHA,'review_exact_original_field_required')
    manifest=read(REVIEW/MANIFEST);require(manifest['original_spec_sha256']==SPEC_SHA and manifest['original_runtime_sha256']==RUNTIME_SHA,'review_manifest_field_binding')
    pins=manifest['review_source_files'];require(set(pins)=={'training/c5_completed_field_gpu_audit.py','tools/review_c5_completed_field_audit.py','eval/test_c5_completed_field_audit.py','eval/c5/recovery-attempt3-budget-audit-regression-20261014.json'},'review_closed_additional_sources')
    require(sys.pycache_prefix==MAC_CACHE and not os.path.lexists(MAC_CACHE) and Path(sys.prefix).resolve()==Path('/opt/anaconda3') and sys.version==plan['environment']['mac']['python'],'review_original_cpu_interpreter')
    verify_process_identity(plan['host_acceptance']['process_observation'],embedded=False)
    def guard():
        field_guard(cleanup_only=True)
        require(all(digest(REVIEW/n)==v for n,v in pins.items()),'review_additional_source_drift')
        for files in (plan['host_readable_files'],plan['environment']['mac']['file_sha256']):
            require(all(code_sha(p)==v for p,v in files.items()),'review_original_readable_environment_drift')
        verify_audit_tokenizer(plan['model_assets'])
        for m in tuple(sys.modules.values()):
            p=origin_path(m,sys.modules,require)
            if p is None:continue
            if p.is_relative_to(FIELD):require(p.relative_to(FIELD).as_posix() in r['source_files'],'review_unregistered_original_project_origin')
            elif p.is_relative_to(REVIEW):require(p.relative_to(REVIEW).as_posix() in pins,'review_unregistered_additional_origin')
            else:require(str(p) in plan['environment']['mac']['file_sha256'] and code_sha(p)==plan['environment']['mac']['file_sha256'][str(p)],'review_foreign_loaded_environment')
    guard()
    path=REVIEW/'training/c5_completed_field_gpu_audit.py';spec=importlib.util.spec_from_file_location('completed_review_gpu_checker',path);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    S=Path(b['paths']['state_root']);owner=S.parent/'owner-custody';export_raw=(S/'gpu-public-eight-raw-export.json').read_bytes();export=json.loads(export_raw);require(export_raw==canonical(export)+b'\n','review_original_export_serialization')
    gpu=material(s,r,now=time.time(),endpoint='gpu',attempt=3,cleanup_only=True);require(export['binding']==gpu,'review_original_gpu_binding')
    native=[read_record(S/'native-controller','raw-%04d.json'%i)[0] for i in range(len(list((S/'native-controller').iterdir())))];nh=native[-1]['record_sha256'];names=sorted((S/'controller').glob('raw-*.json'));ch=read_record(S/'controller',names[-1].name)[0]['record_sha256'];controller=read_journal(S/'controller',b,'controller',ch)
    public=public_plan(FIELD);slots={}
    for slot in public['order']:
        key=read_json(S/'audit-key-custody',slot+'.json');require(key['runtime_sha256']==RUNTIME_SHA,'review_original_fixture_key_scope');d=S/slot;slots[slot]={'secret':bytes.fromhex(key['key_hex']),'consent_path':d/'consent.sqlite3','ledger_path':d/'fixture.sqlite3'}
    hk=read_json(S/'audit-key-custody','hub.json');require(hk['runtime_sha256']==RUNTIME_SHA,'review_original_hub_key_scope');secret=bytes.fromhex(hk['key_hex']);terminal=read_json(S,'host-continuity-terminal-receipt.json')
    tok=load_pinned_tokenizer(FIELD.parent/'modelbridge-tokenizer'/s['comparison']['base_revision'],config=load_config(FIELD/'eval/c5/c5-engineering-config.json'))
    entry_args=(export['supervisor'],export['lifecycle'],export['worker'],gpu,plan,s['resources']);entry_kwargs={'spec':s,'runtime':r,'plan_raw':(FIELD/'eval/c5/recovery-environment-plan-20261013.json').read_bytes(),'supervisor_head':export['supervisor_head'],'lifecycle_head':export['lifecycle_head'],'worker_head':export['worker_head'],'plans':public['task_plans'],'tokenizer':tok}
    try:frozen_gpu(*entry_args,**entry_kwargs)
    except ValueError as error:require(str(error)=='recovery_audit_shared_wall_budget','review_unexpected_original_verifier_failure');original_rejection=str(error)
    else:raise ValueError('review_original_rejection_not_reproduced')
    entry=module.audit_gpu_entry(*entry_args,**entry_kwargs)
    wire=audit_join(controller,export['worker'],b,gpu,ch,export['worker_head'],public['task_plans'],tok)
    geometry=audit_native_eight(native,b,nh,controller,ch,public,read(FIELD/'eval/c5/rhino-runtime-schema-v1.json')['core_parameters'],slots,secret,source_files=r['source_files'],external_host_seal_sha256=terminal['seal_sha256'],write_assertions=read(FIELD/SOURCE)['independent_write_assertions'])
    result={'status':'SUPPLEMENTAL_COMPONENTS_COMPLETE_OWNER_FINAL_JOINT_PENDING','gpu_entry':entry,'wire_join':wire,'native':geometry}
    if not args.components:
        external=read_json(owner,'owner-final-attempt-3.json')
        from training.c5_recovery_history import open_campaign
        log=open_campaign(b['paths']['admission_root'],'mac',b['recovery']['scope'],h)
        try:initial,rows=log.binding,log.rows()
        finally:log.close()
        globals_copy=dict(frozen_joint.__globals__);globals_copy['audit_gpu_entry']=module.audit_gpu_entry
        joint=FunctionType(frozen_joint.__code__,globals_copy,'supplemental_completed_joint_audit')
        require(frozen_joint.__globals__['audit_gpu_entry'] is frozen_gpu,'review_frozen_module_was_modified')
        result=joint(mac=b,gpu=gpu,spec=s,runtime=r,plan=plan,plan_raw=(FIELD/'eval/c5/recovery-environment-plan-20261013.json').read_bytes(),controller=controller,controller_head=ch,export=export,native=native,native_head=nh,public=public,schemas=read(FIELD/'eval/c5/rhino-runtime-schema-v1.json')['core_parameters'],slot_inputs=slots,hub_secret=secret,tokenizer=tok,external=external,write_assertions=read(FIELD/SOURCE)['independent_write_assertions'],actual_deployment_receipts=read(owner/'actual-deployment-byte-receipts.json'),mac_lifecycle=read_control(S/'controller-lifecycle',b,'controller-lifecycle',head=external['mac_lifecycle_head_sha256']),mac_lifecycle_head=external['mac_lifecycle_head_sha256'],gpu_export_raw=export_raw,campaign_initial_scope=initial,campaign_rows=rows,load_permit=read(S/'load-permit.json'),grant=grant,ready_proof=read(S/'ready-proof-stdout.raw'))
    guard()
    print(json.dumps({'status':'SUPPLEMENTAL_READONLY_AUDIT_RESULT_ORIGINAL_REJECTION_RETAINED','epoch':time.time(),'original_spec_sha256':SPEC_SHA,'original_runtime_sha256':RUNTIME_SHA,'original_export_raw_sha256':hashlib.sha256(export_raw).hexdigest(),'review_source_inventory_sha256':sha(pins),'original_frozen_verifier_passed':False,'original_frozen_rejection':original_rejection,'original_field_source_bytes_unchanged':True,'original_modules_and_function_globals_unchanged':True,'only_reviewed_budget_predicate_differs':True,'owner_final_statement_synthesized':False,'owner_acceptance_required_before_using_supplement_as_formal_gate':True,'new_model_or_rhino_calls':0,'private_formal_reads':0,'supplemental_result':result},sort_keys=True))
if __name__=='__main__':main()
