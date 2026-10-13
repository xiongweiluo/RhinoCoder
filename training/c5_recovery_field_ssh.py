"""Pinned existing SSH master only. No reconnect, shell input or old entry."""
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from plugin.rhino_listener.c5_recovery_scope import paths as fixed_paths,validate_preload_begin
from plugin.rhino_listener.c5_recovery_runtime_scope import read_bytes
from training.c5_reuse_evidence import exact,is_sha,raw_sha,require,sha
from training.c5_reuse_field_scope import validate_binding,PROTOCOL,common_scope
from training.c5_reuse_process_identity import stable_file_sha
from plugin.rhino_listener.c5_recovery_profile import PYTHON,ENTRY
from training.c5_reuse_field_journal import FieldJournal
from training.c5_reuse_control_journal import ControlJournal
from training.c5_reuse_field_transport import FieldPipe,FieldModelChannel
from training.c5_reuse_worker_loop import receive,send,validate_begin
from training.c5_followup_diagnostics import CapturedStreams,CapturedPipe
from plugin.rhino_listener.c5_followup_profile import GPU_FLAGS

SSH=Path('/usr/bin/ssh')
POLICY={'host':'175.155.64.171','port':24151,'user':'linux',
        'socket':'/private/tmp/c5-reuse-24151.control',
        'known_hosts':'/Users/xiongweiluo/RhinoCoder/data/training/c5/known-hosts-22159',
        'known_hosts_sha256':'ae41a99e39f76b1be352f0098439b126fe5b8465c358b8dabbb7a71e53d2d1a9',
        'host_key_alias':'[175.155.64.171]:22159','automatic_reconnect':False,
        'local_shell':False,'remote_entry':ENTRY,'connection_timeout_seconds':15,
        'diagnostic_stderr_retained':True,'stdout_capture_cap_bytes':67108864,'stderr_capture_cap_bytes':262144,'automatic_signal_escalation':False}


class RecoveryCapturedStreams(CapturedStreams):
    """Add only fixed proof names; retain the original bounded pump/seal."""
    def __init__(self,root,prefix,*,stdout_cap=67108864,stderr_cap=262144):
        if prefix in ('serve','stop','export'):
            super().__init__(root,prefix,stdout_cap=stdout_cap,stderr_cap=stderr_cap);return
        require(prefix in ('ready-proof','failure-proof'),'recovery_fixed_proof_capture_name')
        import queue,threading
        from training.c5_followup_diagnostics import RawFile
        root=Path(root)
        require(root.is_absolute() and root.resolve()==root and root.is_dir()
            and stat.S_IMODE(root.stat().st_mode)==0o700 and root.stat().st_uid==os.getuid(),
            'followup_capture_root')
        self.stdout=RawFile(root/(prefix+'-stdout.raw'),stdout_cap)
        try:self.stderr=RawFile(root/(prefix+'-stderr.raw'),stderr_cap)
        except BaseException:self.stdout.finish(None);raise
        self.queue=queue.Queue(maxsize=16);self.delivery_overflow=False;self.stop=threading.Event()
        self.threads=[];self.process=None;self.finished=False


def validate_transport(value):
    exact(value,('policy','ssh_executable_sha256'))
    require(value['policy']==POLICY and is_sha(value['ssh_executable_sha256']),'reuse_fixed_transport_policy')


def command(mode,attempt=1):
    require(mode in ('serve','stop','export','check','ready-proof','failure-proof'),'reuse_fixed_ssh_mode')
    args=[str(SSH),'-F','/dev/null','-T','-S',POLICY['socket'],
        '-o','BatchMode=yes','-o','ControlMaster=no','-o','ProxyCommand=/usr/bin/false',
        '-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no',
        '-o','UserKnownHostsFile='+POLICY['known_hosts'],'-o','HostKeyAlias='+POLICY['host_key_alias'],
        '-o','ConnectTimeout=15','-p',str(POLICY['port'])]
    if mode=='check':args+=['-O','check']
    args+=[POLICY['user']+'@'+POLICY['host']]
    if mode!='check':
        # These fixed ASCII paths contain no whitespace/shell metacharacters.
        # No model text, case, path or caller argument reaches the remote shell.
        root=fixed_paths('gpu',attempt)['source_root']
        args+=['cd '+root+' && '+str(PYTHON)+' '+' '.join(GPU_FLAGS)+' '+root+'/'+ENTRY+' --'+mode+' --attempt '+str(attempt)]
    return args


