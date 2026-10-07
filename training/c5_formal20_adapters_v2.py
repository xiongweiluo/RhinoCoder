"""Owner-side v2 adapters. New exact scope gate precedes construction/use.

Zero-stage arming/loading has no task input. It is still a separately approved
live operation, not a CPU preflight. Only the owner entry invokes it.
"""
import os
import time
import secrets
import subprocess

from training.c5_formal20_adapters import NativeAdapter, ModelAdapter
from training.c5_formal20_transport_v2 import NativeChannelV2, FormalLifecyclePipe
from plugin.rhino_listener.c5_formal20_scope_v2 import (
    STUDY_ID,REMOTE_SOURCE,REMOTE_ENV,SSH_SOCKET,SSH_PORT,SSH_KNOWN_HOSTS,SSH_KNOWN_HOSTS_SHA,native_plans)
from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import require,digest
from training.c5_model_transport import request,rebind_observation
from training.c5_startup_transport import startup_receipt
from training.c5_modelbridge_runtime import file_sha


class NativeAdapterV2(NativeAdapter):
    def __init__(self,*args,channel_factory=NativeChannelV2,**kwargs):
        super().__init__(*args,channel_factory=channel_factory,**kwargs)
        self.armed=False

    def arm(self):
        self.guard()
        require(not self.armed and not (self.state/'formal20.started.json').exists(),
            'formal zero-stage arm once before private consumption')
        require(read_json(self.state,'formal20.zero-started.claim.json')=={
            'study_id':STUDY_ID,'runtime_freeze_sha256':digest(self.freeze),'replay_allowed':False},
            'new exact zero-stage claim required')
        publish_json(self.state,'hub.key',{'key_hex':secrets.token_bytes(32).hex()})
        self.keys.append((self.state,'hub.key'))
        for n in range(1,21):
            for route in ('base','lora'):
                directory=self.state/('F%02d-%s'%(n,route));directory.mkdir(mode=0o700)
                publish_json(directory,'handoff.key',{'key_hex':secrets.token_bytes(32).hex()})
                self.keys.append((directory,'handoff.key'))
        publish_json(self.state,'formal20.zero-prepared.json',{'study_id':STUDY_ID,
            'runtime_freeze_sha256':digest(self.freeze),'private_rows_read':0,'model_calls':0})
        self.armed=True

    def wait_zero_ready(self):
        deadline=time.monotonic()+self.spec['hub_attach_timeout_seconds']
        self.guard()
        while not (self.state/'host-continuity-ready.json').exists():
            require(not (self.state/'deferred-baseline.failed.json').exists(),'formal host arm failed; no consumption')
            self.guard();require(time.monotonic()<deadline,'formal zero-stage host readiness unknown')
            time.sleep(0.05)
        require(read_json(self.state,'host-continuity-ready.json')=={'study_id':STUDY_ID,
            'runtime_freeze_sha256':digest(self.freeze),'legacy_byte_closure_verified':False,
            'sealed_before_model_generation':True},'formal host ready binding differs')
        self.guard()
        require(time.monotonic()<deadline,'formal complete zero-stage readiness expired; no consumption')

    def prepare(self,plans,*,freeze_sha256):
        self.guard()
        require(self.armed and freeze_sha256==digest(self.freeze)
            and read_json(self.state,'formal20.started.json')['runtime_freeze_sha256']==freeze_sha256,
            'formal pre-armed/private started scope required')
        self.plans=native_plans(plans)
        require(digest(plans['slot_order'])==self.spec['slot_order_sha256'],'formal sealed order differs')
        publish_json(self.state,'native-plans.json',plans)
        publish_json(self.state,'native-prepared.json',{'study_id':STUDY_ID,
            'native_plans_sha256':digest(plans),'runtime_freeze_sha256':freeze_sha256})

    def start(self):
        deadline=time.monotonic()+self.spec['hub_attach_timeout_seconds']
        if self.attach_wait is not None:self.attach_wait()
        while not (self.state/'hub-bootstrap.json').exists():
            require(not (self.state/'formal20.hub-initialization.failed.json').exists(),
                'formal private initialization failed; no retry')
            self.guard()
            require(time.monotonic()<deadline,'formal private hub attachment unknown')
            time.sleep(0.05)
        bootstrap=read_json(self.state,'hub-bootstrap.json')
        require(not (self.state/'formal20.hub-initialization.failed.json').exists()
            and bootstrap['runtime_freeze_sha256']==digest(self.freeze)
            and bootstrap['source_sha256']==self.freeze['source_inventory_sha256']
            and bootstrap['native_plans_sha256']==digest(self.plans),
            'formal actual hub bootstrap differs')
        self.guard()
        channel=self.channel_factory(self.state,bytes.fromhex(read_json(self.state,'hub.key')['key_hex']),
            digest(self.freeze),hub=True,guard=self.guard)
        require(time.monotonic()<deadline,'formal complete hub attachment expired')
        self.hub=channel


