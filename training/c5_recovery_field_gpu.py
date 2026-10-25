"""Qualified Linux fork, shared stop and one campaign budget. Lazy inference."""
import hashlib
import os
from pathlib import Path
import selectors
import signal
import sys
import time
from training.c5_reuse_evidence import require,sha
from training.c5_reuse_process_identity import LinuxIdentity,OwnedPidfdOperations
from training.c5_reuse_control_journal import ControlJournal,read_control
from training.c5_reuse_field_journal import FieldJournal
from training.c5_reuse_gpu_supervisor import Watchdog,progress
from training.c5_recovery_history import history_guard,open_qualified_stop
from training.c5_recovery_field_budget import FieldBudget
from plugin.rhino_listener.c5_recovery_admission import initialize_roles,AdmissionRegistry
from plugin.rhino_listener.c5_recovery_profile import PYTHON,GPU_FLAGS,ENTRY,RECOVERY_POLICY

def entry_identity(binding,plan):
    require(sys.platform=='linux' and Path(sys.executable).resolve()==Path(PYTHON)
        and Path.cwd()==Path(binding['paths']['source_root']) and os.getuid()==plan['gpu_process']['uid'],
        'recovery_fixed_gpu_process')
    argv=[PYTHON,*GPU_FLAGS,str(Path(binding['paths']['source_root'])/ENTRY),'--serve',
          '--attempt',str(binding['recovery']['attempt'])]
    value=LinuxIdentity()(os.getpid())
    require(value['argv_sha256']==hashlib.sha256(b'\0'.join(a.encode() for a in argv)+b'\0').hexdigest()
        and value['boot_id']==plan['gpu_process']['boot_id'],'recovery_gpu_argv_boot')
    return value

def independent_stop(binding,history,grant,guard):
    rows=read_control(Path(binding['paths']['state_root'])/'supervisor',binding,'supervisor')
    qualified=[r for r in rows if r['kind']=='owned_child_qualified']
    require(len(qualified)==1,'recovery_stop_unique_qualification')
    q=qualified[0]['payload'];parent=Path(binding['paths']['admission_root'])/'engineering-recovery-v3'
    hg=history_guard(binding['paths']['admission_root'],'gpu',history)
    coordinator=open_qualified_stop(parent,binding['recovery']['scope'],q,hg)
    try:
        result=coordinator.observe()
        if result['status']!='not_requested':return result
        launch=[r for r in rows if r['kind']=='child_launch_intent']
        require(len(launch)==1 and LinuxIdentity()(q['parent_pid'])==launch[0]['payload']['parent'],
                'recovery_stop_original_parent')
        return coordinator.stop(OwnedPidfdOperations(lambda:guard(cleanup_only=True)))
    finally:coordinator.log.close()