def master_pin(transport):
    validate_transport(transport)
    require(stable_file_sha(SSH)==transport['ssh_executable_sha256'],'reuse_ssh_binary_drift')
    require(raw_sha(read_bytes(POLICY['known_hosts']))==POLICY['known_hosts_sha256'],'reuse_ssh_host_key_pin')
    p=Path(POLICY['socket']);info=p.lstat()
    require(p.resolve()==p and stat.S_ISSOCK(info.st_mode) and info.st_uid==os.getuid()
            and info.st_nlink==1 and not info.st_mode&0o077,'reuse_existing_master_socket')
    result=subprocess.run(command('check'),capture_output=True,timeout=15)
    require(result.returncode==0 and not result.stdout
            and re.fullmatch(rb'Master running \(pid=[1-9][0-9]*\)\r?\n?',result.stderr),'reuse_existing_master_check')
    current=p.lstat()
    require((current.st_dev,current.st_ino,current.st_uid,current.st_mode)==
            (info.st_dev,info.st_ino,info.st_uid,info.st_mode),'reuse_master_socket_changed')
    return {'device':info.st_dev,'inode':info.st_ino,'master_check_raw_sha256':raw_sha(result.stderr),
            'master_check_is_not_remote_model_or_host_origin_proof':True}


def validate_ready(binding,value):
    exact(value,('kind','protocol','scope_sha256','qualification_sha256','worker_open_head_sha256',
                'model_requests_before_ready','generation_stages_before_ready'))
    require(value['kind']=='reuse_worker_loaded_ready' and value['protocol']==PROTOCOL
            and value['scope_sha256']==sha(common_scope(binding))
            and is_sha(value['qualification_sha256']) and is_sha(value['worker_open_head_sha256'])
            and all(type(value[k]) is int and value[k]==0 for k in ('model_requests_before_ready','generation_stages_before_ready')),
            'reuse_loaded_readiness_scope')


