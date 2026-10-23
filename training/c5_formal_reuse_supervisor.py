"""Pre-load Linux qualification, finite watchdog and shared one-signal stop.

All effects require the actual new formal scope guard and verified Mac permit.
No process lookup by name, reconnecting model, or implicit replacement worker.
"""
import math
import hashlib
import os
from pathlib import Path
import selectors
import signal
import sys
import time
from training.c5_reuse_evidence import require,sha,strict
from training.c5_recovery_storage import EvidenceLog,write_once,read_private
from training.c5_recovery_stop import CoordinatedStop
from training.c5_reuse_process_identity import LinuxIdentity,OwnedPidfdOperations
from training.c5_reuse_gpu_supervisor import PACKET,progress

from plugin.rhino_listener.c5_formal_reuse_limits import watchdog_limits

def validate_load_permit(permit,spec,freeze,attempt):
    from training.c5_formal_reuse_admission import campaign_scope
    from training.c5_formal_reuse_admission import formal_replay as replay
    from training.c5_reuse_evidence import ZERO
    require(type(permit) is dict and set(permit)==({'scope','rows','attempt','first_load_epoch','budget_basis'} if 'run_package' in freeze else {'scope','rows','attempt','first_load_epoch'})
        and permit['scope']==campaign_scope(spec,freeze) and type(permit['attempt']) is int and permit['attempt']==attempt
        and type(permit['rows']) is list and 1<=len(permit['rows'])<=2048,'formal_reuse_load_permit_shape')
    from training.c5_formal_reuse_revision import initial_scope
    initial=initial_scope(spec,freeze)
    lineage=freeze.get('incremental_revision')
    if lineage is not None:
        require(permit['rows'][:lineage['prior_campaign_rows']]==lineage['prior_campaign_events'],
            'formal_reuse_exact_original_permit_prefix_required')
    head=ZERO
    for i,row in enumerate(permit['rows']):
        require(set(row)=={'seq','previous_sha256','binding_sha256','kind','payload','record_sha256'}
            and type(row['seq']) is int and row['seq']==i and row['previous_sha256']==head and row['binding_sha256']==sha(initial)
            and row['record_sha256']==sha({k:v for k,v in row.items() if k!='record_sha256'}),
            'formal_reuse_load_permit_original_chain')
        head=row['record_sha256']
    state=replay(initial,permit['rows'])
    require(state['scope']==permit['scope'],'formal_reuse_current_revision_permit_required')
    require(state['active'] and state['attempts']==attempt and not state['formal_consumed']
        and state['status']=='LOADING' and state['first_load_epoch']==permit['first_load_epoch'],
        'formal_reuse_load_permit_preprivate_order')
    if 'run_package' in freeze:
        from training.c5_formal_run_package import verify_package_prefix
        verify_package_prefix(freeze['run_package'],permit['rows'])
        require(state['package']==freeze['run_package'] and permit['budget_basis']=={
            'charged_before_seconds':state['charged_gpu_seconds'],
            'load_intent_epoch':state['load_intent_epoch'],'legacy_first_load_epoch':state['first_load_epoch']},
            'run_package_actual_budget_permit')
    return state

def claim_gpu_role(permit,freeze,attempt):
    from training.c5_formal_reuse_admission import ROOTS,NAMESPACE,history_guard
    root=ROOTS['gpu'];history_guard('gpu',freeze['history'])()
    parent=root/NAMESPACE
    from training.c5_formal_reuse_revision import initial_scope
    manifest={'scope_sha256':sha(initial_scope({},freeze)) if freeze.get('incremental_revision') is not None else sha(permit['scope']),'first_load_epoch':permit['first_load_epoch'],
        'history_sha256':sha(freeze['history']),'replay_allowed':False}
    if not parent.exists():
        require(attempt==1,'formal_reuse_gpu_missing_previous_roles')
        parent.mkdir(mode=0o700);write_once(parent,'campaign.json',manifest)
    require(strict(read_private(parent/'campaign.json'))==manifest,
        'formal_reuse_gpu_no_clock_or_scope_replacement')
    require(set(p.name for p in parent.iterdir())=={'campaign.json'}|{
        'worker-role-%d.json'%n for n in range(1,attempt)},'formal_reuse_gpu_exact_role_population')
    write_once(parent,'worker-role-%d.json'%attempt,{'attempt':attempt,
        'permit_sha256':sha(permit),'first_load_epoch':permit['first_load_epoch'],'replay_allowed':False})

