"""Fixed Linux pre-load fork barrier and independent owned-child watchdog.

Never imported/called from Rhino. No fork, signal, model or filesystem writes
on import. The caller must first check the complete two-hash entry scope.
"""
import math
import os
from pathlib import Path
import selectors
import signal
import struct
import sys
import time

from training.c5_reuse_evidence import require,sha
from training.c5_reuse_owned_child import OwnedChildStop,POLICY
from training.c5_reuse_process_identity import OwnedPidfdOperations,LinuxIdentity
from training.c5_reuse_control_journal import ControlJournal,read_control
from training.c5_reuse_field_journal import FieldJournal
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_budget import ReuseBudget

PACKET=struct.Struct('!cd')


class Watchdog:
    def __init__(self,start,cap,*,clock=time.monotonic,limits=None):
        require(type(start) in (int,float) and math.isfinite(start) and 0<cap<=3600,'reuse_watchdog_reservation')
        self.limits=limits
        self.startup=180 if limits is None else limits['startup_seconds']
        self.first_gap=180 if limits is None else limits['first_request_idle_seconds']
        self.native_gap=180 if limits is None else limits['between_requests_idle_seconds']
        self.begun=limits is None
        self.clock=clock;self.last=start;self.hard=start+cap;self.deadline=min(self.hard,start+self.startup)
        self.ready=False;self.pending=False;self.stages=0;self.buffer=b'';self.last_packet=start
        self.request_active=False;self.requests=0

    def check(self):
        now=self.clock()
        require(math.isfinite(now) and self.last<=now<self.deadline,'reuse_supervisor_watchdog_deadline')
        self.last=now
        return self.deadline-now

    def feed(self,chunk):
        self.check()
        require(type(chunk) is bytes and 0<len(chunk)<=4096,'reuse_watchdog_progress_bytes')
        self.buffer+=chunk
        while len(self.buffer)>=PACKET.size:
            kind,issued=PACKET.unpack(self.buffer[:PACKET.size]);self.buffer=self.buffer[PACKET.size:]
            now=self.clock()
            require(math.isfinite(issued) and self.last_packet<=issued<=now,'reuse_watchdog_progress_time')
            self.last_packet=issued
            if kind==b'L':
                require(not self.ready and not self.pending,'reuse_watchdog_duplicate_ready')
                self.ready=True
                self.deadline=min(self.hard,issued+180)
            elif kind==b'B':
                require(self.limits is not None and self.ready and not self.begun and not self.request_active
                        and not self.pending and self.requests==0,'reuse_watchdog_once_begin')
                self.begun=True;self.deadline=min(self.hard,issued+self.first_gap)
            elif kind==b'R':
                require(self.ready and self.begun and not self.request_active and not self.pending and self.requests<8,
                        'reuse_watchdog_whole_request_start')
                self.request_active=True;self.requests+=1
                self.deadline=min(self.hard,issued+180)
            elif kind==b'D':
                require(self.request_active and not self.pending,'reuse_watchdog_whole_request_end')
                self.request_active=False
                self.deadline=min(self.hard,issued+self.native_gap)
            elif kind==b'S':
                require(self.ready and self.request_active and not self.pending and self.stages<112,'reuse_watchdog_stage_order')
                self.stages+=1;self.pending=True
            elif kind==b'E':
                require(self.ready and self.request_active and self.pending,'reuse_watchdog_unmatched_return')
                self.pending=False
            else:raise ValueError('reuse_watchdog_unknown_progress')


def progress(fd,kind):
    raw=PACKET.pack(kind,time.monotonic())
    require(os.write(fd,raw)==len(raw),'reuse_watchdog_atomic_progress')


