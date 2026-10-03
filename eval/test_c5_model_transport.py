"""Synthetic wire/session/process controls; no SSH, models or real fixtures."""
import contextlib
import copy
import hashlib
import json
import os
import subprocess
import sys

import pytest

from plugin.rhino_listener.c5_research_native import digest
from training.c5_model_transport import (request,strict_json,frame,validate_request,validate_response,
    OneShotModelSession,rebind_observation,FramedPipe)
from training.c5_modelbridge_runtime import Budget


class Tokenizer:
    def apply_chat_template(self,messages,*,tools=None,**kwargs):
        return json.dumps({'messages':messages,'tools':tools},ensure_ascii=False)
    def __call__(self,text,**kwargs): return {'input_ids':[0]*100}


def binding(): return {'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64}
def scene(): return {'unit':'Millimeters','objects':[],'groups':{}}
def sent(): return request('DEV','write-base','base',0,'创建宽2深3高4毫米的盒体。',scene(),binding(),'c'*64,'request-1')


def session(tmp_path,*,generate=None,guard=lambda:None,steps=None):
    state = tmp_path/'state'
    state.mkdir(mode=0o700,exist_ok=True)
    calls = []
    def good(prompt,stage):
        calls.append(stage)
        raw = '{"tool":"create_box"}' if stage=='selector' else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'
        return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                'output_sha256':hashlib.sha256(raw.encode()).hexdigest()}
    s = OneShotModelSession('DEV','c'*64,{'write-base':{'route':'base','steps':steps or [sent()['task']]}},
            state,Tokenizer(),generate or good,lambda route:contextlib.nullcontext(),
            {'base':'d'*64,'lora':'e'*64},guard,lambda:100)
    return s,calls


def test_full_raw_response_and_local_rebinding(tmp_path):
    s,calls = session(tmp_path)
    wire = sent(); value = s.infer(wire)
    assert calls==['selector','invocation']
    assert value['observation']['scene_binding'] is None
    observed = rebind_observation(value,wire,'d'*64,binding())
    assert observed['scene_binding']==binding() and observed['name']=='create_box'
    assert observed['repair_count']==observed['dispatch_count']==0
    assert 'document_key' not in wire and 'revision' not in wire
    assert len(list(s.state.glob('*-raw.json')))==2


@pytest.mark.parametrize('mutation',['oracle','physical','route','boolean_step','sha','privacy','task_budget'])
def test_outbound_rejects_unapproved_or_private_payload(mutation):
    wire = sent()
    if mutation=='oracle': wire['expected_arguments']={}
    if mutation=='physical': wire['scene']['objects']=[{'alias':'11111111-2222-3333-4444-555555555555'}]
    if mutation=='route': wire['route']='cloud'
    if mutation=='boolean_step': wire['step_index']=False
    if mutation=='sha': wire['binding_sha256']='no'
    if mutation=='privacy': wire['task']='我的身份证号码是110101199001011234，请创建盒体'
    if mutation=='task_budget': wire['task']='A'*4097
    with pytest.raises(Exception): validate_request(wire)


@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":Infinity}',b'\xff'])
def test_strict_frames(raw):
    with pytest.raises(Exception): strict_json(raw)
    with pytest.raises(Exception): frame({'raw':'x'*(1024*1024)})


def test_permanent_claim_survives_reconstructor_and_new_request_id(tmp_path):
    first,calls = session(tmp_path); first.infer(sent())
    second,later = session(tmp_path)
    wire = sent(); wire['request_id']='new-request'
    with pytest.raises(Exception): second.infer(wire)
    assert later==[] and calls==['selector','invocation']


def test_step_cannot_skip_prior_attempt(tmp_path):
    s,calls = session(tmp_path,steps=[sent()['task'],sent()['task']])
    wire=sent(); wire['step_index']=1
    with pytest.raises(Exception): s.infer(wire)
    assert calls==[]