def independent_stop(state,guard):
    qualification=strict(read_private(state/'qualification.json'))
    log=EvidenceLog(state/'qualified-stop',{'qualification_sha256':sha(qualification)},guard)
    try:
        coordinator=CoordinatedStop(log,qualification);value=coordinator.observe()
        if value['status']!='not_requested':return value
        require(LinuxIdentity()(qualification['parent_pid'])==strict(read_private(state/'parent-identity.json')),
            'formal_reuse_original_parent_required')
        return coordinator.stop(OwnedPidfdOperations(guard))
    finally:log.close()

def supervise(state,spec,freeze,attempt,guard,child,*,watchdog_type=None):
    import threading
    limits=watchdog_limits(spec)
    require(sys.platform=='linux' and hasattr(os,'fork') and hasattr(os,'pidfd_open')
        and hasattr(signal,'pidfd_send_signal') and threading.active_count()==1 and 'torch' not in sys.modules,
        'formal_reuse_qualification_before_threads_or_model')
    guard();state.mkdir(mode=0o700)
    permit=strict(sys.stdin.buffer.readline(1048577));validated=validate_load_permit(permit,spec,freeze,attempt)
    claim_gpu_role(permit,freeze,attempt)
    write_once(state,'load-permit.json',permit)
    write_once(state,'worker-role-consumed.json',{'attempt':attempt,'permit_sha256':sha(permit),'replay_allowed':False})
    from training.c5_formal_run_budget import budget_for
    budget=budget_for(freeze,permit)
    parent=LinuxIdentity()(os.getpid())
    require(parent['uid']==freeze['field_plan']['gpu_process']['uid']
        and parent['boot_id']==freeze['field_plan']['gpu_process']['boot_id'],
        'formal_reuse_current_owned_gpu_identity')
    from plugin.rhino_listener.c5_formal_reuse_scope import REMOTE_ENV,REMOTE_SOURCE
    from plugin.rhino_listener.c5_followup_profile import GPU_FLAGS
    expected=[str(REMOTE_ENV/'bin/python3.11'),*GPU_FLAGS,
        str(REMOTE_SOURCE/'tools/run_c5_formal_reuse_worker.py'),'serve','--attempt',str(attempt)]
    require(Path(sys.executable).resolve()==REMOTE_ENV/'bin/python3.11'
        and Path.cwd()==REMOTE_SOURCE and parent['argv_sha256']==hashlib.sha256(
            b'\0'.join(v.encode() for v in expected)+b'\0').hexdigest(),
        'formal_reuse_exact_qualified_entry_argv')
    write_once(state,'parent-identity.json',parent)
    gate_r,gate_w=os.pipe();progress_r,progress_w=os.pipe();pid=None;fd=None;log=None
    status=None;stop_result=None;old_handlers={};primary=None;cleanup_errors=[]
    try:
        def interrupted(*_):raise TimeoutError('formal_reuse_supervisor_termination')
        old_handlers={s:signal.signal(s,interrupted) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP)}
        sys.stdout.flush();sys.stderr.flush();pid=os.fork()
        if pid==0:
            for s in old_handlers:signal.signal(s,signal.SIG_DFL)
            os.close(gate_w);os.close(progress_r)
            try:
                require(os.read(gate_r,2)==b'G','formal_reuse_preload_gate');os.close(gate_r)
                q=strict(read_private(state/'qualification.json'))
                require(q['target']==LinuxIdentity()(os.getpid()) and q['parent_pid']==os.getppid(),
                    'formal_reuse_qualified_child_only')
                child(progress_w);os._exit(0)
            except BaseException:
                # Never print private request/answer frames or their exceptions.
                sys.stderr.write('C5_FORMAL_REUSE_CHILD_FAILED\n');sys.stderr.flush();os._exit(1)
        os.close(gate_r);gate_r=None;os.close(progress_w);progress_w=None
        fd=os.pidfd_open(pid,0);target=LinuxIdentity()(pid)
        require(LinuxIdentity().parent(pid)==os.getpid() and all(target[k]==parent[k]
            for k in ('uid','boot_id','argv_sha256','executable_sha256','cwd')),'formal_reuse_owned_fork_identity')
        qualification={'target':target,'parent_pid':os.getpid(),'model_loading_started':False}
        write_once(state,'qualification.json',qualification)
        log=EvidenceLog(state/'qualified-stop',{'qualification_sha256':sha(qualification)},guard,create=True)
        coordinator=CoordinatedStop(log,qualification)
        if watchdog_type is None:watchdog_type=FormalWatchdog
        watchdog=watchdog_type(time.monotonic(),budget.check(),limits=limits)
        guard();budget.check();require(os.write(gate_w,b'G')==1,'formal_reuse_load_release')
        os.close(gate_w);gate_w=None;os.set_blocking(progress_r,False)
        with selectors.DefaultSelector() as selector:
            selector.register(fd,selectors.EVENT_READ,'exit');selector.register(progress_r,selectors.EVENT_READ,'progress')
            while True:
                guard();budget.check();events=selector.select(min(watchdog.check(),1))
                if any(e.data=='exit' for e,_ in events):break
                for event,_ in events:
                    data=os.read(progress_r,4096)
                    if data:watchdog.feed(data)
                    else:selector.unregister(progress_r)
    except BaseException as error:
        primary=error
        raise
    finally:
        try:
            if log is not None:
                ops=OwnedPidfdOperations(guard)
                ops.pin=lambda supplied:os.dup(fd) if supplied==pid else (_ for _ in ()).throw(ValueError('formal_reuse_stop_pid'))
                try:stop_result=coordinator.stop(ops)
                except BaseException as error:cleanup_errors.append({'action':'qualified_stop','error_type':type(error).__name__})
            if pid is not None and pid>0:
                deadline=time.monotonic()+30
                while True:
                    observed,value=os.waitpid(pid,os.WNOHANG)
                    if observed==pid:status=value;break
                    if time.monotonic()>=deadline:break
                    time.sleep(0.05)
            write_once(state,'supervisor-final.json',{'child_wait_status':status,'child_exit_reaped':status is not None,
                'stop_result':stop_result,'epoch':time.time(),'retry_allowed':False,
                'primary_error_type':None if primary is None else type(primary).__name__,'cleanup_errors':cleanup_errors})
        finally:
            # Keep an unreleased child blocked until the qualified shared stop
            # is recorded. Closing its gate first creates an EOF/identity race.
            for item in (gate_r,gate_w,progress_r,progress_w):
                if item is not None:os.close(item)
            if log is not None:log.close()
            if fd is not None:os.close(fd)
            for s,h in old_handlers.items():signal.signal(s,h)
    require(not cleanup_errors and status==0,'formal_reuse_child_incomplete_no_replay')


