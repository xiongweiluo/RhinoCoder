"""Real CPU framed subprocess and clock negatives; zero live/private calls."""
import copy
import json
import subprocess
import sys

import pytest

from eval.test_c5_startup_transport import close
from eval.test_c5_model_transport import sent
from eval.test_c5_hostassurance_lifecycle_d import Clock
from training.c5_formal20_transport_v2 import FormalLifecyclePipe,NativeChannelV2
from training.c5_startup_transport import startup_receipt,StartupReadyPipe
from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_research_channel import publish_json
from plugin.rhino_listener.c5_lifecycle_deadlines import PhaseClock


def ready():return startup_receipt('DEV','c'*64,'a'*64,'b'*64,{'base':'d'*64,'lora':'e'*64})


def test_real_cpu_bootstrap_and_abort_keep_zero_readiness_and_complete_timing(tmp_path):
    r=ready()
    script='''import sys,json,hashlib
r=json.loads(sys.argv[1]);print(json.dumps(r),flush=True)
for line in sys.stdin:
 x=json.loads(line);sha=hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 if x['kind']=='formal_bootstrap':v={'status':'formal_worker_ready','request_sha256':sha,'runtime_freeze_sha256':r['runtime_freeze_sha256'],'model_identities':r['model_identities'],'startup_receipt':r}
 else:v={'status':'formal_prebootstrap_aborted_zero_generation','request_sha256':sha,'runtime_freeze_sha256':r['runtime_freeze_sha256'],'generation_requests':0}
 print(json.dumps(v),flush=True)
'''
    p=subprocess.Popen([sys.executable,'-u','-c',script,json.dumps(r)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        wire=FormalLifecyclePipe(p,r,model_identities=r['model_identities'],journal_state=tmp_path)
        assert wire.wait_ready()==r and wire.last_phase['role']=='startup'
        value=wire.exchange({'kind':'formal_bootstrap','runtime_freeze_sha256':'c'*64})
        assert value['startup_receipt']['holdout_rows_read']==0
        assert wire.last_phase['role']=='formal-control' and wire.last_phase['sequence']==1
        assert (tmp_path/'control-0001-time.json').exists()
    finally:close(p)


def test_premature_model_request_sticks_and_never_sends(monkeypatch):
    r=ready();wire=FormalLifecyclePipe(None,r,model_identities=r['model_identities'])
    with pytest.raises(NativeError):wire.exchange(sent())
    assert wire.blocked
    with pytest.raises(NativeError):wire.wait_ready()


def test_sensitive_or_invalid_model_request_rejected_before_wire(monkeypatch):
    r=ready();wire=FormalLifecyclePipe(None,r,model_identities=r['model_identities']);wire.ready=True
    called=[]
    monkeypatch.setattr(StartupReadyPipe,'exchange',lambda *a:called.append(1))
    value=sent();value['task']='密码 test-not-a-real-secret'
    with pytest.raises(NativeError):wire.exchange(value)
    assert not called and wire.blocked


@pytest.mark.parametrize('phase',['startup','model','bootstrap'])
def test_full_validation_deadline_overrun_is_sticky(monkeypatch,phase):
    import training.c5_formal20_transport_v2 as module
    clock=Clock();r=ready();wire=FormalLifecyclePipe(None,r,model_identities=r['model_identities'],clock=clock)
    called=[]
    if phase=='startup':
        def receive(self):called.append(1);clock.advance(181);self.ready=True;return r
        monkeypatch.setattr(StartupReadyPipe,'wait_ready',receive)
        with pytest.raises(ValueError):wire.wait_ready()
    else:
        wire.ready=True
        def receive(self,value):
            called.append(1)
            if phase=='model':return {'raw':'synthetic'}
            return {'status':'formal_worker_ready','request_sha256':digest(value),'runtime_freeze_sha256':'c'*64,
                'model_identities':r['model_identities'],'startup_receipt':r}
        monkeypatch.setattr(StartupReadyPipe,'exchange',receive)
        if phase=='model':monkeypatch.setattr(module,'validate_response',lambda *a:clock.advance(181))
        else:monkeypatch.setattr(module,'validate_startup_receipt',lambda *a:clock.advance(181))
        with pytest.raises(ValueError):wire.exchange(sent() if phase=='model' else {'kind':'formal_bootstrap'})
    assert wire.blocked and called==[1]
    with pytest.raises(Exception):wire.exchange(sent())
    assert called==[1]


def test_native_reply_without_complete_service_proof_is_unknown_no_resend(tmp_path):
    clock=Clock();req={'kind':'control','synthetic':True}
    def pump():
        if not (tmp_path/'response-0001.json').exists():publish_json(tmp_path,'response-0001.json',{'status':'captured'})
    wire=NativeChannelV2(tmp_path,b'x'*32,'a'*64,clock=clock,pump=pump,sleep=lambda _:clock.advance(121))
    with pytest.raises(ValueError):wire.exchange(req)
    assert wire.unresolved and wire.seq==1
    with pytest.raises(NativeError):wire.exchange(req)
    assert len(list(tmp_path.glob('request-*.json')))==1
