"""Real CPU pipe and fault injection; no SSH/model/Rhino call or real grant."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from eval.test_c5_reuse_field_preparation import binding, peer, Tokenizer, records
from eval.test_c5_reuse_field_negative import rechain
from training.c5_model_transport import request
from training.c5_reuse_evidence import canonical, sha
from training.c5_reuse_field_scope import STUDY
from training.c5_reuse_field_wire import frame,envelope,validate_peer_result
from training.c5_reuse_field_transport import FieldModelChannel,FieldPipe
from training.c5_reuse_field_transport_audit import audit_controller,audit_join
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_field_journal import read_journal


class Endpoint:
    def __init__(self,raw,kind='good'):
        self.raw,self.kind,self.writes,self.received=raw,kind,[],False
    def write(self,remaining,deadline):
        self.writes.append(remaining)
        if self.kind=='write_unknown': raise BrokenPipeError('CPU broken pipe')
        return min(3,len(remaining)) if self.kind=='partial' else len(remaining)
    def read(self,deadline):
        if self.kind=='eof' or self.received: return b''
        self.received=True
        if self.kind=='oversize': return b'x'*32769
        if self.kind=='duplicate': return self.raw+self.raw
        if self.kind=='partial_eof': return self.raw[:9]
        return self.raw


def setup(tmp_path,kind='good'):
    p,gpu_registry,sent,calls=peer(tmp_path)
    returned=p.infer(sent)
    raw=frame(returned)
    if kind=='scope':
        returned=copy.deepcopy(returned); returned['request_sha256']='0'*64; raw=frame(returned)
    elif kind=='parser':
        returned=copy.deepcopy(returned); returned['observation']['arguments']['width']=99; raw=frame(returned)
    mac=binding(tmp_path,endpoint='mac')
    Path(mac['paths']['state_root']).mkdir(mode=0o700)
    mac_registry=AdmissionRegistry(mac,create=True)
    endpoint=Endpoint(raw,kind)
    channel=FieldModelChannel(mac,mac_registry,endpoint,lambda:None,lambda:None,p.plans)
    return channel,p,sent,endpoint,mac_registry,gpu_registry


@pytest.mark.parametrize('kind',['good','partial'])
def test_two_endpoint_raw_join_and_partial_writes_never_resend_prefix(tmp_path,kind):
    channel,p,sent,endpoint,mac_registry,gpu_registry=setup(tmp_path,kind)
    try:
        returned=channel.exchange(sent)
        assert returned==p.journal.records[-1]['payload']['result']
        if kind=='partial':
            written=b''.join(part[:min(3,len(part))] for part in endpoint.writes)
            assert written==frame(sent)
        joined=audit_join(channel.journal.records,p.journal.records,channel.binding,p.binding,
            channel.journal.head,p.journal.head,p.plans,Tokenizer())
        assert joined['complete_raw_join'] and joined['generation']['recorded_generation_returns']==2
        assert joined['actual_physical_generation_total_independently_proven'] is None
        assert not joined['execution_ready'] and not joined['external_witness_origin_verified']
        with pytest.raises(ValueError): channel.exchange(sent)
    finally: mac_registry.close(); gpu_registry.close()


@pytest.mark.parametrize('kind',['write_unknown','eof','oversize','duplicate','partial_eof','scope','parser'])
def test_transport_unknown_preserves_received_bytes_and_permanent_admission(tmp_path,kind):
    channel,p,sent,endpoint,mac_registry,gpu_registry=setup(tmp_path,kind)
    try:
        with pytest.raises((ValueError,OSError)): channel.exchange(sent)
        evidence=read_journal(channel.journal.root,channel.binding,'controller',channel.journal.head)
        if kind!='write_unknown':
            assert any(r['kind']=='wire_received' for r in evidence)
        assert evidence[-1]['kind']=='wire_retired'
        old=len(endpoint.writes)
        with pytest.raises(ValueError,match='no_retry'): channel.exchange(sent)
        assert len(endpoint.writes)==old
    finally: mac_registry.close(); gpu_registry.close()
    with AdmissionRegistry(channel.binding) as registry:
        with pytest.raises(FileExistsError): registry.claim('controller')


@pytest.mark.parametrize('kind',['task','role','durability','deadline'])
def test_bad_scope_or_intent_failure_has_no_outbound_bytes(tmp_path,kind):
    channel,p,sent,endpoint,mac_registry,gpu_registry=setup(tmp_path)
    try:
        if kind=='task': sent['request']['task']='未批准的任务'
        elif kind=='role': sent['request']['route']='lora'
        elif kind=='durability':
            original=channel.journal.append
            def append(event,payload):
                if event=='wire_intent': raise OSError('CPU disk failure')
                original(event,payload)
            channel.journal.append=append
        else:
            clock=iter((1,181)); channel.clock=lambda:next(clock)
        with pytest.raises((ValueError,OSError)): channel.exchange(sent)
        assert endpoint.writes==[]
    finally: mac_registry.close(); gpu_registry.close()


@pytest.mark.parametrize('kind',['received','ack','sent','intent','missing','truncate'])
def test_independent_controller_audit_rejects_rehashed_wire_tampering(tmp_path,kind):
    channel,p,sent,endpoint,mac_registry,gpu_registry=setup(tmp_path)
    try:
        channel.exchange(sent)
        rows=copy.deepcopy(channel.journal.records)
        received=next(r for r in rows if r['kind']=='wire_received')
        if kind=='received': received['payload']['raw_hex']=b'false'.hex(); received['payload']['observed_bytes']=5
        elif kind=='ack': rows[-1]['payload']['frame_sha256']='0'*64
        elif kind=='sent': next(r for r in rows if r['kind']=='wire_sent')['payload']['bytes']=True
        elif kind=='intent': rows.insert(2,copy.deepcopy(rows[1]))
        elif kind=='missing': rows.remove(received)
        else: received['payload']['truncated']=True
        for i,row in enumerate(rows): row['seq']=i
        head=rechain(rows)
        with pytest.raises(ValueError): audit_controller(rows,channel.binding,head,p.plans)
    finally: mac_registry.close(); gpu_registry.close()


def test_real_cpu_subprocess_two_endpoint_field_pipe(tmp_path):
    gpu=binding(tmp_path); mac=binding(tmp_path,endpoint='mac'); plans=records(tmp_path)[3]
    Path(gpu['paths']['state_root']).mkdir(mode=0o700); Path(mac['paths']['state_root']).mkdir(mode=0o700)
    code='''import contextlib,json,sys
from pathlib import Path
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_generation import GenerationPeer
from training.c5_reuse_field_wire import frame
from training.c5_reuse_evidence import raw_sha
from eval.test_c5_reuse_field_preparation import Tokenizer
x=json.loads(sys.argv[1])
def generate(prompt,stage):
    raw='{"tool":"create_box"}' if stage=='selector' else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'
    return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':raw_sha(prompt.encode()),'output_sha256':raw_sha(raw.encode())}
with AdmissionRegistry(x['binding'],create=True) as registry:
    peer=GenerationPeer(x['binding'],registry,x['plans'],Tokenizer(),generate,lambda route:contextlib.nullcontext(),lambda:None,lambda:None)
    sent=json.loads(sys.stdin.buffer.readline())
    sys.stdout.buffer.write(frame(peer.infer(sent))); sys.stdout.buffer.flush()
'''
    process=subprocess.Popen([sys.executable,'-B','-c',code,json.dumps({'binding':gpu,'plans':plans})],
                             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        with AdmissionRegistry(mac,create=True) as registry:
            pipe=FieldPipe(process.stdin.fileno(),process.stdout.fileno())
            channel=FieldModelChannel(mac,registry,pipe,lambda:None,lambda:None,plans)
            sent=envelope(mac,request(STUDY,'slot-base','base',0,plans['slot-base']['steps'][0],
                {'unit':'Millimeters','objects':[],'groups':{}},{'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64},
                mac['runtime_sha256'],'cpu-pipe-request'))
            result=channel.exchange(sent)
            assert result['observation']['status']=='schema_valid_not_authorized'
            process.wait(timeout=10)
            assert process.returncode==0,process.stderr.read().decode()
    finally:
        if process.poll() is None: process.kill(); process.wait(timeout=10)
        for stream in (process.stdin,process.stdout,process.stderr): stream.close()


@pytest.mark.parametrize('kind,code',(('eof','field_transport_eof'),('oversize','field_oversize_chunk')))
def test_eof_and_oversize_have_distinct_raw_evidence_codes(tmp_path,kind,code):
    channel,p,sent,endpoint,mac_registry,gpu_registry=setup(tmp_path,kind)
    try:
        with pytest.raises(ValueError,match=code):channel.exchange(sent)
        received=[r['payload'] for r in channel.journal.records if r['kind']=='wire_received']
        assert len(received)==1 and received[0]['observed_bytes']==(0 if kind=='eof' else 32769)
        assert len(endpoint.writes)==1
    finally:mac_registry.close();gpu_registry.close()