class FormalWatchdog:

    def __init__(self, start, cap, *, clock=time.monotonic, limits=None):
        require(type(start) in (int, float) and math.isfinite(start) and (0 < cap <= (3600 if limits is None else 129600 if limits['model_seconds'] == 360 else 18000)), 'reuse_watchdog_reservation')
        self.limits = limits
        self.startup = 180 if limits is None else limits['startup_seconds']
        self.first_gap = 180 if limits is None else limits['first_request_idle_seconds']
        self.native_gap = 180 if limits is None else limits['between_requests_idle_seconds']
        self.begun = limits is None
        self.clock = clock
        self.last = start
        self.hard = start + cap
        self.deadline = min(self.hard, start + self.startup)
        self.ready = False
        self.pending = False
        self.stages = 0
        self.buffer = b''
        self.last_packet = start
        self.request_active = False
        self.requests = 0

    def check(self):
        now = self.clock()
        require(math.isfinite(now) and self.last <= now < self.deadline, 'reuse_supervisor_watchdog_deadline')
        self.last = now
        return self.deadline - now

    def feed(self, chunk):
        self.check()
        require(type(chunk) is bytes and 0 < len(chunk) <= 4096, 'reuse_watchdog_progress_bytes')
        self.buffer += chunk
        while len(self.buffer) >= PACKET.size:
            kind, issued = PACKET.unpack(self.buffer[:PACKET.size])
            self.buffer = self.buffer[PACKET.size:]
            now = self.clock()
            require(math.isfinite(issued) and self.last_packet <= issued <= now, 'reuse_watchdog_progress_time')
            self.last_packet = issued
            if kind == b'L':
                require(not self.ready and (not self.pending), 'reuse_watchdog_duplicate_ready')
                self.ready = True
                self.deadline = self.hard
            elif kind == b'B':
                require(self.limits is not None and self.ready and (not self.begun) and (not self.request_active) and (not self.pending) and (self.requests == 0), 'reuse_watchdog_once_begin')
                self.begun = True
                self.deadline = min(self.hard, issued + self.first_gap)
            elif kind == b'R':
                require(self.ready and self.begun and (not self.request_active) and (not self.pending) and (self.requests < 56), 'reuse_watchdog_whole_request_start')
                self.request_active = True
                self.requests += 1
                self.deadline = min(self.hard, issued + (180 if self.limits is None else self.limits['model_seconds']))
            elif kind == b'D':
                require(self.request_active and (not self.pending), 'reuse_watchdog_whole_request_end')
                self.request_active = False
                self.deadline = min(self.hard, issued + self.native_gap)
            elif kind == b'S':
                require(self.ready and self.request_active and (not self.pending) and (self.stages < 112), 'reuse_watchdog_stage_order')
                self.stages += 1
                self.pending = True
            elif kind == b'E':
                require(self.ready and self.request_active and self.pending, 'reuse_watchdog_unmatched_return')
                self.pending = False
            else:
                raise ValueError('reuse_watchdog_unknown_progress')

def export_supervisor(state,freeze,guard):
    import subprocess
    guard();qualification=strict(read_private(state/'qualification.json'))
    log=EvidenceLog(state/'qualified-stop',{'qualification_sha256':sha(qualification)},guard)
    try:rows=log.rows()
    finally:log.close()
    value={'qualification':qualification,'parent':strict(read_private(state/'parent-identity.json')),
        'permit':strict(read_private(state/'load-permit.json')),
        'final':strict(read_private(state/'supervisor-final.json')),'stop_rows':rows,
        'stop_binding':{'qualification_sha256':sha(qualification)},'epoch':time.time(),
        'target_proc_present':Path('/proc',str(qualification['target']['pid'])).exists(),
        'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'gpu_stdout':subprocess.check_output(['nvidia-smi','--query-gpu=uuid,memory.used',
            '--format=csv,noheader,nounits'],text=True,timeout=15),
        'compute_stdout':subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory',
            '--format=csv,noheader,nounits'],text=True,timeout=15),'model_or_cuda_calls':0,'private_formal_reads':0}
    if 'run_package' in freeze:
        value['worker_resource']=strict(read_private(state/'resource-settlement.json')) if (state/'resource-settlement.json').exists() else None
    guard();return value