def supervise(binding,plan,runtime,history,grant,guard,campaign):
    import threading
    require(sys.platform=='linux' and hasattr(os,'fork') and hasattr(os,'pidfd_open')
        and hasattr(signal,'pidfd_send_signal') and threading.active_count()==1 and 'torch' not in sys.modules,
        'recovery_fork_before_threads_model')
    parent_identity=entry_identity(binding,plan);guard()
    budget=FieldBudget(campaign,persist=False);budget.require_attempt_window(plan['minimum_attempt_window_seconds'])
    control=ControlJournal(binding,'supervisor');registry=initialize_roles(binding,history,guard)
    journal=FieldJournal(binding,'worker',registry)
    # Original model/native/package bytes/settings are reused, not rebuilt.
    from training.c5_followup_gpu_loader import preflight
    inventory=preflight(runtime,plan,guard);budget.check()
    from training.c5_reuse_development_plan import public_plan
    plans=public_plan(Path(binding['paths']['source_root']))['task_plans']
    require(sha(plans)==binding['development_plan_sha256'],'recovery_exact_public_eight')
    gate_r,gate_w=os.pipe();progress_r,progress_w=os.pipe();pid=None;fd=None;coordinator=None;status=None
    previous={};primary=None;cleanup_errors=[]
    try:
        control.append('child_launch_intent',{'parent':parent_identity,'worker_open_head_sha256':journal.head,
            'policy_sha256':sha(RECOVERY_POLICY),'budget':budget.observation()})
        def interrupted(*_):raise TimeoutError('recovery_supervisor_termination')
        previous={s:signal.signal(s,interrupted) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP)}
        guard();budget.check();sys.stdout.flush();sys.stderr.flush();pid=os.fork()
        if pid==0:
            for s in previous:signal.signal(s,signal.SIG_DFL)
            os.close(gate_w);os.close(progress_r)
            try:
                require(os.read(gate_r,2)==b'G','recovery_child_load_barrier');os.close(gate_r)
                rows=read_control(control.root,binding,'supervisor')
                qualified=[r for r in rows if r['kind']=='owned_child_qualified']
                require(len(qualified)==1 and qualified[0]['payload']['target']==LinuxIdentity()(os.getpid())
                    and qualified[0]['payload']['parent_pid']==os.getppid(),'recovery_child_original_qualification')
                registry.close()
                lifecycle=ControlJournal(binding,'worker-lifecycle')
                qsha=sha(qualified[0]['payload'])
                lifecycle.append('model_loading_intent',{'qualification_sha256':qsha,'worker_open_head_sha256':journal.head})
                from training.c5_followup_gpu_loader import load
                tokenizer,generate,route,check=load(Path(binding['paths']['source_root']),inventory,guard,
                    budget.check,runtime=runtime,plan=plan)
                lifecycle.append('model_loaded',{'qualification_sha256':qsha,'training':False,'parse_repair':False})
                from training.c5_reuse_generation import GenerationPeer
                peer=GenerationPeer(binding,registry,plans,tokenizer,None,route,check,budget.check,journal=journal)
                def watched(prompt,stage):
                    check();progress(progress_w,b'S');value=generate(prompt,stage);progress(progress_w,b'E');check();return value
                peer.generate=watched
                from training.c5_reuse_field_transport import FieldPipe
                from training.c5_reuse_worker_loop import serve
                serve(peer,FieldPipe(sys.stdout.fileno(),sys.stdin.fileno()),qsha,check,budget.check,lifecycle.append,
                    on_ready=lambda:progress(progress_w,b'L'),on_request_start=lambda:progress(progress_w,b'R'),
                    on_request_end=lambda:progress(progress_w,b'D'),on_begin=lambda:progress(progress_w,b'B'))
                lifecycle.append('worker_budget_observation',budget.observation());os._exit(0)
            except BaseException:
                import traceback
                traceback.print_exc(file=sys.stderr);sys.stderr.flush();os._exit(1)
        os.close(gate_r);gate_r=None;os.close(progress_w);progress_w=None
        fd=os.pidfd_open(pid,0);reader=LinuxIdentity();target=reader(pid)
        require(reader.parent(pid)==os.getpid() and all(target[k]==parent_identity[k] for k in
            ('uid','boot_id','argv_sha256','executable_sha256','cwd')),'recovery_fork_target_identity')
        qualification={'target':target,'parent_pid':os.getpid(),'model_loading_started':False}
        control.append('owned_child_qualified',qualification)
        hg=history_guard(binding['paths']['admission_root'],'gpu',history)
        coordinator=open_qualified_stop(Path(binding['paths']['admission_root'])/'engineering-recovery-v3',
            binding['recovery']['scope'],qualification,hg,create=True,grant=grant)
        # Shared stop exists durably BEFORE the load permit.
        guard();budget.check();require(os.write(gate_w,b'G')==1,'recovery_parent_load_permit')
        os.close(gate_w);gate_w=None;os.set_blocking(progress_r,False)
        watchdog=Watchdog(time.monotonic(),budget.check(),limits=binding['limits'])
        with selectors.DefaultSelector() as selector:
            selector.register(fd,selectors.EVENT_READ,'exit');selector.register(progress_r,selectors.EVENT_READ,'progress')
            while True:
                guard();budget.check();events=selector.select(min(watchdog.check(),1))
                if any(e.data=='exit' for e,_ in events):break
                for event,_ in events:
                    chunk=os.read(progress_r,4096)
                    if chunk:watchdog.feed(chunk)
                    else:selector.unregister(progress_r)
    except BaseException as error:
        primary=error
        raise
    finally:
        for item in (gate_r,gate_w,progress_r,progress_w):
            if item is not None:os.close(item)
        try:
            if coordinator is not None:
                ops=OwnedPidfdOperations(lambda:guard(cleanup_only=True))
                # Keep the ORIGINAL pidfd for a natural exit/zombie. Never
                # reopen a recycled PID just to rediscover a finished child.
                ops.pin=lambda supplied:os.dup(fd) if supplied==pid else (_ for _ in ()).throw(ValueError('recovery_stop_pid'))
                try:
                    result=coordinator.stop(ops)
                    control.append('coordinated_stop_observed',{'result':result,'qualification_sha256':sha(qualification)})
                except BaseException as error:
                    cleanup_errors.append(type(error).__name__)
            if pid is not None and pid>0:
                deadline=time.monotonic()+30
                while True:
                    observed,value=os.waitpid(pid,os.WNOHANG)
                    if observed==pid:status=value;break
                    if time.monotonic()>=deadline:break
                    time.sleep(0.05)
            control.append('supervisor_final_observation',{'child_wait_status':status,'child_exit_reaped':status is not None,
                'budget':budget.observation(),'physical_gpu_release_verified':None,'whole_field_pass':False})
            if cleanup_errors and primary is None:raise RuntimeError('recovery_cleanup_unknown:'+','.join(cleanup_errors))
        except BaseException:
            if primary is None:raise
        finally:
            if coordinator is not None:coordinator.log.close()
            if fd is not None:os.close(fd)
            registry.close()
            for s,handler in previous.items():signal.signal(s,handler)
    return {'child_exit_success':status==0,'child_exit_reaped':status is not None,
            'whole_field_pass':False,'supervisor_head_sha256':control.head}
