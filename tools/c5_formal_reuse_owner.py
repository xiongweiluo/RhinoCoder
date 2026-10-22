#!/usr/bin/env python3
"""Private owner TTY only. No agent private-case or key-path interface.

Pre-load confirmation may pause without consuming an attempt. A new durable
global exposure event precedes decryption; after exposure there is no retry.
"""
import argparse
import getpass
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_formal_reuse_scope import STUDY_ID,MAC_STATE,attempt_state
from plugin.rhino_listener.c5_research_native import require,digest
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from training.c5_formal_reuse_field_scope import scope
from training.c5_formal_reuse_admission import open_formal_campaign,require_startable,consume_before_private
from training.c5_formal_reuse_budget import FormalBudgetV2
from training.c5_formal_reuse_adapters import NativeAdapterV2,ModelAdapterV2
from training.c5_formal_reuse_runner import FormalRunner
from training.c5_formal_reuse_joint_audit import audit_run_v2,public_summary
from training.c5_recovery_confirmation import snapshot,confirm_preload
from tools.c5_formal20_owner_run import sealed_loader
from tools.c5_formal20_owner_run_v2 import verify_private_metadata

def commitment(spec):
    from tools.c5_formal20_public_preflight import preflight
    p=ROOT/'eval/c5/rhino-formal20-public-commitment-v1.json'
    require(preflight(p)['public_commitment_sha256']==spec['public_commitment_sha256'],
        'formal_reuse_original_commitment_drift')
    return json.loads(p.read_bytes())

