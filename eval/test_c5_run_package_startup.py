"""Real owner->permit->worker CLI->fork->ready->abort CPU regression.

Only installed Rhino, model loading, deployment filesystem and owner typing are
CPU fixtures. Complete public spec/grant validation, campaign replay, process,
stdin/stdout frames, watchdog, qualification and shared stop are real code.
No actual research root, sealed input, GPU model or grant is touched.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.skipif(sys.platform!='linux' or not hasattr(os,'pidfd_open'),reason='actual Linux fork/pidfd startup')
def test_full_approved_spec_to_real_owner_and_worker_startup(tmp_path):
    script=r'''
import contextlib,io,json,os,sys,time,types
from pathlib import Path
sys.path.insert(0,REPO)
from plugin.rhino_listener.c5_followup_profile import GPU_FLAGS
from plugin.rhino_listener.c5_research_native import digest
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from training.c5_reuse_process_identity import LinuxIdentity
from plugin.rhino_listener import c5_formal_reuse_scope as scoped
from training import c5_formal_reuse_ssh as ssh
from training import c5_formal_reuse_admission as admission
from training import c5_formal_reuse_revision as revision
from training.c5_recovery_storage import EvidenceLog
from training.c5_formal_reuse_admission import FormalCampaign,campaign_scope
from training.c5_recovery_policy import POLICY
root=Path.cwd();gpu=root/'gpu-state';gpu.mkdir(mode=0o700,exist_ok=True)
s=json.loads((Path(REPO)/'eval/c5/formal-reuse-spec-20261022-r1.json').read_bytes())
f=json.loads((Path(REPO)/'eval/c5/formal-reuse-runtime-freeze-20261022-r1.json').read_bytes())
grant=scoped.expected_grant(s,f)
# The complete actual public spec/runtime shape and exact pair are validated.
scoped.authority(s,f,grant,check_time=False)
real_mono=time.monotonic;begin=real_mono()
time.time=lambda:1792692329.837715+10000+real_mono()-begin
def guard():
 assert grant==scoped.expected_grant(s,f)
scoped.REMOTE_SOURCE=root;scoped.REMOTE_ENV=Path(sys.executable).resolve().parent.parent
scoped.REMOTE_STATE=gpu
ssh.REMOTE_SOURCE=root;ssh.REMOTE_ENV=scoped.REMOTE_ENV
ssh.verify=lambda *args:None
def argv(spec,mode,attempt):
 return [str(Path(sys.executable).resolve()),*GPU_FLAGS,str(root/'tools/run_c5_formal_reuse_worker.py'),mode,'--attempt',str(attempt)]
ssh.argv=argv

if sys.argv[1]=='worker':
 import tools.run_c5_formal_reuse_worker as worker
 import training.c5_formal_reuse_supervisor as supervisor
 import training.c5_formal_reuse_control as control
 import training.c5_followup_gpu_loader as loader
 worker.ROOT=root;worker.REMOTE_STATE=gpu
 admission.attempt_state=lambda endpoint,attempt:gpu/('preload-'+str(attempt))
 supervisor.claim_gpu_role=lambda *args:None # Separate actual role-population tests cover this boundary.
 def scope(*,with_assets=True):
  scoped.authority(s,f,grant,check_time=False)
  return s,f,digest(f),guard,{'environment_sha256':f['environment_sha256']},{},root
 worker.approved_scope=scope
 control.control_scope=lambda actual:(s,f,guard)
 def cpu_load(*args,**kwargs):
  sys.modules['torch']=types.SimpleNamespace(version=types.SimpleNamespace(cuda='CPU-fixture'),
   cuda=types.SimpleNamespace(get_device_name=lambda _: 'NVIDIA GeForce RTX 3090'))
  return None,None,None,guard
 loader.load=cpu_load
 original_check=subprocess.check_output if False else __import__('subprocess').check_output
 def cpu_status(args,**kw):
  if args[0]=='nvidia-smi':
   return f['field_plan']['gpu_process']['gpu_uuid']+', 11\n' if '--query-gpu=uuid,memory.used' in args else ''
  return original_check(args,**kw)
 __import__('subprocess').check_output=cpu_status
 # Actual ownership facts are Linux process boundaries, not fabricated loader success.
 f['field_plan']['gpu_process']['uid']=os.getuid()
 f['field_plan']['gpu_process']['boot_id']=LinuxIdentity()(os.getpid())['boot_id']
 # These two observation fields are re-bound BEFORE both fixture grants.
 # Recompute the exact complete pair in both owner and worker fixture scopes.
 grant=scoped.expected_grant(s,f)
 if not (gpu/'owner-approval.json').exists():publish_json(gpu,'owner-approval.json',grant)
 sys.argv=[sys.argv[0],*sys.argv[2:]]
 worker.main();raise SystemExit(0)

import tools.c5_formal_reuse_owner as owner
from training.c5_formal_reuse_adapters import ModelAdapterV2
f['field_plan']['gpu_process']['uid']=os.getuid()
f['field_plan']['gpu_process']['boot_id']=LinuxIdentity()(os.getpid())['boot_id']
grant=scoped.expected_grant(s,f);scoped.authority(s,f,grant,check_time=False)
publish_json(gpu,'owner-approval.json',grant)
logroot=root/'ledger';log=EvidenceLog(logroot,f['incremental_revision']['initial_campaign_scope'],guard,create=True)
for row in f['incremental_revision']['prior_campaign_events']:assert log.append(row['kind'],row['payload'])==row
initial=FormalCampaign(log.binding,log)
from training.c5_reuse_evidence import sha
revised=campaign_scope(s,f);head=log.rows()[-1]['record_sha256']
initial.accept_revision(revised,{'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],
 'scope_sha256':sha(revised),'spec_sha256':revised['spec_sha256'],'runtime_sha256':revised['runtime_sha256'],
 'policy_sha256':sha(POLICY),'previous_campaign_head_sha256':head});log.close()
def campaign(*args,**kw):return FormalCampaign(revised,EvidenceLog(logroot,f['incremental_revision']['initial_campaign_scope'],guard))
owner.open_formal_campaign=campaign
owner.scope=lambda **kw:(s,f,grant,guard)
owner.commitment=lambda _:{}
owner.attempt_state=lambda endpoint,attempt:root/('preload-'+str(attempt))
owner.sys.stdin=types.SimpleNamespace(isatty=lambda:True)
owner.sys.stderr=types.SimpleNamespace(isatty=lambda:True,write=lambda value:None,flush=lambda:None)
def confirm(scope,snap,guard):
 return {'actor':'repository_owner',**snap,'before_model_loading':True,
  'public_attempts_authorized':0,'human_origin_cryptographically_proven':False}
owner.confirm_preload=confirm
class Native:
 def __init__(self,state,spec,freeze,**kwargs):self.state=state;self.hub=None
 def arm(self):publish_json(self.state,'formal20.zero-prepared.json',{'study_id':s['study_id'],'runtime_freeze_sha256':digest(f),'private_rows_read':0,'model_calls':0})
 def wait_zero_ready(self):publish_json(self.state,'host-continuity-ready.json',{'study_id':s['study_id'],'runtime_freeze_sha256':digest(f),'legacy_byte_closure_verified':False,'sealed_before_model_generation':True})
 def finish(self):
  if not (self.state/'preload-abort.response.json').exists():publish_json(self.state,'preload-abort.response.json',{'cpu_native_cleanup':True})
owner.NativeAdapterV2=Native
def private_boundary(_):raise KeyboardInterrupt('CPU fixture stops before private path or exposure')
owner.getpass.getpass=private_boundary
try:owner.run_interactive(2)
except KeyboardInterrupt:pass
state=root/'preload-2'
assert (state/'worker-startup-ready.json').exists()
assert read_json(state,'worker-process-exit.json')['exit_code']==0
assert read_json(state,'raw-streams-final.json')['complete_raw_capture'] is True
assert not (state/'formal20.started.json').exists()
original=read_json(state,'export-supervisor-original.json')
assert original['final']['child_wait_status']==0 and original['final']['child_exit_reaped']
assert original['final']['stop_result']['signal_attempts']==0
c=campaign();value=c.observation();c.log.close()
assert value['attempts']==2 and not value['formal_consumed'] and value['first_load_epoch']==1792692329.837715
print(json.dumps({'full_public_authority_checked':True,'actual_owner_worker_cli_startup':True,
 'actual_fork_qualified_before_loader':True,'actual_ready_frame':True,'natural_abort_exit':True,
 'private_exposures':0,'first_load_epoch_preserved':True}))
'''
    script=script.replace('REPO',repr(str(ROOT)))
    (tmp_path/'tools').mkdir()
    entry=tmp_path/'tools/run_c5_formal_reuse_worker.py'
    launcher=tmp_path/'fixture.py';launcher.write_text(script)
    entry.write_text('import runpy,sys\nsys.argv.insert(1,"worker")\nrunpy.run_path('+repr(str(launcher))+',run_name="__main__")\n')
    result=subprocess.run([sys.executable,'-I','-B',str(launcher),'owner'],cwd=tmp_path,
                          capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stderr
    v=json.loads(result.stdout.splitlines()[-1])
    assert v['actual_owner_worker_cli_startup'] and v['actual_ready_frame'] and v['private_exposures']==0
