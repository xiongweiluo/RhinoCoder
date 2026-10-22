"""Real isolated CPU subprocess framing and synthetic independent HMAC audit."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import pytest
from plugin.rhino_listener.c5_research_native import digest,NativeError
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_research_gate import signature
from training.c5_followup_diagnostics import CapturedStreams
from training.c5_startup_transport import startup_receipt
from training.c5_formal_reuse_wire_io import StartupReadyPipe
from training.c5_formal_reuse_evidence_audit import audit_signatures
from plugin.rhino_listener.c5_formal_reuse_scope import STUDY_ID

ERRORS=(ValueError,NativeError)

def spawn(root,mode,*,stderr_cap=262144):
    root.chmod(0o700)
    ready=startup_receipt(STUDY_ID,'1'*64,'2'*64,'3'*64,{'base':'4'*64,'lora':'5'*64})
    code='import json,sys\nready='+repr(ready)+'\n'
    if mode=='wrong_ready':code+="ready['generation_requests']=1\n"
    if mode=='stderr_overflow':code+="sys.stderr.write('x'*16384);sys.stderr.flush()\n"
    code+="sys.stdout.write(json.dumps(ready)+'\\n');sys.stdout.flush()\n"
    code+="request=json.loads(sys.stdin.readline())\n"
    if mode=='half':code+="sys.stdout.write('{\\\"torn\\\":');sys.stdout.flush()\n"
    elif mode=='duplicate':code+="sys.stdout.write('{}\\n{}\\n');sys.stdout.flush()\n"
    elif mode=='eof':code+="pass\n"
    else:code+="sys.stdout.write(json.dumps({'received':request})+'\\n');sys.stdout.flush()\n"
    capture=CapturedStreams(root,'serve',stderr_cap=stderr_cap)
    process=subprocess.Popen([sys.executable,'-I','-B','-c',code],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)
    capture.start(process,protocol=True)
    pipe=StartupReadyPipe(process,ready,capture=capture,timeout=2,startup_timeout=2)
    return process,capture,pipe

def finish(process,capture):
    if process.stdin and not process.stdin.closed:process.stdin.close()
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=3)
    value=capture.finish()
    process.stdout.close();process.stderr.close()
    return value

def test_real_subprocess_complete_frame_has_original_eof_and_raw_hashes(tmp_path):
    process,capture,pipe=spawn(tmp_path,'normal')
    try:
        ready=pipe.wait_ready();assert ready['generation_requests']==0
        assert pipe.exchange({'cpu_only':True})=={'received':{'cpu_only':True}}
    finally:value=finish(process,capture)
    assert value['complete_raw_capture'] is True and not value['protocol_delivery_overflow']
    assert value['unconsumed_protocol_tail_bytes']==0
    for n in ('stdout','stderr'):
        r=value[n];assert hashlib.sha256((tmp_path/r['name']).read_bytes()).hexdigest()==r['observed_bytes_sha256']

@pytest.mark.parametrize('mode',['half','eof','duplicate'])
def test_real_torn_or_duplicate_reply_is_sticky_and_never_resent(tmp_path,mode):
    process,capture,pipe=spawn(tmp_path,mode)
    try:
        pipe.wait_ready()
        with pytest.raises(ERRORS):pipe.exchange({'cpu_only':True})
        assert pipe.blocked
        with pytest.raises(ERRORS):pipe.exchange({'cpu_only':True})
    finally:finish(process,capture)

def test_wrong_actual_ready_refuses_before_any_request(tmp_path):
    process,capture,pipe=spawn(tmp_path,'wrong_ready')
    try:
        with pytest.raises(ERRORS):pipe.wait_ready()
        assert pipe.blocked
    finally:finish(process,capture)

def test_raw_stderr_overflow_is_incomplete_and_not_a_retry_permission(tmp_path):
    process,capture,pipe=spawn(tmp_path,'stderr_overflow',stderr_cap=128)
    try:
        try:pipe.wait_ready()
        except ERRORS:pass
        deadline=time.monotonic()+2
        while capture.stderr.observed<16384 and time.monotonic()<deadline:time.sleep(0.005)
        with pytest.raises(ERRORS):capture.check()
        with pytest.raises(ERRORS):pipe.exchange({'must_not_send_after_observed_overflow':True})
    finally:value=finish(process,capture)
    assert value['complete_raw_capture'] is False and value['stderr']['truncated'] is True
    assert value['retry_allowed'] is False

def test_request_before_ready_permanently_blocks_the_frame_session(tmp_path):
    process,capture,pipe=spawn(tmp_path,'normal')
    try:
        with pytest.raises(ERRORS):pipe.exchange({'cpu_only':True})
        assert pipe.blocked
        with pytest.raises(ERRORS):pipe.wait_ready()
    finally:finish(process,capture)

def signature_fixture(root):
    root.chmod(0o700);custody=root/'audit-key-custody';custody.mkdir(mode=0o700)
    freeze={'cpu_fixture':True};order=[];cases=[];secret=b'c'*32
    for n in range(1,21):
        family='synthetic-%02d'%n;cases.append({'family_id':family,'task_text':'public CPU task %d'%n})
        for route in ('base','lora'):
            label='F%02d-%s'%(n,route);order.append({'slot_id':label,'family_id':family,'route':route})
            d=root/label;d.mkdir(mode=0o700)
            publish_json(custody,label+'.json',{'key_hex':secret.hex(),'runtime_sha256':digest(freeze)})
            payload={'owner_freeze_sha256':digest(freeze),'request_id':label+'-cpu-control',
                'task_sha256':hashlib.sha256(cases[-1]['task_text'].encode()).hexdigest()}
            publish_json(d,'request-0001.json',{'kind':'control','envelope':{'payload':payload,'signature':signature(secret,payload)}})
    publish_json(custody,'hub.json',{'key_hex':secret.hex(),'runtime_sha256':digest(freeze)})
    p={'owner_freeze_sha256':digest(freeze),'request_id':'hub-cpu-control'}
    publish_json(root,'hub-request-0001.json',{'payload':p,'signature':signature(secret,p)})
    return freeze,order,cases

def test_independent_hmac_uses_retained_keys_after_dispatch_keys_are_removed(tmp_path):
    freeze,order,cases=signature_fixture(tmp_path)
    result=audit_signatures(tmp_path,freeze,order,cases)
    assert result['signed_requests_recomputed']==41 and result['private_audit_keys_retained']==41
    assert result['dispatch_keys_absent'] is True and result['memory_erasure_proven'] is False

@pytest.mark.parametrize('change',['body','signature','scope','key_missing','replayed_id','dispatch_key_remaining'])
def test_raw_signature_tampering_or_missing_key_never_becomes_verified(tmp_path,change):
    freeze,order,cases=signature_fixture(tmp_path);slot=tmp_path/'F01-base';p=slot/'request-0001.json'
    value=read_json(slot,p.name)
    if change=='key_missing':(tmp_path/'audit-key-custody/F01-base.json').unlink()
    elif change=='dispatch_key_remaining':publish_json(slot,'handoff.key',{'key_hex':(b'c'*32).hex()})
    elif change=='scope':
        q=tmp_path/'audit-key-custody/F01-base.json';v=json.loads(q.read_bytes());v['runtime_sha256']='0'*64;q.write_text(json.dumps(v))
    else:
        envelope=value['envelope']
        if change=='body':envelope['payload']['task_sha256']='0'*64
        elif change=='signature':envelope['signature']='0'*64
        else:
            envelope['payload']['request_id']='hub-cpu-control'
            envelope['signature']=signature(b'c'*32,envelope['payload'])
        p.write_text(json.dumps(value))
    with pytest.raises(ERRORS):audit_signatures(tmp_path,freeze,order,cases)