def child_main(binding,plans,journal,registry,gate_fd,progress_fd,qualification,inventory,guard,budget,runtime,plan):
    """Inherited raw journal is exclusively transferred; parent never appends."""
    require(os.read(gate_fd,2)==b'G','reuse_child_load_barrier')
    os.close(gate_fd)
    guard();budget.check()
    registry.close()  # No SQLite connection is reused across fork.
    lifecycle=ControlJournal(binding,'worker-lifecycle')
    lifecycle.append('model_loading_intent',{'qualification_sha256':qualification,'worker_open_head_sha256':journal.head})
    from training.c5_reuse_gpu_loader import load
    tokenizer,generate,route,check=load(Path(binding['paths']['source_root']),inventory,guard,budget.check,runtime=runtime,plan=plan)
    lifecycle.append('model_loaded',{'qualification_sha256':qualification,'training':False,'parse_repair':False})
    from training.c5_reuse_generation import GenerationPeer
    peer=GenerationPeer(binding,registry,plans,tokenizer,None,route,check,budget.check,journal=journal)
    def watched_generate(prompt,stage):
        check();progress(progress_fd,b'S')
        value=generate(prompt,stage)
        progress(progress_fd,b'E');check()
        return value
    peer.generate=watched_generate
    from training.c5_reuse_field_transport import FieldPipe
    from training.c5_reuse_worker_loop import serve
    pipe=FieldPipe(sys.stdout.fileno(),sys.stdin.fileno())
    serve(peer,pipe,qualification,check,budget.check,lifecycle.append,on_ready=lambda:progress(progress_fd,b'L'),
          on_request_start=lambda:progress(progress_fd,b'R'),on_request_end=lambda:progress(progress_fd,b'D'),
          on_begin=lambda:progress(progress_fd,b'B'))
    lifecycle.append('worker_budget_observation',budget.observation())


def supervise(spec,runtime,binding,plan,guard):
    require(sys.platform=='linux' and hasattr(os,'fork') and hasattr(os,'pidfd_open')
            and hasattr(signal,'pidfd_send_signal'),'reuse_linux_owned_child_primitives')
    import threading
    require(threading.active_count()==1 and 'torch' not in sys.modules,'reuse_fork_before_threads_or_model_import')
    from training.c5_reuse_gpu_loader import validate_plan,verify_entry_process,preflight
    from training.c5_reuse_development_plan import public_plan
    validate_plan(spec,runtime,plan)
    parent=verify_entry_process(binding,plan,LinuxIdentity())
    guard()
    # Time before fork is included in the one parent/child wall reservation.
    budget=ReuseBudget(spec['resources'])
    watchdog=Watchdog(budget.start_mono,budget.cap,limits=binding['limits'])
    control=ControlJournal(binding,'supervisor')
    registry=AdmissionRegistry(binding)
    owned=None;pid=None;gate_r=gate_w=progress_r=progress_w=None;wait_status=None
    try:
        journal=FieldJournal(binding,'worker',registry)  # Global claim before any launch/load.
        inventory=preflight(runtime,plan,guard);budget.check();watchdog.check()
        plans=public_plan(Path(binding['paths']['source_root']))['task_plans']
        require(sha(plans)==binding['development_plan_sha256'],'reuse_supervisor_plans')
        gate_r,gate_w=os.pipe();progress_r,progress_w=os.pipe()
        control.append('child_launch_intent',{'parent':parent,'worker_open_head_sha256':journal.head,
                                             'policy_sha256':sha(POLICY),'budget':budget.observation()})
        guard();budget.check();sys.stdout.flush();sys.stderr.flush()
        def interrupted(*_):raise TimeoutError('reuse_supervisor_termination')
        previous={kind:signal.signal(kind,interrupted) for kind in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT)}
        pid=os.fork()
        if pid==0:
            for kind in previous:signal.signal(kind,signal.SIG_DFL)
            os.close(gate_w);os.close(progress_r)
            try:
                # Qualification is known only after the supervisor pins
                # this exact child and publishes durable pre-load evidence.
                require(os.read(gate_r,2)==b'G','reuse_child_load_barrier')
                os.close(gate_r)
                rows=read_control(control.root,binding,'supervisor')
                qualified=[r for r in rows if r['kind']=='owned_child_qualified']
                require(len(qualified)==1 and qualified[0]['payload']['target']==LinuxIdentity()(os.getpid())
                        and qualified[0]['payload']['parent_pid']==os.getppid(),'reuse_child_original_qualification')
                # A new local pipe keeps child_main's load barrier explicit;
                # only this verified branch may issue its permit.
                local_r,local_w=os.pipe();os.write(local_w,b'G');os.close(local_w)
                child_main(binding,plans,journal,registry,local_r,progress_w,
                           sha(qualified[0]['payload']),inventory,guard,budget,runtime,plan)
                os._exit(0)
            except BaseException as error:
                try:sys.stderr.write('reuse child retired: '+type(error).__name__+'\n');sys.stderr.flush()
                finally:os._exit(1)
        os.close(gate_r);gate_r=None;os.close(progress_w);progress_w=None
        owned=OwnedChildStop(binding,POLICY,os.getpid(),pid,
                             OwnedPidfdOperations(lambda:guard(cleanup_only=True)),control.append,registry)
        require(owned.expected['uid']==parent['uid'] and owned.expected['boot_id']==parent['boot_id']
                and owned.expected['argv_sha256']==parent['argv_sha256']
                and owned.expected['executable_sha256']==parent['executable_sha256']
                and owned.expected['cwd']==parent['cwd'],'reuse_owned_child_expected_process')
        guard();budget.check();watchdog.check()
        require(os.write(gate_w,b'G')==1,'reuse_parent_load_permit')
        os.close(gate_w);gate_w=None
        os.set_blocking(progress_r,False)
        with selectors.DefaultSelector() as selector:
            selector.register(owned.fd,selectors.EVENT_READ,'exit')
            selector.register(progress_r,selectors.EVENT_READ,'progress')
            while True:
                budget.check();guard()
                events=selector.select(min(watchdog.check(),1))
                if any(event.data=='exit' for event,_ in events):break
                for event,_ in events:
                    chunk=os.read(progress_r,4096)
                    if chunk:watchdog.feed(chunk)
                    else:selector.unregister(progress_r)
    finally:
        # Revocation by closing an unopened gate makes an unqualified child
        # exit without signals. Qualified children use only the frozen stop.
        for fd in (gate_r,gate_w,progress_r,progress_w):
            if fd is not None:os.close(fd)
        try:
            try:
                if owned is not None:
                    try:owned.stop()
                    finally:owned.close()
            finally:
                if pid is not None and pid>0:
                    observed,status=os.waitpid(pid,os.WNOHANG)
                    if observed==pid:wait_status=status
                control.append('supervisor_final_observation',{'child_wait_status':wait_status,'child_exit_reaped':wait_status is not None,
                            'budget':budget.observation(),'physical_gpu_release_verified':None,'whole_field_pass':False})
        finally:
            registry.close()
            if 'previous' in locals():
                for kind,handler in previous.items():signal.signal(kind,handler)
    require(budget.observation()['within_reserved_wall_seconds'],'reuse_supervisor_reserved_wall_exceeded')
    return {'child_exit_reaped':wait_status is not None,'child_exit_success':wait_status==0,
            'supervisor_head_sha256':control.head,'physical_gpu_release_verified':None,'whole_field_pass':False}