@pytest.mark.parametrize('mutation',['model','freeze','raw','tokens','seconds','repair','binding','prompt'])
def test_response_tampering_rejected(tmp_path,mutation):
    s,_ = session(tmp_path); wire=sent(); value=s.infer(wire)
    if mutation=='model': value['model_identity_sha256']='f'*64
    if mutation=='freeze': value['runtime_freeze_sha256']='f'*64
    if mutation=='raw': value['observation']['calls'][0]['raw']='{"tool":null}'
    if mutation=='tokens': value['generation_receipts'][0]['tokens']=129
    if mutation=='seconds': value['generation_receipts'][0]['seconds']=float('inf')
    if mutation=='repair': value['observation']['repair_count']=False
    if mutation=='binding': value['request_sha256']='f'*64
    if mutation=='prompt': value['generation_receipts'][0]['prompt_sha256']='f'*64
    with pytest.raises(Exception): validate_response(value,wire,'d'*64)


def test_scene_drift_never_rebinds_or_signs(tmp_path):
    s,_=session(tmp_path); wire=sent(); value=s.infer(wire)
    changed=binding(); changed['revision']=1
    with pytest.raises(Exception): rebind_observation(value,wire,'d'*64,changed)


def test_generation_error_is_not_retried_and_blocks_session(tmp_path):
    calls=[]
    def broken(*args): calls.append(1); raise TimeoutError('synthetic')
    s,_=session(tmp_path,generate=broken)
    value=s.infer(sent())
    assert value['observation']['status']=='operational_failure_no_retry' and calls==[1]
    assert s.blocked and len(list(s.state.glob('*-failure.json')))==1
    with pytest.raises(Exception): s.infer(sent())
    assert calls==[1]


def test_post_generation_guard_failure_retains_raw(tmp_path):
    count=[]
    def guard():
        count.append(1)
        if len(count)>=3: raise RuntimeError('source drift')
    s,calls=session(tmp_path,guard=guard)
    value=s.infer(sent())
    assert value['observation']['status']=='operational_failure_no_retry' and calls==['selector']
    assert s.blocked and len(list(s.state.glob('*-raw.json')))==1


@pytest.mark.parametrize('body',['import sys; sys.stdin.buffer.readline()',
    'import sys; sys.stdout.buffer.write(b"bad JSON\\n");sys.stdout.flush()',
    'import sys; sys.stdout.buffer.write(b"{}\\n{}\\n");sys.stdout.flush()'])
def test_pipe_eof_bad_and_unsolicited_responses_block(body):
    process=subprocess.Popen([sys.executable,'-c',body],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    pipe=FramedPipe(process,timeout=1)
    try:
        with pytest.raises(Exception): pipe.exchange(sent())
        assert pipe.blocked
        with pytest.raises(Exception): pipe.exchange(sent())
    finally:
        process.stdin.close(); process.stdout.close(); process.wait(timeout=2)


def boundary():
    return {'owner_confirmed':True,'provider_expiry_epoch':10000,'hard_stop_epoch':9000,'export_reserve_seconds':900,
            'development_max_seconds':3600,'prior_cumulative_seconds':100,'original_cumulative_max_seconds':57600}


def test_budget_includes_idle_and_utc_jumps(tmp_path):
    now=[1000.0]; mono=[0.0]
    b=Budget(boundary(),wall=lambda:now[0],mono=lambda:mono[0])
    assert b.cap==3600
    mono[0]=3600
    with pytest.raises(Exception): b.check()
    mono[0]=1; now[0]=8100
    with pytest.raises(Exception): b.check()
    state=tmp_path/'settled';state.mkdir(mode=0o700)
    assert b.settle(state,'stopped')['elapsed_seconds_including_load_and_idle']==1
    with pytest.raises(Exception): b.settle(state,'stopped')


@pytest.mark.parametrize('mutation',['owner','past','reserve','budget','cumulative','expiry','nan'])
def test_old_or_invalid_resource_boundary_never_admits(mutation):
    x=boundary()
    if mutation=='owner': x['owner_confirmed']=False
    if mutation=='past': x['hard_stop_epoch']=1000
    if mutation=='reserve': x['export_reserve_seconds']=899
    if mutation=='budget': x['development_max_seconds']=3601
    if mutation=='cumulative': x['prior_cumulative_seconds']=57600
    if mutation=='expiry': x['provider_expiry_epoch']=8000
    if mutation=='nan': x['hard_stop_epoch']=float('nan')
    with pytest.raises(Exception): Budget(x,wall=lambda:1000,mono=lambda:0)
