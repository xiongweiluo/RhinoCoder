#!/usr/bin/env python3
"""New exact-approved per-attempt setup/drive; human waiting never loads GPU."""
import argparse
import os
from pathlib import Path
import secrets
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def failure_category(error):
    """Only known engineering failures are retryable after independent cleanup."""
    if isinstance(error,(KeyboardInterrupt,SystemExit)):return 'cancelled'
    message=str(error)
    if message in ('followup_capture_read_deadline','field_pipe_deadline','field_whole_exchange_deadline','field_transport_eof'):
        return 'transport'
    if message in ('reuse_worker_eof_or_chunk','reuse_ssh_remote_supervisor_failed',
                   'recovery_ready_proof_transport'):return 'transport'
    if message=='reuse_model_operational_retirement':return 'native_operational'
    if message in ('followup_remote_diagnostic_incomplete_no_retry',
                   'followup_capture_limit_or_error_no_retry','followup_protocol_delivery_unknown'):
        return 'capture'
    return 'integrity'

def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--prepare',action='store_true');m.add_argument('--drive',action='store_true');m.add_argument('--accept-revision',action='store_true')
    p.add_argument('--attempt',required=True,type=int,choices=(1,2,3));args=p.parse_args()
    from plugin.rhino_listener.c5_recovery_mac_scope import mac_scope
    s,r,b,plan,h,g,guard=mac_scope(ROOT,args.attempt,private_prefixes=('__main__',))
    os.umask(0o077);os.chdir(ROOT)
    from training.c5_recovery_history import open_campaign
    from training.c5_recovery_controller import Campaign
    from training.c5_recovery_storage import write_once,read_private,directory
    from training.c5_reuse_evidence import require,sha,strict,canonical
    from plugin.rhino_listener.c5_research_channel import read_json
    root=Path(b['paths']['admission_root']);parent=root/'engineering-recovery-v3'
    if args.accept_revision:
        from training.c5_recovery_storage import EvidenceLog
        from training.c5_recovery_history import history_guard
        previous=s['recovery']['previous_campaign_head_sha256']
        require(previous is not None and parent.exists(),'recovery_exact_revision_prior_head_required')
        hg=history_guard(root,'mac',h)
        initial=strict(read_private(parent/'ledger/manifest.json'))['binding']
        revision_log=EvidenceLog(parent/'ledger',initial,hg)
        try:
            from training.c5_recovery_controller import replay
            rows=revision_log.rows();old=replay(initial,rows)
            require(rows and rows[-1]['record_sha256']==previous,'recovery_exact_revision_prior_head_changed')
            # Old host effects must be demonstrably closed before rebinding
            # readable code; a source change never legitimizes a live/unknown host.
            for folder in Path(b['paths']['state_root']).parent.glob('attempt-*'):
                if not folder.is_dir():continue
                if (folder/'warmup.started.json').exists():require((folder/'warmup.result.json').exists(),'recovery_revision_warmup_unknown')
                if (folder/'new-hub-started.claim.json').exists():
                    require((folder/'host-continuity-terminal-receipt.json').exists()
                        and not (folder/'hub.key').exists(),'recovery_revision_host_cleanup_unknown')
            current=Campaign(old['scope'],revision_log)
            action=(current.accept_resource_revision if b['recovery']['scope']['development_seconds_max']!=old['scope']['development_seconds_max'] else current.accept_revision)
            action(b['recovery']['scope'],dict(g,previous_campaign_head_sha256=previous))
            print('C5_RECOVERY_REVISION_ACCEPTED_BUDGET_AND_ATTEMPTS_PRESERVED');return
        finally:revision_log.close()
    create=args.prepare and not parent.exists()
    log=open_campaign(root,'mac',b['recovery']['scope'],h,create=create,grant=g)
    try:
        campaign=Campaign(b['recovery']['scope'],log);state=campaign.observation()
        require(not state['active'] and args.attempt==state['attempts']+1
            and state['status'] in ('WAITING_OWNER','PREPARED','RETRYABLE_ENGINEERING',
                                  'RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE'),
            'recovery_attempt_requires_known_campaign_state')
        remaining=(min(state['first_load_epoch']+b['recovery']['scope']['development_seconds_max']-60,s['resources']['generation_cutoff_epoch']-60)-time.time()
                   if state['first_load_epoch'] is not None else s['resources']['generation_cutoff_epoch']-time.time()-60)
        require(remaining>=plan['minimum_attempt_window_seconds'],'recovery_complete_remaining_attempt_window_unavailable')
        if state['first_load_epoch'] is None:
            require(time.time()+b['recovery']['scope']['development_seconds_max']<=s['resources']['generation_cutoff_epoch'],'recovery_complete_window_unavailable')
        local=Path(b['paths']['state_root']);owner=local.parent/'owner-custody'
        if args.prepare:
            require(not local.exists(),'recovery_attempt_setup_already_exists_no_overwrite')
            local.mkdir(mode=0o700)
            from training.c5_recovery_field_mac import prepare
            prepare(b,guard)
            if not owner.exists():owner.mkdir(mode=0o700)
            # Pointer update retains every previous public setup record. It
            # is not a new campaign/approval or a cleared consumption marker.
            setup={'attempt':args.attempt,'spec_sha256':b['spec_sha256'],'runtime_sha256':b['runtime_sha256']}
            write_once(local,'host-setup.json',setup)
            pointer=local.parent/'pending-host-setup.json'
            if pointer.exists():
                old=strict(read_private(pointer));require(old['attempt']==args.attempt-1 or (old['attempt']==args.attempt and old['runtime_sha256']!=b['runtime_sha256']),'recovery_host_pointer_order')
            temp=local.parent/('pending-host-setup-'+str(args.attempt)+'-'+b['runtime_sha256']+'.json')
            write_once(local.parent,temp.name,setup)
            # Preserve the prior pointer bytes under an immutable named copy.
            if pointer.exists():write_once(local.parent,'previous-host-pointer-'+str(old['attempt'])+'-'+old['runtime_sha256']+'.json',old)
            os.replace(temp,pointer)
            d=os.open(local.parent,os.O_DIRECTORY|os.O_RDONLY)
            try:os.fsync(d)
            finally:os.close(d)
            print('C5_RECOVERY_HOST_SETUP_PREPARED_NO_MODEL_LOADING');return
        guard();host=read_json(local,'host-continuity-ready.json');release=read_json(local,'entry-return-release.json')
        require(host['study_id']==b['study_id'] and host['runtime_sha256']==b['runtime_sha256']
            and host['generation_stages']==0 and release['source_inventory_sha256']==sha(r['source_files']),
            'recovery_current_host_preload_binding')
        if not (owner/('owner-preload-confirmation-'+b['runtime_sha256']+'.json')).exists():
            print('C5_RECOVERY_WAITING_OWNER_NO_MODEL_NO_ATTEMPT');return
        snap=strict(read_private(owner/('preload-snapshot-'+b['runtime_sha256']+'.json')))
        receipt=strict(read_private(owner/('owner-preload-confirmation-'+b['runtime_sha256']+'.json')))
        from training.c5_recovery_confirmation import validate_receipt
        validate_receipt(campaign.scope,snap,receipt)
        if state['receipt'] is None:campaign.confirm(snap,receipt)
        else:require(state['receipt']=={'snapshot':snap,'receipt':receipt},'recovery_retained_owner_permission_changed')
        guard();attempt=campaign.start()
        runner=None;session_holder={}
        try:
            from training.c5_recovery_field_budget import FieldBudget
            budget=FieldBudget(campaign)
            from training.c5_recovery_field_permit import permit
            load_permit=permit(campaign,b)
            from training.c5_recovery_field_ssh import FieldSSHSession
            from training.c5_recovery_field_mac import MacController
            from training.c5_reuse_admission import AdmissionRegistry
            from training.c5_recovery_field_audit import audit_ready,audit_failure
            from training.c5_reuse_field_scope import common_scope,PROTOCOL
            from plugin.rhino_listener.c5_recovery_scope import paths
            schemas=strict((ROOT/'eval/c5/rhino-runtime-schema-v1.json').read_bytes())['core_parameters']
            with AdmissionRegistry(b) as registry:
                def factory(*a):
                    session=FieldSSHSession.__new__(FieldSSHSession);session_holder['session']=session
                    session.__init__(*a,load_permit=load_permit);return session
                runner=MacController(b,{**plan,'source_files':r['source_files']},schemas,registry,guard,
                    budget.check,session_factory=factory)
                def begin(current_host,worker):
                    gpu={**b,'endpoint':'gpu','paths':paths('gpu',attempt,b['runtime_sha256'])}
                    raw=runner.session.ready_proof();anchor=audit_ready(raw,gpu,worker,load_permit,g)
                    campaign.ready(anchor);guard();budget.check();campaign.begin(anchor)
                    return {'kind':'reuse_begin_after_preload_confirmation','protocol':PROTOCOL,
                        'scope_sha256':sha(common_scope(b)),'preload_snapshot':snap,'preload_receipt':receipt,
                        'host_baseline_head_sha256':current_host['host_baseline_head_sha256'],
                        'worker_readiness_sha256':sha(worker)}
                result=runner.drive(begin)
                campaign.completed(sha(result))
                print('C5_RECOVERY_COMPLETE_AWAITING_INDEPENDENT_AUDIT '+canonical(result).decode())
        except BaseException as original:
            # The native driver records its known one-time cleanup. An unknown
            # fixture/dispatch is kept, never guessed or reset for another run.
            proof={'raw_anchor_sha256':sha({'error_type':type(original).__name__}),
                   'capture_complete':False,'qualified_target_absent':False,
                   'known_native_cleanup_complete':False,'private_exposure_absent':True}
            secondary=[]
            if runner is not None and session_holder.get('session') is not None:
                try:
                    session=session_holder['session']
                    result=session._captured_command('failure-proof')
                    require(result.returncode==0,'recovery_failure_export_unknown')
                    raw=strict(read_private(local/'failure-proof-stdout.raw'))
                    diagnostic=next((r['payload'] for r in session.lifecycle.rows
                                     if r['kind']=='raw_streams_final_observed'),None)
                    from training.c5_recovery_field_native_failure_audit import audit_known_first_hub_stop
                    from training.c5_reuse_field_journal import read_record
                    native_root=local/'native-controller';names=list(native_root.iterdir())
                    native_rows=[read_record(native_root,'raw-%04d.json'%i)[0] for i in range(len(names))]
                    native_proof=audit_known_first_hub_stop(native_rows,b,native_rows[-1]['record_sha256'],r)
                    native_known=native_proof['known_native_cleanup_complete']
                    gpu={**b,'endpoint':'gpu','paths':paths('gpu',attempt,b['runtime_sha256'])}
                    proof=audit_failure(raw,gpu,serve_capture=diagnostic,native_known=native_known,expected_gpu_uuid=plan['gpu_process']['gpu_uuid'])
                except BaseException as error:secondary.append(type(error).__name__)
            category=failure_category(original)
            try:decision=campaign.failed(category,proof)
            except BaseException as error:
                secondary.append(type(error).__name__);decision='PAUSED_RECONCILIATION'
            print('C5_RECOVERY_ATTEMPT_FAILED '+canonical({'attempt':attempt,'decision':decision,
                'error_type':type(original).__name__,'secondary':secondary,'proof':proof}).decode(),file=sys.stderr)
            raise
    finally:log.close()
if __name__=='__main__':main()