class FieldSSHSession:
    """Actual Mac entry supplies a verified guard/budget and master plan.

    This helper cannot verify human approval/readiness origin. Its source is
    inert; calling it with fabricated records is not execution authorization.
    """
    def __init__(self,binding,registry,plans,transport,guard,budget,*,load_permit):
        validate_binding(binding);validate_transport(transport)
        require(binding['endpoint']=='mac' and binding['endpoints']=={e:fixed_paths(e,binding['recovery']['attempt'],binding['runtime_sha256']) for e in ('mac','gpu')},
                'reuse_ssh_exact_endpoint_roots')
        self.binding,self.transport,self.guard,self.budget=binding,transport,guard,budget
        self.attempt=binding['recovery']['attempt']
        self.load_permit=load_permit
        self.process=None;self.pipe=None;self.ready=None;self.begin_spent=False;self.close_spent=False;self.stop_spent=False
        self.export_spent=False
        guard();budget()
        journal=FieldJournal(binding,'controller',registry)  # Before SSH/model startup.
        self.lifecycle=ControlJournal(binding,'controller-lifecycle')
        pin=master_pin(transport);guard();budget()
        self.lifecycle.append('remote_launch_intent',{'argv':command('serve',self.attempt),'master_pin':pin,
            'controller_open_head_sha256':journal.head})
        guard();budget()
        self.capture=CapturedStreams(Path(binding['paths']['state_root']),'serve')
        self.diagnostics_spent=False
        self.lifecycle.append('raw_streams_created_before_launch',{'stdout_cap':67108864,'stderr_cap':262144})
        try:
            self.process=subprocess.Popen(command('serve',self.attempt),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
            self.capture.start(self.process,protocol=True)
            from training.c5_reuse_evidence import canonical
            from training.c5_recovery_storage import write_once
            write_once(Path(binding['paths']['state_root']),'load-permit.json',load_permit)
            raw=canonical(load_permit)+b'\n'
            require(len(raw)<=1048576,'recovery_load_permit_capacity')
            offset=0
            while offset<len(raw):
                guard();budget();n=os.write(self.process.stdin.fileno(),raw[offset:]);require(n>0,'recovery_load_permit_write');offset+=n
            self.lifecycle.append('preload_permit_sent',{'permit_sha256':sha(load_permit)})
            self.pipe=CapturedPipe(self.process.stdin.fileno(),self.process.stdout.fileno(),self.capture)
            self.channel=FieldModelChannel(binding,registry,self.pipe,self._check,budget,plans,journal=journal)
        except BaseException:
            if self.process is not None and not self.stop_spent:
                try:self.independent_stop()
                except BaseException:pass
            if not self.diagnostics_spent:
                try:self.finalize_diagnostics()
                except BaseException:pass
            raise

    def _check(self):self.capture.check();self.guard();self.budget()

    def await_ready(self):
        require(self.ready is None and not self.close_spent,'reuse_ssh_ready_no_retry')
        self.close_spent=True  # Unknown startup is permanently retired.
        value=receive(self.pipe,time.monotonic()+self.binding['limits']['startup_seconds'],self._check)
        validate_ready(self.binding,value)
        self.lifecycle.append('remote_ready_received',{'ready':value,'human_or_model_origin_verified':False})
        self._check();self.ready=value;self.close_spent=False
        return value

    def begin(self,value):
        require(self.ready is not None and not self.begin_spent and not self.close_spent,'recovery_begin_once')
        validate_preload_begin(self.binding,value)
        require(value['worker_readiness_sha256']==sha(self.ready),'recovery_current_worker_ready_binding')
        self.begin_spent=True
        self.lifecycle.append('external_begin_send_intent',{'begin':value,'human_provenance_independently_verified':False})
        send(self.pipe,value,time.monotonic()+180,self._check)
        self.lifecycle.append('external_begin_sent',{'begin_sha256':sha(value)})

    def ready_proof(self):
        result=self._captured_command('ready-proof')
        require(result.returncode==0,'recovery_ready_proof_transport')
        from training.c5_reuse_evidence import strict
        raw=read_bytes(Path(self.binding['paths']['state_root'])/'ready-proof-stdout.raw',limit=1048576,private=True)
        return strict(raw,limit=1048576)

    def close(self):
        require(self.begin_spent and not self.close_spent and len(self.channel.spent)==8,'reuse_ssh_complete_close_no_retry')
        self.close_spent=True
        value={'kind':'reuse_worker_close','protocol':PROTOCOL,'scope_sha256':sha(common_scope(self.binding))}
        self.lifecycle.append('worker_close_send_intent',{'close':value})
        send(self.pipe,value,time.monotonic()+180,self._check)
        receipt=receive(self.pipe,time.monotonic()+180,self._check)
        exact(receipt,('kind','protocol','scope_sha256','worker_final_head_sha256','requests','generation_intents',
                       'physical_gpu_release_verified','whole_field_pass'))
        require(receipt['kind']=='reuse_worker_closed' and receipt['protocol']==PROTOCOL
                and receipt['scope_sha256']==sha(common_scope(self.binding)) and is_sha(receipt['worker_final_head_sha256'])
                and type(receipt['requests']) is int and receipt['requests']==8
                and type(receipt['generation_intents']) is int and 8<=receipt['generation_intents']<=16
                and receipt['physical_gpu_release_verified'] is None and receipt['whole_field_pass'] is False,
                'reuse_ssh_close_receipt')
        self.lifecycle.append('worker_close_received',{'receipt':receipt})
        self.process.stdin.close()
        require(self.process.wait(timeout=30)==0,'reuse_ssh_remote_supervisor_failed')
        self.lifecycle.append('remote_supervisor_exit_observed',{'ssh_exit_status':0,'physical_gpu_release_verified':None})
        diagnostic=self.finalize_diagnostics()
        require(diagnostic['complete_raw_capture'] and not diagnostic['protocol_delivery_overflow']
            and diagnostic['unconsumed_protocol_tail_bytes']==0,'followup_remote_diagnostic_incomplete_no_retry')
        return receipt

    def independent_stop(self):
        require(not self.stop_spent,'reuse_ssh_stop_no_retry');self.stop_spent=True
        self.guard(cleanup_only=True)
        pin=master_pin(self.transport)
        self.lifecycle.append('independent_stop_send_intent',{'argv':command('stop',self.attempt),'master_pin':pin})
        self.guard(cleanup_only=True)
        result=self._captured_command('stop')
        self.lifecycle.append('independent_stop_command_result',{'ssh_exit_status':result.returncode,
                    'physical_gpu_release_verified':None,'retry_allowed':False})
        require(result.returncode==0,'reuse_ssh_independent_stop_unknown_no_retry')
        return {'ssh_exit_status':0,'physical_gpu_release_verified':None}

    def export(self):
        require(self.close_spent and self.process.poll()==0 and not self.export_spent,'reuse_export_after_known_exit_once')
        self.export_spent=True;self.guard(cleanup_only=True);pin=master_pin(self.transport)
        path=Path(self.binding['paths']['state_root'])/'gpu-public-eight-raw-export.json'
        result=self._captured_command('export')
        require(result.returncode==0,'reuse_export_unknown_no_retry')
        raw=read_bytes(Path(self.binding['paths']['state_root'])/'export-stdout.raw',limit=64*1024*1024,private=True)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            offset=0
            while offset<len(raw):
                n=os.write(fd,raw[offset:]);require(n>0,'followup_export_write');offset+=n
            os.fsync(fd)
        finally:os.close(fd)
        raw=read_bytes(path,limit=64*1024*1024,private=True)
        self.lifecycle.append('gpu_export_observed',{'raw_sha256':raw_sha(raw),'bytes':len(raw),
            'human_or_physical_origin_proven_by_export_hash':False})
        return raw

    def finalize_diagnostics(self):
        require(not self.diagnostics_spent,'followup_diagnostic_finalize_no_retry');self.diagnostics_spent=True
        value=self.capture.finish();self.lifecycle.append('raw_streams_final_observed',value);return value

    def _captured_command(self,mode):
        from types import SimpleNamespace
        capture=RecoveryCapturedStreams(Path(self.binding['paths']['state_root']),mode,
            stdout_cap=67108864 if mode=='export' else 262144)
        process=None
        try:
            process=subprocess.Popen(command(mode,self.attempt),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
            capture.start(process,protocol=False);deadline=time.monotonic()+60
            while process.poll() is None and time.monotonic()<deadline:time.sleep(0.05)
        finally:
            value=capture.finish();self.lifecycle.append(mode+'_raw_streams_final_observed',value)
        require(value['complete_raw_capture'],'followup_command_exit_or_raw_capture_unknown_no_retry')
        return SimpleNamespace(returncode=process.returncode)