def run_interactive(attempt):
    require(sys.stdin.isatty() and sys.stderr.isatty(),'formal_reuse_owner_private_terminal_required')
    spec,freeze,approval,source=scope();public=commitment(spec)
    root=Path(freeze['history']['mac_global_root'])
    campaign=open_formal_campaign(spec,freeze,approval,freeze['history'],create=not(root/'formal-reuse-v1').exists())
    state=attempt_state('mac',attempt);budget=None;native=model=None;started=False;exposed=False;primary_error=None
    try:
        require_startable(campaign,attempt)
        if not state.exists():state.mkdir(mode=0o700)
        def guard():
            source()
            if budget is not None:budget.check()
        native=NativeAdapterV2(state,spec,freeze,guard=guard,cleanup_guard=source)
        if not (state/'formal20.zero-prepared.json').exists():
            publish_json(state,'formal20.zero-started.claim.json',{'study_id':STUDY_ID,
                'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
            native.arm()
        else:
            require(read_json(state,'formal20.zero-prepared.json')=={'study_id':STUDY_ID,
                'runtime_freeze_sha256':digest(freeze),'private_rows_read':0,'model_calls':0}
                and not (state/'remote-launch-intent.json').exists()
                and not (state/'formal20.started.json').exists(),'formal_reuse_resume_only_unloaded_preparation')
            native.armed=True
            native.keys=[(state,'hub.key')]+[(state/('F%02d-%s'%(n,r)),'handoff.key')
                for n in range(1,21) for r in ('base','lora')]
        print('C5_FORMAL_REUSE_WAIT_APPROVED_RHINO_ARM_ZERO_PRIVATE_ROWS',flush=True)
        native.wait_zero_ready();source()
        basis=read_json(state,'host-continuity-ready.json')
        snap_name='preload-snapshot.json'
        if not (state/snap_name).exists():
            publish_json(state,snap_name,snapshot(campaign.scope,digest(basis),hashlib.sha256(secrets.token_bytes(32)).hexdigest()))
        snap=read_json(state,snap_name)
        previous=campaign.observation()['receipt']
        if previous is not None and previous['snapshot']==snap and campaign.observation()['status']=='PREPARED':
            from training.c5_recovery_confirmation import validate_receipt
            receipt=validate_receipt(campaign.scope,snap,previous['receipt'])
        else:
            receipt=confirm_preload(campaign.scope,snap,source)
            if receipt is None:return {'status':'WAITING_OWNER_MODEL_NOT_LOADED','attempt_consumed':False}
            campaign.confirm(snap,receipt)
        require(time.time()<=spec['latest_owner_start_epoch'],'formal_reuse_full_window_unavailable')
        campaign.start();started=True
        first=campaign.observation()['first_load_epoch'];now,mono=time.time(),time.monotonic()
        budget=FormalBudgetV2(freeze['resource_boundary'],start={'wall':first,'mono':mono-(now-first)})
        model=ModelAdapterV2(state,spec,freeze,guard=guard);model.attempt=attempt
        model.load_permit={'scope':campaign.scope,'rows':campaign.log.rows(),'attempt':attempt,'first_load_epoch':first}
        model.start_zero();guard()
        ready=read_json(state,'worker-startup-ready.json');campaign.ready(digest(ready))
        publish_json(state,'formal20.zero-readiness.json',{'study_id':STUDY_ID,
            'runtime_freeze_sha256':digest(freeze),'host_ready_sha256':digest(basis),
            'model_ready_sha256':digest(ready),'private_rows_read':0,'formal_started_present':False})
        sealed=Path(getpass.getpass('原封存 age 文件绝对路径（仅本人终端，不回显）：').strip())
        identity=Path(getpass.getpass('age identity 文件绝对路径（不回显）：').strip())
        verify_private_metadata(sealed,identity,public,freeze);guard()
        consume_before_private(campaign,attempt,state);exposed=True;campaign.begin(digest(ready))
        runner=FormalRunner(state=state,spec=spec,freeze=freeze,approval=approval,model=model,native=native,
            source_guard=source,budget_guard=budget.check)
        result=runner.run(sealed_loader(sealed,identity,public,freeze,state=state,
            repository_root=Path(freeze['repository_root_for_private_boundary'])))
        if result['status']=='formal_execution_complete_awaiting_independent_audit':campaign.completed(digest(result))
        else:
            campaign.failed('integrity',{'raw_anchor_sha256':digest(result),'capture_complete':False,
                'qualified_target_absent':False,'known_native_cleanup_complete':False,'private_exposure_absent':False})
        return {k:result[k] for k in ('study_id','status','slots_attempted','route_slots_required','error_type','c5_6_gate_claim')}
    except BaseException as primary:
        primary_error=primary
        cleanup=[]
        if started:
            if model is not None and model.process is not None and not model.bootstrapped:
                try:model.stop_zero()
                except BaseException as error:cleanup.append({'action':'qualified_gpu_cleanup','error_type':type(error).__name__})
            if native is not None and not exposed:
                try:native.finish()
                except BaseException as error:cleanup.append({'action':'known_native_cleanup','error_type':type(error).__name__})
            publish_json(state,'formal-preexposure-failure.json',{'error_type':type(primary).__name__,
                'cleanup_errors':cleanup,'private_exposure_recorded':exposed,'retry_authorized_by_summary':False})
            observation=campaign.observation()
            if observation['active']:
                # This is an incomplete proof and therefore PAUSED_RECONCILIATION.
                # The read-only independent failure auditor must supply actual
                # raw evidence before bounded pre-exposure recovery is possible.
                campaign.failed('startup' if not exposed else 'integrity',{'raw_anchor_sha256':digest(
                    read_json(state,'formal-preexposure-failure.json')),'capture_complete':False,
                    'qualified_target_absent':False,'known_native_cleanup_complete':False,
                    'private_exposure_absent':not exposed})
        raise
    finally:
        try:
            if started and model is not None and model.process is not None and not model.bootstrapped \
                    and not (state/'worker-process-exit.json').exists():
                try:model.stop_zero()
                except BaseException as error:
                    if not (state/'owner-zero-cleanup-error.json').exists():
                        publish_json(state,'owner-zero-cleanup-error.json',{'error_type':type(error).__name__})
            if started and native is not None and not (state/'formal20.hub-initialization.claim.json').exists() \
                    and not (state/'preload-abort.response.json').exists():
                try:native.finish()
                except BaseException as error:
                    if not (state/'owner-native-cleanup-error.json').exists():
                        publish_json(state,'owner-native-cleanup-error.json',{'error_type':type(error).__name__})
            if budget is not None:
                try:budget.settle(state,'formal_mac_driver_finished')
                except BaseException as error:
                    if not (state/'owner-budget-settlement-error.json').exists():
                        publish_json(state,'owner-budget-settlement-error.json',{'error_type':type(error).__name__})
                    if primary_error is None:raise
        finally:campaign.log.close()

def audit_owner(attempt):
    require(sys.stdin.isatty() and sys.stderr.isatty(),'formal_reuse_owner_private_terminal_required')
    spec,freeze,_,guard=scope(check_time=False);commitment(spec);state=attempt_state('mac',attempt)
    print('第一步：只在此终端粘贴 Rhino 最后的完整实际终止回执行。不要在本提示输入确认文字。')
    line=input('完整 C5_FORMAL_REUSE_HOST_EXTERNAL_RECEIPT 行：').strip()
    prefix='C5_FORMAL_REUSE_HOST_EXTERNAL_RECEIPT '
    require(line.startswith(prefix),'formal_reuse_actual_terminal_receipt_required')
    terminal=json.loads(line[len(prefix):]);actual=read_json(state,'host-continuity-terminal-receipt.json')
    require(terminal==actual and terminal['study_id']==STUDY_ID,'formal_reuse_actual_terminal_binding')
    from training.c5_recovery_confirmation import input_status
    confirmed=False
    for _ in range(3):
        status,_=input_status(input('第二步：核对并私下保管后，输入“确认并保管”：'))
        if status=='confirmed':confirmed=True;break
        if status=='cancelled':break
        print('输入未匹配；请手动键入。没有重新执行研究。')
    require(confirmed,'formal_reuse_owner_final_confirmation_paused')
    from training.c5_execution import load_pinned_tokenizer,load_config
    tokenizer=load_pinned_tokenizer(Path(freeze['tokenizer_dir']),config=load_config(ROOT/'eval/c5/c5-engineering-config.json'))
    guard()
    private=audit_run_v2(state,read_json(state,'private-cases.json'),spec,freeze,tokenizer,
        source_guard=guard,external_seal_sha=terminal['seal_sha256'])
    publish_json(state,'independent-audit.json',private)
    summary=public_summary(private,spec,freeze,terminal['seal_sha256'])
    publish_json(state,'owner-public-audit-summary.json',summary);return summary

def reconcile_owner(attempt):
    require(sys.stdin.isatty() and sys.stderr.isatty(),'formal_reuse_owner_private_terminal_required')
    spec,freeze,approval,guard=scope(check_time=False);state=attempt_state('mac',attempt)
    line=input('第一步：私下粘贴本次失败的完整 C5_FORMAL_REUSE_HOST_EXTERNAL_RECEIPT 行：').strip()
    prefix='C5_FORMAL_REUSE_HOST_EXTERNAL_RECEIPT '
    require(line.startswith(prefix),'formal_reuse_actual_terminal_receipt_required')
    terminal=json.loads(line[len(prefix):])
    from training.c5_recovery_confirmation import input_status
    require(input_status(input('第二步：核对并私下保管后，输入“确认并保管”：'))[0]=='confirmed',
        'formal_reuse_owner_final_confirmation_paused')
    campaign=open_formal_campaign(spec,freeze,approval,freeze['history'])
    try:
        from training.c5_formal_reuse_failure_audit import audit_preexposure_failure
        guard();proof=audit_preexposure_failure(state,spec,freeze,campaign,terminal);guard()
        if (state/'independent-preexposure-failure-proof.json').exists():
            require(read_json(state,'independent-preexposure-failure-proof.json')==proof,
                'formal_reuse_failure_proof_changed')
        else:publish_json(state,'independent-preexposure-failure-proof.json',proof)
        decision=campaign.reconcile('startup',proof)
        return {'study_id':STUDY_ID,'status':decision,'attempts_consumed':campaign.observation()['attempts'],
            'first_load_epoch_preserved':True,'private_exposure_recorded':False,'research_restarted':False}
    finally:campaign.log.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit','reconcile'))
    p.add_argument('--attempt',type=int,choices=(1,2,3),default=1);a=p.parse_args()
    try:
        result={'run':run_interactive,'audit':audit_owner,'reconcile':reconcile_owner}[a.mode](a.attempt)
        print(json.dumps(result,sort_keys=True));return 0
    except BaseException as error:
        code=str(error)
        if not(code.startswith('formal_reuse_') and code.replace('_','').isascii() and code.replace('_','').isalnum()):code=type(error).__name__
        print(json.dumps({'status':'formal_reuse_owner_entry_stopped','error_code':code,
            'private_content_included':False}),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
