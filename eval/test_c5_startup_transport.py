"""CPU subprocess timing/negative controls; zero model, Rhino or holdout."""
import copy
import json
import subprocess
import sys

import pytest

from plugin.rhino_listener.c5_research_native import digest,NativeError
from training.c5_startup_transport import startup_receipt,validate_startup_receipt,StartupReadyPipe
from training.c5_startup_audit import audit_startup_ready
from eval.test_c5_model_transport import sent


def records():
    f={'source_inventory_sha256':'a'*64,'environment_sha256':'b'*64,
        'model_identities':{'base':'c'*64,'lora':'d'*64}}
    return f,startup_receipt('DEV',digest(f),f['source_inventory_sha256'],f['environment_sha256'],f['model_identities'])


def child(ready,delay=0,after=0,extra=False):
    script='''import sys,json,time,hashlib
time.sleep(float(sys.argv[2]))
print(json.dumps(json.loads(sys.argv[1])),flush=True)
if sys.argv[4]=='True':print('{}',flush=True)
line=sys.stdin.buffer.readline()
if line:
    x=json.loads(line);time.sleep(float(sys.argv[3]))
    sha=hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    print(json.dumps({'request_sha256':sha}),flush=True)
'''
    return subprocess.Popen([sys.executable,'-u','-c',script,json.dumps(ready),str(delay),str(after),str(extra)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def close(p):
    p.stdin.close()
    try:p.wait(timeout=3)
    except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=3)
    p.stdout.close();p.stderr.close()


def test_startup_can_exceed_request_window_without_spending_task_or_replaying():
    _,r=records();p=child(r,delay=.6,after=.01)
    try:
        wire=StartupReadyPipe(p,r,timeout=.3,startup_timeout=2)
        assert wire.wait_ready()==r
        assert wire.exchange(sent())=={'request_sha256':digest(sent())}
    finally:close(p)


@pytest.mark.parametrize('change',['study','freeze','source','environment','base','count','stage','holdout','loaded','boolean_count','extra','status'])
def test_independent_audit_and_wire_reject_wrong_readiness(change):
    f,r=records();bad=copy.deepcopy(r)
    if change in {'study','freeze','source','environment','status'}:
        key={'study':'study_id','freeze':'runtime_freeze_sha256','source':'source_inventory_sha256',
            'environment':'environment_sha256','status':'status'}[change];bad[key]='wrong'
    elif change=='base':bad['model_identities']['base']='f'*64
    elif change=='count':bad['generation_requests']=1
    elif change=='stage':bad['generation_stages']=1
    elif change=='holdout':bad['holdout_rows_read']=1
    elif change=='loaded':bad['model_loaded']=False
    elif change=='boolean_count':bad['generation_requests']=False
    else:bad['unfrozen_field']=True
    with pytest.raises(NativeError):validate_startup_receipt(bad,r)
    with pytest.raises(NativeError):audit_startup_ready(bad,bad,f,'DEV')


def test_startup_unknown_is_sticky_no_send_or_reconnect():
    _,r=records();p=child(r,delay=.4)
    try:
        wire=StartupReadyPipe(p,r,timeout=.2,startup_timeout=.03)
        with pytest.raises(NativeError):wire.wait_ready()
        assert wire.blocked and not wire.ready
        with pytest.raises(NativeError):wire.wait_ready()
        with pytest.raises(NativeError):wire.exchange(sent())
    finally:close(p)


def test_premature_task_is_not_written_and_blocks():
    _,r=records();p=child(r)
    try:
        wire=StartupReadyPipe(p,r)
        with pytest.raises(NativeError):wire.exchange(sent())
        assert wire.blocked and not wire.ready
        with pytest.raises(NativeError):wire.wait_ready()
    finally:close(p)


def test_wrong_initial_frame_and_duplicate_ready_fail_closed():
    _,r=records();p=child({**r,'study_id':'WRONG'})
    try:
        wire=StartupReadyPipe(p,r,startup_timeout=2)
        with pytest.raises(NativeError):wire.wait_ready()
        assert wire.blocked
    finally:close(p)
    p=child(r)
    try:
        wire=StartupReadyPipe(p,r);wire.wait_ready()
        with pytest.raises(NativeError):wire.wait_ready()
        assert wire.blocked
        with pytest.raises(NativeError):wire.exchange(sent())
    finally:close(p)


def test_request_timeout_after_ready_remains_unknown_no_replay():
    _,r=records();p=child(r,after=.2)
    try:
        wire=StartupReadyPipe(p,r,timeout=.03,startup_timeout=2);wire.wait_ready()
        with pytest.raises(NativeError):wire.exchange(sent())
        assert wire.blocked
        with pytest.raises(NativeError):wire.exchange(sent())
    finally:close(p)


def test_independent_zero_count_reconstruction_passes():
    f,r=records();assert audit_startup_ready(r,r,f,'DEV')['startup_record_identity_and_zero_counts_verified']


def test_unsolicited_extra_frame_cannot_be_accepted_as_task_response():
    _,r=records();p=child(r,extra=True)
    try:
        wire=StartupReadyPipe(p,r,startup_timeout=2)
        with pytest.raises(NativeError):
            wire.wait_ready();wire.exchange(sent())
        assert wire.blocked
        with pytest.raises(NativeError):wire.exchange(sent())
    finally:close(p)


def test_initial_eof_never_sends_task():
    _,r=records();p=subprocess.Popen([sys.executable,'-c','pass'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        wire=StartupReadyPipe(p,r,startup_timeout=2)
        with pytest.raises(NativeError):wire.wait_ready()
        assert wire.blocked and not wire.ready
    finally:close(p)
