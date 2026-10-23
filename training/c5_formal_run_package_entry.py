"""Owner's single private session; no chat relay or per-retry attestation."""
import getpass
import json
import os
import secrets
import sys
import time
from pathlib import Path
from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.c5_research_channel import private_directory, read_json, publish_json
from plugin.rhino_listener.c5_formal_reuse_scope import MAC_STATE, attempt_state
from training.c5_formal_run_package import automatic_reconcile, capture_owner_receipt, public_status


def request_rhino_attempt(spec, freeze, attempt):
    value = {'attempt': attempt, 'study_id': spec['study_id'], 'runtime_sha256': digest(freeze),
             'nonce':secrets.token_hex(32)}
    fd = private_directory(MAC_STATE)
    name = 'rhino-attempt-' + secrets.token_hex(12) + '.tmp'
    try:
        out = os.open(name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(out, 'w') as stream:
            json.dump(value, stream, sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(name, 'rhino-active-attempt.json', src_dir_fd=fd, dst_dir_fd=fd);os.fsync(fd)
    finally:
        try:os.unlink(name,dir_fd=fd)
        except FileNotFoundError:pass
        os.close(fd)
    return value


def prepare_owner_session(session,campaign,spec,freeze,public,source,*,input_fn=input,output=print):
    """All human input precedes native preparation and durable load intent."""
    from tools.c5_formal20_owner_run_v2 import verify_private_metadata
    from training.c5_recovery_confirmation import input_status
    if session.get('confirmed'):return True
    session['sealed']=Path(getpass.getpass('原封存 age 文件绝对路径（不回显）：').strip())
    session['identity']=Path(getpass.getpass('age identity 绝对路径（不回显）：').strip())
    verify_private_metadata(session['sealed'],session['identity'],public,freeze);source()
    if not campaign.observation()['package_owner_consent']:
        output('确认本精确运行包、有限预曝光自动恢复，以及真实回执在本终端自动展示并私下保存；不声称逐次人工核对宿主回执。')
        confirmed=False
        for _ in range(3):
            try:status,_=input_status(input_fn('输入“确认并保管”（取消则暂停，未准备Rhino、未加载模型）：'))
            except (EOFError,KeyboardInterrupt):return False
            if status=='confirmed':confirmed=True;break
            if status=='cancelled':return False
            output('输入未匹配；未准备Rhino、未消费尝试。')
        if not confirmed:return False
        source()
        from training.c5_reuse_evidence import sha
        campaign._event('package_owner_session_confirmed',{'scope_sha256':sha(campaign.scope),
            'automatic_receipt_capture':True,'manual_host_ready_attestation':False,'before_model_loading':True})
    session['confirmed']=True
    return True


def prepare_private_session(session,campaign,spec,freeze,public,source):
    from training.c5_formal_run_budget import require_recovery_window
    require(session.get('confirmed') is True,'run_package_private_session_not_prepared')
    source();require_recovery_window(spec['run_package'],campaign.observation())


def finalize_private_audit(state, spec, freeze, guard, terminal):
    from training.c5_execution import load_pinned_tokenizer, load_config
    from training.c5_formal_reuse_joint_audit import audit_run_v2, public_summary
    root=Path(__file__).resolve().parents[1]
    tokenizer=load_pinned_tokenizer(Path(freeze['tokenizer_dir']),config=load_config(root/'eval/c5/c5-engineering-config.json'))
    guard()
    private=audit_run_v2(state,read_json(state,'private-cases.json'),spec,freeze,tokenizer,
                         source_guard=guard,external_seal_sha=terminal['seal_sha256'])
    if (state/'independent-audit.json').exists():
        require(read_json(state,'independent-audit.json')==private,'run_package_original_audit_changed')
    else:publish_json(state,'independent-audit.json',private)
    summary=public_summary(private,spec,freeze,terminal['seal_sha256'])
    summary['receipt_custody']='owner_authorized_automatic_capture_not_manual_per_receipt'
    if (state/'owner-public-audit-summary.json').exists():
        require(read_json(state,'owner-public-audit-summary.json')==summary,'run_package_original_audit_summary_changed')
    else:publish_json(state,'owner-public-audit-summary.json',summary)
    return summary


def _run_package(*, output=print):
    require(sys.stdin.isatty() and sys.stderr.isatty(),'run_package_owner_private_terminal_required')
    from training.c5_formal_reuse_field_scope import scope
    from training.c5_formal_reuse_admission import open_formal_campaign
    from tools.c5_formal_reuse_owner import run_interactive
    spec,freeze,grant,guard=scope(check_time=False)
    require('run_package' in spec,'run_package_required')
    previous=Path(spec['run_package']['previous_mac_attempt_root'])
    if (previous/'host-continuity-terminal-receipt.json').is_file():
        output('原失败实际回执（新规则自动保管，不追认旧逐次人工见证）：'+
            json.dumps(read_json(previous,'host-continuity-terminal-receipt.json'),sort_keys=True))
    session={}
    output(json.dumps({'package_id':spec['run_package']['layout']['package_id'],
        'spec_sha256':digest(spec),'runtime_sha256':digest(freeze),'rules':spec['run_package']['policy'],
        'custody':'本终端确认一次；各次真实回执自动展示并保存在本人目录，不声称逐次人工核对',
        'paths_collected_before_model_loading':True},ensure_ascii=False,sort_keys=True))
    while True:
        campaign=open_formal_campaign(spec,freeze,grant,freeze['history'])
        observation=campaign.observation()
        attempt=observation['attempts']+1
        try:
            if observation['status']=='AWAITING_INDEPENDENT_AUDIT':
                previous=attempt_state('mac',observation['attempts'])
                terminal=capture_owner_receipt(previous,spec,freeze,output=output)
                summary=finalize_private_audit(previous,spec,freeze,guard,terminal)
                from training.c5_formal_run_package import settle_known_load
                settle_known_load(campaign,previous,summary['private_audit_sha256'])
                return summary
            if observation['status']=='PAUSED_RECONCILIATION' and not observation['formal_consumed']:
                previous=attempt_state('mac',observation['attempts'])
                try:
                    capture_owner_receipt(previous,spec,freeze,output=output)
                    decision=automatic_reconcile(campaign,previous,spec,freeze)
                except BaseException:
                    return public_status(campaign,previous)
                if decision!='RETRYABLE_ENGINEERING':return public_status(campaign,previous)
            observation=campaign.observation()
            if observation['formal_consumed'] or attempt>observation['attempts_max']:
                return public_status(campaign,attempt_state('mac',max(1,observation['attempts'])))
            require(not observation['active'],'run_package_existing_active_attempt_requires_reconciliation')
            from tools.c5_formal_reuse_owner import commitment
            if not prepare_owner_session(session,campaign,spec,freeze,commitment(spec),guard,output=output):
                return {'status':'WAITING_OWNER','attempt_consumed':False,'native_preparation_started':False}
            state=attempt_state('mac',attempt)
        finally:campaign.log.close()
        error=None;result=None
        try:result=run_interactive(attempt,package_session=session)
        except BaseException as caught:error=caught
        campaign=open_formal_campaign(spec,freeze,grant,freeze['history'])
        try:
            observed=campaign.observation()
            if not (state/'host-continuity-terminal-receipt.json').is_file():
                return {'status':'PAUSED_RECONCILIATION' if observed['attempts']>=attempt else 'WAITING_OWNER',
                        'error_type':type(error).__name__ if error else None,'private_content_included':False}
            terminal=capture_owner_receipt(state,spec,freeze,output=output)
            if observed['status']=='AWAITING_INDEPENDENT_AUDIT':
                summary=finalize_private_audit(state,spec,freeze,guard,terminal)
                from training.c5_formal_run_package import settle_known_load
                settle_known_load(campaign,state,summary['private_audit_sha256'])
                output(json.dumps(summary,sort_keys=True));return summary
            if observed['formal_consumed']:
                # Incomplete post-exposure runs are never filled or replayed.
                return public_status(campaign,state)
            if observed['status']!='PAUSED_RECONCILIATION':
                return public_status(campaign,state)
            try:
                decision=automatic_reconcile(campaign,state,spec,freeze,
                    error='cancelled' if isinstance(error,KeyboardInterrupt) else 'startup')
            except BaseException as audit_error:
                return {'status':'PAUSED_RECONCILIATION','error_type':type(audit_error).__name__,
                        'attempts_consumed':observed['attempts'],'private_content_included':False}
            status=public_status(campaign,state);output(json.dumps(status,sort_keys=True))
            if decision!='RETRYABLE_ENGINEERING':return status
            from training.c5_formal_run_budget import require_recovery_window
            require_recovery_window(spec['run_package'],campaign.observation())
            # Same exact approved pair, complete raw proof, known cleanup and
            # original ledger counters are checked again by the actual entry.
        finally:campaign.log.close()


def run_package(*,output=print):
    import fcntl,stat
    require(sys.stdin.isatty() and sys.stderr.isatty(),'run_package_owner_private_terminal_required')
    from training.c5_formal_reuse_control import control_scope
    control_scope(Path(__file__).resolve().parents[1])
    # One owner process per exact package. No second terminal can launch a
    # competing load while the first waits for private input or is cleaning up.
    fd=os.open(MAC_STATE/'owner-session.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    info=os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
        and stat.S_IMODE(info.st_mode)==0o600,'run_package_owner_lock_identity')
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return {'status':'ALREADY_RUNNING','model_restart':False,'private_content_included':False}
    try:return _run_package(output=output)
    finally:
        try:
            # The generation/native observer has already ended before a terminal
            # receipt exists. Detach the known waiting dispatcher independently.
            from training.c5_formal_reuse_control import control_scope
            from training.c5_formal_reuse_admission import open_formal_campaign
            root=Path(__file__).resolve().parents[1]
            spec,freeze,_=control_scope(root)
            grant=read_json(MAC_STATE,'owner-approval.json')
            campaign=open_formal_campaign(spec,freeze,grant,freeze['history'])
            try:
                state=attempt_state('mac',max(1,campaign.observation()['attempts']))
                detached=None
                if (state/'host-continuity-terminal-receipt.json').exists():
                    request=request_rhino_attempt(spec,freeze,0)
                    name='package-dispatcher-detached-'+request['nonce']+'.json'
                    deadline=time.monotonic()+10
                    while not (MAC_STATE/name).exists() and time.monotonic()<deadline:time.sleep(0.05)
                    detached=(MAC_STATE/name).exists() and read_json(MAC_STATE,name)==request
                review=public_status(campaign,state)
                review['package_dispatcher_detach_observed']=detached
                review['manual_external_receipt_attestation']=False
                head=campaign.log.rows()[-1]['record_sha256']
                name='package-review-summary-'+head+'.json'
                if not (MAC_STATE/name).exists():publish_json(MAC_STATE,name,review)
                output(json.dumps(review,sort_keys=True))
            finally:campaign.log.close()
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
