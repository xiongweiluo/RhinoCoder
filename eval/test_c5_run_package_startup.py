"""Real owner->permit->worker CLI->fork->ready->abort CPU regression.

Only installed Rhino, model loading, deployment filesystem and owner typing are
CPU fixtures (including a historical wall epoch and common monotonic offset). Complete public spec/grant validation, campaign replay, process,
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


@pytest.mark.parametrize('package_mode',['r1','r2','r3'])
def test_full_approved_spec_to_real_owner_and_worker_startup(tmp_path,package_mode):
    script=r'''
import contextlib,io,json,os,sys,time,types
from pathlib import Path
_real_mono=time.monotonic
_clock_path=Path.cwd()/'cpu-clock.json'
if not _clock_path.exists():
 _clock_path.write_text(json.dumps({'origin':(1792778000. if PACKAGE_MODE=='r3' else 1792692329.837715+(30000 if PACKAGE_MODE=='r2' else 10000))-_real_mono()}))
_origin=json.loads(_clock_path.read_bytes())['origin']
time.monotonic=lambda:_real_mono()+100000.0
time.time=lambda:_origin+_real_mono()
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
if PACKAGE_MODE in ('r2','r3'):
 name='r3' if PACKAGE_MODE=='r3' else 'r2'
 s=json.loads((Path(REPO)/('eval/c5/reuse-formal-20261023-'+name+'-spec.json')).read_bytes())
 f=json.loads((Path(REPO)/('eval/c5/reuse-formal-20261023-'+name+'-runtime.json')).read_bytes())
 # Current remote historical exit remains unknown in preparation. This explicit
 # CPU fixture supplies a prior cleanup proof, not an assertion about the field.
 package=s['run_package'];package['timing_migration']['gpu_residency_upper_seconds']=package['timing_migration']['legacy_elapsed_debit_seconds']
 f['run_package']=package
 s['execution_ready']=f['execution_ready']=True
 for key in ('current_gpu_full_bytes_verified','current_mac_full_bytes_verified','actual_public_deployment_both_endpoints_verified'):f[key]=True
 f['spec_sha256']=digest(s)
 layout=package['layout'];scoped.PACKAGE_LAYOUT=layout;scoped.INSTANCE=layout['package_id']
 scoped.MAC_SOURCE=Path(layout['mac_source_root']);scoped.MAC_STATE=Path(layout['mac_state_root'])
 scoped.REMOTE_SOURCE=Path(layout['gpu_source_root']);scoped.REMOTE_STATE=Path(layout['gpu_state_root'])
 scoped.SPEC_FILE=layout['spec_file'];scoped.FREEZE_FILE=layout['runtime_file']
grant=scoped.expected_grant(s,f,execution_approved=PACKAGE_MODE in ('r2','r3'))
# Public fixed-layout metadata and CPU OS paths are distinct fixture boundaries.
# Never replace authority: validate the complete actual pair against its public
# layout, then restore the CPU paths used by real qualification/fork/transport.
fixed_public_layout=(scoped.REMOTE_SOURCE,scoped.REMOTE_STATE,scoped.REMOTE_ENV)
def validate_public_pair():
 mapped=(scoped.REMOTE_SOURCE,scoped.REMOTE_STATE,scoped.REMOTE_ENV)
 scoped.REMOTE_SOURCE,scoped.REMOTE_STATE,scoped.REMOTE_ENV=fixed_public_layout
 try:scoped.authority(s,f,grant,check_time=False)
 finally:scoped.REMOTE_SOURCE,scoped.REMOTE_STATE,scoped.REMOTE_ENV=mapped
validate_public_pair()
def guard():
 assert grant==scoped.expected_grant(s,f,execution_approved=PACKAGE_MODE in ('r2','r3'))
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
  validate_public_pair()
  return s,f,digest(f),guard,{'environment_sha256':f['environment_sha256']},{},root
 worker.approved_scope=scope
 control.control_scope=lambda actual:(s,f,guard)
 def cpu_load(*args,**kwargs):
  q=json.loads((gpu/('preload-'+('4' if PACKAGE_MODE=='r3' else '3' if PACKAGE_MODE=='r2' else '2'))/'qualification.json').read_bytes())
  assert q['model_loading_started'] is False and q['target']==LinuxIdentity()(os.getpid())
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
 grant=scoped.expected_grant(s,f,execution_approved=PACKAGE_MODE in ('r2','r3'))
 if not (gpu/'owner-approval.json').exists():publish_json(gpu,'owner-approval.json',grant)
 sys.argv=[sys.argv[0],*sys.argv[2:]]
 worker.main();raise SystemExit(0)

import tools.c5_formal_reuse_owner as owner
from training.c5_formal_reuse_adapters import ModelAdapterV2
f['field_plan']['gpu_process']['uid']=os.getuid()
f['field_plan']['gpu_process']['boot_id']=LinuxIdentity()(os.getpid())['boot_id']
grant=scoped.expected_grant(s,f,execution_approved=PACKAGE_MODE in ('r2','r3'));validate_public_pair()
publish_json(gpu,'owner-approval.json',grant)
logroot=root/'ledger';log=EvidenceLog(logroot,f['incremental_revision']['initial_campaign_scope'],guard,create=True)
prefix=f['run_package']['prior_campaign_events'] if PACKAGE_MODE in ('r2','r3') else f['incremental_revision']['prior_campaign_events']
for row in prefix:assert log.append(row['kind'],row['payload'])==row
from training.c5_reuse_evidence import sha
from training.c5_formal_reuse_admission import formal_replay
observed=formal_replay(log.binding,log.rows());initial=FormalCampaign(observed['scope'],log)
revised=campaign_scope(s,f);head=log.rows()[-1]['record_sha256']
revision_grant={'actor':'repository_owner','approved':True,'protocol':POLICY['protocol'],
 'scope_sha256':sha(revised),'spec_sha256':revised['spec_sha256'],'runtime_sha256':revised['runtime_sha256'],
 'policy_sha256':sha(POLICY),'previous_campaign_head_sha256':head}
if PACKAGE_MODE=='r3':
 p=s['run_package']['slot_protocol']
 initial._event('slot_protocol_revision_accepted',{'scope':revised,'grant':revision_grant,'previous_head_sha256':head,'package':s['run_package'],'original_audit_sha256':p['prior_audit_sha256'],'original_settlement_sha256':p['prior_settlement_sha256']})
 initial._event('slot_owner_session_confirmed',{'scope_sha256':sha(revised),'automatic_receipt_capture':True,'manual_host_ready_attestation':False,'before_model_loading':True})
elif PACKAGE_MODE=='r2':
 prior={'raw_anchor_sha256':'d'*64,'capture_complete':True,'qualified_target_absent':True,
  'known_native_cleanup_complete':True,'private_exposure_absent':True}
 initial._event('run_package_revision_accepted',{'scope':revised,'grant':revision_grant,
  'previous_head_sha256':head,'package':s['run_package'],'accounting_cutover':s['run_package']['timing_migration'],
  'prior_reconciliation':{'proof':prior,'basis':'new_package_authorized_automatic_raw_audit','manual_external_attestation':False}})
 initial._event('package_owner_session_confirmed',{'scope_sha256':sha(revised),'automatic_receipt_capture':True,
  'manual_host_ready_attestation':False,'before_model_loading':True})
else:initial.accept_revision(revised,revision_grant)
log.close()
def campaign(*args,**kw):return FormalCampaign(revised,EvidenceLog(logroot,f['incremental_revision']['initial_campaign_scope'],guard))
owner.open_formal_campaign=campaign
def owner_guard():
 guard()
 if PACKAGE_MODE=='r3' and (root/'preload-4/formal20.zero-readiness.json').exists():raise KeyboardInterrupt('CPU stops after real ready before new work')
owner.scope=lambda **kw:(s,f,grant,owner_guard)
owner.commitment=lambda _:{}
owner.attempt_state=lambda endpoint,attempt:root/('preload-'+str(attempt))
owner.sys=types.SimpleNamespace(stdin=types.SimpleNamespace(isatty=lambda:True),
 stderr=types.SimpleNamespace(isatty=lambda:True))
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
if PACKAGE_MODE in ('r2','r3'):
 import training.c5_formal_reuse_control as owner_control
 import training.c5_formal_run_package_entry as private_entry
 owner_control.control_scope=lambda actual:(s,f,guard)
 private_entry.MAC_STATE=root/'mac-state';private_entry.MAC_STATE.mkdir(mode=0o700)
 owner.verify_private_metadata=lambda *args:private_boundary(None)
attempt=4 if PACKAGE_MODE=='r3' else 3 if PACKAGE_MODE=='r2' else 2
session={'confirmed':True,'sealed':Path('/cpu-fixture.age'),'identity':Path('/cpu-fixture.identity')} if PACKAGE_MODE in ('r2','r3') else None
try:owner.run_interactive(attempt,package_session=session)
except KeyboardInterrupt:pass
state=root/('preload-'+str(attempt))
assert (state/'worker-startup-ready.json').exists()
assert read_json(state,'worker-process-exit.json')['exit_code']==0
assert read_json(state,'raw-streams-final.json')['complete_raw_capture'] is True
assert not (state/'formal20.started.json').exists()
original=read_json(state,'export-supervisor-original.json')
assert original['final']['child_wait_status']==0 and original['final']['child_exit_reaped']
assert original['final']['stop_result']['signal_attempts']==0
c=campaign();value=c.observation();c.log.close()
assert value['attempts']==attempt and value['formal_consumed'] is (PACKAGE_MODE=='r3') and value['first_load_epoch']==1792692329.837715
if PACKAGE_MODE=='r3':
 original_campaign=campaign()
 try:assert sum(r['kind']=='private_exposure_intent' for r in original_campaign.log.rows())==1
 finally:original_campaign.log.close()
 assert value['charged_gpu_seconds']==s['run_package']['timing_migration']['legacy_elapsed_debit_seconds']
print(json.dumps({'full_public_authority_checked':True,'actual_owner_worker_cli_startup':True,
 'actual_fork_qualified_before_loader':True,'actual_ready_frame':True,'natural_abort_exit':True,
 'private_exposures':0,'first_load_epoch_preserved':True}))
'''
    script=script.replace('REPO',repr(str(ROOT))).replace('PACKAGE_MODE',repr(package_mode))
    compile(script,'generated-approved-worker-startup-'+package_mode,'exec')
    if sys.platform!='linux' or not hasattr(os,'pidfd_open'):
        pytest.skip('generated startup syntax verified; actual fork/pidfd requires Linux')
    (tmp_path/'tools').mkdir()
    entry=tmp_path/'tools/run_c5_formal_reuse_worker.py'
    launcher=tmp_path/'fixture.py';launcher.write_text(script)
    entry.write_text('import runpy,sys\nsys.argv.insert(1,"worker")\nrunpy.run_path('+repr(str(launcher))+',run_name="__main__")\n')
    result=subprocess.run([sys.executable,'-I','-B',str(launcher),'owner'],cwd=tmp_path,
                          capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stderr
    v=json.loads(result.stdout.splitlines()[-1])
    assert v['actual_owner_worker_cli_startup'] and v['actual_ready_frame'] and v['private_exposures']==0
