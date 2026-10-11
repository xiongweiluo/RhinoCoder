"""Independent mutations and actual OS faults against CPU-only field fixtures."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from eval.test_c5_reuse_field_preparation import binding, peer, sha_raw, Tokenizer
from training.c5_reuse_evidence import canonical, sha, ZERO
from training.c5_reuse_field_journal import read_journal
from training.c5_reuse_generation_audit import audit_generation
from training.c5_reuse_development_plan import public_plan, SOURCE
from training.c5_reuse_admission import AdmissionRegistry


def rechain(rows):
    previous = ZERO
    for row in rows:
        row['previous_sha256'] = previous
        row['record_sha256'] = sha({k:v for k,v in row.items() if k != 'record_sha256'})
        previous = row['record_sha256']
    return previous


@pytest.mark.parametrize('kind', ['prompt','raw','tokens','stage','ordinal','scope','task',
    'observation','missing_raw','duplicate_raw','extra_stage','request_order','receipt_returns','extra_payload'])
def test_independent_replay_rejects_rehashed_mutations(tmp_path, kind):
    p, registry, sent, _ = peer(tmp_path)
    try:
        p.infer(sent)
        rows = copy.deepcopy(p.journal.records)
        intent = next(r for r in rows if r['kind']=='generation_intent')
        observed = next(r for r in rows if r['kind']=='generation_raw_observed')
        returned = next(r for r in rows if r['kind']=='generation_return')
        request = rows[1]
        receipt = rows[-1]
        if kind=='prompt':
            intent['payload']['prompt_raw'] += ' change'
            intent['payload']['prompt_sha256'] = sha_raw(intent['payload']['prompt_raw'])
            returned['payload']['raw']['prompt_sha256'] = intent['payload']['prompt_sha256']
            receipt['payload']['result']['generation_returns'][0] = returned['payload']['raw']
        elif kind=='raw': observed['payload']['raw_hex'] = b'altered'.hex(); observed['payload']['observed_bytes']=7
        elif kind=='tokens': returned['payload']['raw']['tokens'] = True
        elif kind=='stage': intent['payload']['stage'] = 'invocation'
        elif kind=='ordinal': intent['payload']['ordinal'] = True
        elif kind=='scope': rows[0]['payload']['admission']['scope_sha256'] = 'a'*64
        elif kind=='task': request['payload']['envelope']['request']['task'] = '未经批准的任务'
        elif kind=='observation': receipt['payload']['result']['observation']['status'] = 'operational_failure_no_retry'
        elif kind=='missing_raw': rows.remove(observed)
        elif kind=='duplicate_raw': rows.insert(rows.index(observed), copy.deepcopy(observed))
        elif kind=='extra_stage': rows.insert(len(rows)-1,copy.deepcopy(intent))
        elif kind=='request_order': rows.insert(len(rows)-1,copy.deepcopy(request))
        elif kind=='receipt_returns': receipt['payload']['result']['generation_returns'] = []
        else: returned['payload']['extra'] = 1
        for i,r in enumerate(rows): r['seq']=i
        head = rechain(rows)
        with pytest.raises((ValueError,KeyError)):
            audit_generation(rows,p.binding,head,plans=p.plans,tokenizer=Tokenizer())
    finally: registry.close()


@pytest.mark.parametrize('kind', ['bad_hash','bool_tokens','negative_seconds','nonfinite','oversize','provider_failure'])
def test_invalid_provider_metadata_preserves_raw_before_retirement(tmp_path,kind):
    text = 'x'*262145 if kind=='oversize' else '{"tool":"create_box"}'
    def generate(prompt, stage):
        if kind=='provider_failure': raise OSError('CPU provider interruption')
        value={'raw':text,'tokens':10,'seconds':0.01,'prompt_sha256':sha_raw(prompt),'output_sha256':sha_raw(text)}
        if kind=='bad_hash': value['output_sha256']='0'*64
        elif kind=='bool_tokens': value['tokens']=True
        elif kind=='negative_seconds': value['seconds']=-1
        elif kind=='nonfinite': value['seconds']=float('inf')
        return value
    p, registry, sent, _ = peer(tmp_path,generate=generate)
    try:
        result=p.infer(sent)
        assert result['observation']['status']=='operational_failure_no_retry'
        observed=[r for r in p.journal.records if r['kind']=='generation_raw_observed']
        assert len(observed)==int(kind!='provider_failure')
        if observed:
            assert bytes.fromhex(observed[0]['payload']['raw_hex']) == text.encode()[:262144]
            assert observed[0]['payload']['truncated'] == (kind=='oversize')
        raw=read_journal(p.journal.root,p.binding,'worker',p.journal.head)
        evidence=audit_generation(raw,p.binding,p.journal.head,plans=p.plans,tokenizer=Tokenizer())
        assert evidence['unknown_attempts']==1 and not evidence['coverage_complete']
        with pytest.raises(ValueError,match='no_retry'): p.infer(sent)
    finally: registry.close()


@pytest.mark.parametrize('kind', ['fifo','hardlink','symlink','extra','missing','tamper','permissions'])
def test_readonly_disk_audit_rejects_real_filesystem_faults(tmp_path,kind):
    p, registry, sent, _ = peer(tmp_path)
    try:
        p.infer(sent)
        file=p.journal.root/'raw-0001.json'
        if kind=='fifo': file.unlink(); os.mkfifo(file,0o600)
        elif kind=='hardlink': os.link(file,tmp_path/'second-link')
        elif kind=='symlink': file.unlink(); file.symlink_to(p.journal.root/'raw-0000.json')
        elif kind=='extra': (p.journal.root/'extra.json').write_text('{}')
        elif kind=='missing': file.unlink()
        elif kind=='tamper': file.write_text('{}\n')
        else: file.chmod(0o644)
        with pytest.raises((ValueError,OSError)):
            read_journal(p.journal.root,p.binding,'worker',p.journal.head)
    finally: registry.close()


def test_actual_separate_process_cannot_enter_locked_registry(tmp_path):
    b=binding(tmp_path)
    child_code='''import json,sys
from training.c5_reuse_admission import AdmissionRegistry
try:
    AdmissionRegistry(json.loads(sys.stdin.read()))
except BlockingIOError:
    sys.exit(0)
sys.exit(1)
'''
    with AdmissionRegistry(b,create=True) as registry:
        with registry._locked():
            p=subprocess.run([sys.executable,'-B','-c',child_code],input=canonical(b),capture_output=True,timeout=10)
            assert p.returncode==0,p.stderr.decode()
    with AdmissionRegistry(b) as registry: assert registry.audit()['rows']==[]


def test_empty_or_unanchored_generation_never_claims_complete_coverage(tmp_path):
    p,registry,sent,_=peer(tmp_path)
    try:
        empty=audit_generation(p.journal.records,p.binding,p.journal.head,plans=p.plans,tokenizer=Tokenizer())
        assert not empty['coverage_complete']
        p.infer(sent)
        for kwargs in ({},{'plans':p.plans},{'tokenizer':Tokenizer()}):
            assert not audit_generation(p.journal.records,p.binding,p.journal.head,**kwargs)['coverage_complete']
        assert not audit_generation(p.journal.records,p.binding,None,plans=p.plans,tokenizer=Tokenizer())['coverage_complete']
    finally: registry.close()


def test_only_pinned_public_plans_are_reused_without_private_inputs(tmp_path):
    root=Path(__file__).resolve().parents[1]
    value=public_plan(root)
    assert len(value['task_plans'])==8 and not value['historical_run_reactivated'] and not value['execution_ready']
    public=tmp_path/SOURCE
    public.parent.mkdir(parents=True); public.write_bytes((root/SOURCE).read_bytes()+b' ')
    with pytest.raises(ValueError,match='source_drift'): public_plan(tmp_path)


@pytest.mark.parametrize('boundary', ['request_intent','generation_intent'])
def test_durable_intent_failure_prevents_any_provider_call_and_reconstruction(tmp_path,boundary):
    p,registry,sent,calls=peer(tmp_path)
    original=p.journal.append
    def append(kind,payload):
        if kind==boundary: raise OSError('CPU injected durability failure')
        original(kind,payload)
    p.journal.append=append
    try:
        if boundary=='request_intent':
            with pytest.raises(OSError): p.infer(sent)
        else:
            assert p.infer(sent)['observation']['status']=='operational_failure_no_retry'
        assert calls==[]
        with pytest.raises(ValueError,match='no_retry'): p.infer(sent)
    finally: registry.close()
    with AdmissionRegistry(p.binding) as registry:
        with pytest.raises(FileExistsError): registry.claim('worker')


@pytest.mark.parametrize('boundary', ['guard','budget','clock'])
def test_post_generation_boundary_failure_retains_return_without_retry(tmp_path,boundary):
    p,registry,sent,calls=peer(tmp_path)
    original=p.generate
    def generate(prompt,stage):
        value=original(prompt,stage)
        def fail(): raise ValueError('CPU source or resource drift')
        if boundary=='guard': p.guard=fail
        elif boundary=='budget': p.check_budget=fail
        else: p.clock=lambda:0
        return value
    p.generate=generate
    try:
        with pytest.raises(ValueError): p.infer(sent)
        assert calls==['selector']
        assert any(row['kind']=='generation_return' for row in p.journal.records)
        raw=read_journal(p.journal.root,p.binding,'worker',p.journal.head)
        result=audit_generation(raw,p.binding,p.journal.head,plans=p.plans,tokenizer=Tokenizer())
        assert result['unknown_attempts']==1 and not result['coverage_complete']
        with pytest.raises(ValueError,match='no_retry'): p.infer(sent)
    finally: registry.close()


@pytest.mark.parametrize('kind', ['task','route','runtime','formal_study'])
def test_unapproved_requests_never_enter_generation(tmp_path,kind):
    p,registry,sent,calls=peer(tmp_path)
    try:
        if kind=='task': sent['request']['task']='做一个未登记的三角形'
        elif kind=='route': sent['request']['route']='lora'
        elif kind=='runtime': sent['request']['runtime_freeze_sha256']='f'*64
        else: sent['request']['probe_id']='c5-rhino-paired-20-reuse-v1'
        with pytest.raises(ValueError): p.infer(sent)
        assert calls==[] and len(p.journal.records)==1
    finally: registry.close()
