"""Actual Linux CPU fork/pidfd barrier and one-stop tests. No CUDA imports.

The isolated fixture rebinds fixed interpreter/root constants to its own public
CPU script. Production entry never passes these fixture hooks or toy actors.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(sys.platform!='linux' or not hasattr(os,'pidfd_open'),reason='actual Linux pidfd CPU control')

def run_fixture(tmp_path,mode):
    tools=tmp_path/'tools';tools.mkdir();entry=tools/'run_c5_formal_reuse_worker.py'
    script='''import sys,json,os,time
from pathlib import Path
sys.path.insert(0,REPO)
from training.c5_reuse_evidence import sha,canonical
from training.c5_recovery_storage import EvidenceLog
from training.c5_formal_reuse_admission import FormalCampaign,campaign_scope
from training.c5_recovery_confirmation import snapshot
from training.c5_formal_reuse_supervisor import supervise,FormalWatchdog,progress,independent_stop
import training.c5_formal_reuse_supervisor as cpu_supervisor
# CPU fixture supplies its own durable role file; production has no fixture hook.
cpu_supervisor.claim_gpu_role=lambda permit,freeze,attempt: None
from training.c5_reuse_process_identity import LinuxIdentity
from plugin.rhino_listener import c5_formal_reuse_scope as scoped
from plugin.rhino_listener.c5_followup_profile import GPU_FLAGS
from training.c5_recovery_policy import POLICY
scoped.REMOTE_SOURCE=Path.cwd();scoped.REMOTE_ENV=Path(sys.executable).resolve().parent.parent
parent=LinuxIdentity()(os.getpid());now=time.time()
boundary={'owner_confirmed':True,'provider_expiry_epoch':now+100900,'generation_cutoff_epoch':now+100000,
 'export_reserve_seconds':900,'formal_max_seconds':64800,'historical_cumulative_upper_bound_seconds':None,
 'original_16_hour_compliance_claimed':False,'old_budget_recredited':False,'unused_development_transferred_to_formal':False,
 'development_first_load_epoch':1791916117.781239,'development_attempts_consumed':3,
 'development_campaign_head_sha256':'ebb572fbbe53ea2ec5c5a191f56ea1ee7767eef7525eca69d4a8a56a90f1975a',
 'development_seconds_max':86400,'research_cumulative_max_seconds':151200,
 'development_elapsed_to_release_seconds':66773.24127721786}
spec=json.loads((Path(REPO)/'eval/c5/formal-reuse-spec-20261022-r1.json').read_bytes())
spec['model_generation_cutoff_epoch']=boundary['generation_cutoff_epoch']

freeze={'history_sha256':'3'*64,'resource_boundary':boundary,
 'field_plan':{'gpu_process':{'uid':os.getuid(),'boot_id':parent['boot_id']}}}
scope=campaign_scope(spec,freeze);log=EvidenceLog(Path.cwd()/'cpu-ledger',scope,lambda:None,create=True)
c=FormalCampaign(scope,log);snap=snapshot(scope,'a'*64,'b'*64)
c.confirm(snap,{'actor':'repository_owner',**snap,'before_model_loading':True,'public_attempts_authorized':0,
 'human_origin_cryptographically_proven':False});c.start()
permit={'scope':scope,'rows':log.rows(),'attempt':1,'first_load_epoch':c.observation()['first_load_epoch']};log.close()
# The same original stdin stream carries exactly one pre-load permit.
import io
sys.stdin=io.TextIOWrapper(io.BytesIO(canonical(permit)+b'\\n'))
state=Path.cwd()/'cpu-state'
def child(fd):
 assert (state/'qualification.json').is_file() and (state/'qualified-stop/manifest.json').is_file()
 q=json.loads((state/'qualification.json').read_bytes())
 assert q['model_loading_started'] is False and q['target']==LinuxIdentity()(os.getpid())
 (state/'cpu-child-after-qualified.json').write_text(json.dumps({'pid':os.getpid(),'no_model':True}))
 progress(fd,b'L');progress(fd,b'B');progress(fd,b'R');progress(fd,b'S')
 if MODE=='broken_stderr':
  read_fd,write_fd=os.pipe();os.close(read_fd);os.dup2(write_fd,2);os.close(write_fd)
  raise ValueError('cpu_fixture_child_failure_with_broken_stderr')
 if MODE=='hang':time.sleep(30)
 progress(fd,b'E');progress(fd,b'D')
def finite_watchdog(start,cap,*,limits):
 if MODE=='constructor_failure':raise ValueError('cpu_fixture_constructor_failure_before_gate')
 if MODE=='hang':return FormalWatchdog(start,5,limits={**limits,'model_seconds':1},clock=time.monotonic)
 return FormalWatchdog(start,cap,limits=limits)
error=None
try:supervise(state,spec,freeze,1,lambda:None,child,watchdog_type=finite_watchdog)
except BaseException as e:error=type(e).__name__
final=json.loads((state/'supervisor-final.json').read_bytes())
before=sorted(p.name for p in (state/'qualified-stop').glob('event-*.json'))
again=independent_stop(state,lambda:None)
after=sorted(p.name for p in (state/'qualified-stop').glob('event-*.json'))
assert before==after and len(after)==2 and 'torch' not in sys.modules
print(json.dumps({'error':error,'final':final,'again':again,'model_imported':False,'child_after_qualified':(state/'cpu-child-after-qualified.json').is_file()}))
'''
    script=script.replace('REPO',repr(str(ROOT))).replace('MODE',repr(mode))
    entry.write_text(script)
    executable=str(Path(sys.executable).resolve())
    from plugin.rhino_listener.c5_followup_profile import GPU_FLAGS
    result=subprocess.run([executable,*GPU_FLAGS,str(entry),'serve','--attempt','1'],cwd=tmp_path,
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)

def test_actual_cpu_child_cannot_run_before_qualification_and_natural_exit_uses_zero_signals(tmp_path):
    result=run_fixture(tmp_path,'normal')
    assert result['error'] is None and result['final']['child_wait_status']==0
    assert result['final']['child_exit_reaped'] is True and result['final']['stop_result']['signal_attempts']==0
    assert result['again']['status']=='already_exited' and result['child_after_qualified'] is True

def test_actual_hung_cpu_child_gets_one_pidfd_signal_and_second_actor_cannot_resignal(tmp_path):
    result=run_fixture(tmp_path,'hang')
    assert result['error']=='ValueError' and result['final']['child_exit_reaped'] is True
    assert result['final']['stop_result']['signal_attempts']==1
    assert result['again']['signal_attempts']==1 and result['again']['retry_signal_allowed'] is False

def test_watchdog_constructor_failure_never_releases_child_and_still_records_one_shared_stop(tmp_path):
    result=run_fixture(tmp_path,'constructor_failure')
    assert result['error']=='ValueError' and result['child_after_qualified'] is False
    assert result['final']['child_exit_reaped'] is True and result['final']['cleanup_errors']==[]
    assert result['final']['stop_result']['signal_attempts']==result['again']['signal_attempts']==1
    assert result['again']['retry_signal_allowed'] is False


def test_broken_child_stderr_cannot_publish_parent_final_or_skip_reap(tmp_path):
    result=run_fixture(tmp_path,'broken_stderr')
    assert result['error']=='ValueError' and result['child_after_qualified'] is True
    final=result['final']
    assert final['child_exit_reaped'] is True and final['child_wait_status']==256
    assert final['primary_error_type'] is None and final['cleanup_errors']==[]
    assert final['stop_result']['status']=='already_exited'
    assert final['stop_result']['signal_attempts']==result['again']['signal_attempts']==0