def independent_stop(spec,runtime,binding,plan,guard):
    from training.c5_reuse_gpu_loader import validate_plan
    validate_plan(spec,runtime,plan);guard(cleanup_only=True)
    root=Path(binding['paths']['state_root'])/'supervisor'
    rows=read_control(root,binding,'supervisor')
    launch=[r for r in rows if r['kind']=='child_launch_intent']
    qualified=[r for r in rows if r['kind']=='owned_child_qualified']
    require(len(launch)==len(qualified)==1 and launch[0]['seq']<qualified[0]['seq']
            and launch[0]['payload']['parent']['pid']==qualified[0]['payload']['parent_pid']
            and launch[0]['payload']['policy_sha256']==sha(POLICY),'reuse_stop_original_control_order')
    current_parent=LinuxIdentity()(qualified[0]['payload']['parent_pid'])
    require(current_parent==launch[0]['payload']['parent'],'reuse_stop_original_parent_identity')
    control=ControlJournal(binding,'independent-stop')
    control.append('original_qualification_anchor',{'supervisor_prefix_head_sha256':rows[-1]['record_sha256'],
                                                 'qualification_record_sha256':qualified[0]['record_sha256']})
    with AdmissionRegistry(binding) as registry:
        owned=OwnedChildStop.recheck_qualified(binding,qualified[0]['payload'],
                     OwnedPidfdOperations(lambda:guard(cleanup_only=True)),control.append,registry)
        try:return owned.stop()
        finally:owned.close()