class ModelAdapterV2(ModelAdapter):
    def __init__(self,*args,process_factory=subprocess.Popen,pipe_factory=FormalLifecyclePipe,**kwargs):
        super().__init__(*args,process_factory=process_factory,pipe_factory=pipe_factory,**kwargs)
        self.zero_ready=False;self.bootstrapped=False

    def start_zero(self):
        self.guard()
        require(self.process is None and not (self.state/'formal20.started.json').exists(),
            'formal zero model startup once before private consumption')
        require(SSH_SOCKET.is_socket() and file_sha(SSH_KNOWN_HOSTS)==SSH_KNOWN_HOSTS_SHA,
            'formal authenticated pinned SSH required')
        self.stderr_fd=os.open(self.state/'worker-stderr.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        args=['ssh','-T','-S',str(SSH_SOCKET),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+str(SSH_KNOWN_HOSTS),'-o','HostKeyAlgorithms=ssh-ed25519',
            '-p',str(SSH_PORT),'linux@175.155.64.171',
            'cd '+str(REMOTE_SOURCE)+' && '+str(REMOTE_ENV/'bin/python')+' -B -m tools.run_c5_formal20_worker_v2 serve']
        self.process=self.process_factory(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr_fd)
        expected=startup_receipt(STUDY_ID,digest(self.freeze),self.freeze['source_inventory_sha256'],
            self.freeze['environment_sha256'],self.freeze['model_identities'])
        self.pipe=self.pipe_factory(self.process,expected,model_identities=self.freeze['model_identities'],
            timeout=180,startup_timeout=180,journal_state=self.state)
        ready=self.pipe.wait_ready()
        publish_json(self.state,'startup-time.json',self.pipe.last_phase)
        publish_json(self.state,'worker-startup-ready.json',ready)
        self.guard();self.zero_ready=True

    def start(self):
        self.guard()
        require(self.zero_ready and not self.bootstrapped and self.plans is not None,
            'formal zero readiness and one new hash bootstrap required')
        sent={'kind':'formal_bootstrap','study_id':STUDY_ID,'runtime_freeze_sha256':digest(self.freeze),
            'started':read_json(self.state,'formal20.started.json'),'plans':self.plans}
        publish_json(self.state,'worker-bootstrap-request.json',sent)
        value=self.pipe.exchange(sent)
        publish_json(self.state,'worker-bootstrap-response.json',value)
        self.bootstrapped=True

    def infer(self,*,slot_id,route,step_index,task_text,scene,binding,freeze_sha256):
        self.guard()
        require(self.bootstrapped and freeze_sha256==digest(self.freeze),'formal loaded/bootstrap scope required')
        sent=request(STUDY_ID,slot_id,route,step_index,task_text,scene,binding,freeze_sha256,'m-'+secrets.token_urlsafe(24))
        key=digest({'slot':slot_id,'step':step_index,'freeze':freeze_sha256})
        self.attempts.append(key)
        publish_json(self.state,key+'-model-request.json',sent)
        wire=self.pipe.exchange(sent)
        publish_json(self.state,key+'-model-time.json',self.pipe.last_phase)
        publish_json(self.state,key+'-model-response.json',wire)
        observed=rebind_observation(wire,sent,self.freeze['model_identities'][route],binding)
        return {**wire,'observation':observed,'wire_request':sent,'wire_response':wire}

    def stop_zero(self):
        require(not self.bootstrapped,'zero-stage abort cannot follow private bootstrap')
        if self.process is None: return
        try:
            require(self.zero_ready and not self.pipe.blocked,'unknown startup acknowledgement; no reconnect or abort resend')
            sent={'kind':'formal_abort_before_bootstrap','study_id':STUDY_ID,'runtime_freeze_sha256':digest(self.freeze)}
            value=self.pipe.exchange(sent)
            publish_json(self.state,'worker-zero-abort-response.json',value)
        finally:
            self.process.stdin.close()
            try:code=self.process.wait(timeout=180)
            except subprocess.TimeoutExpired:code=None
            self.process.stdout.close()
            if self.stderr_fd is not None:os.close(self.stderr_fd);self.stderr_fd=None
            publish_json(self.state,'worker-process-exit.json',{'exit_code':code,'replay_allowed':False})
        require(code==0,'formal zero-stage worker exit unknown')
