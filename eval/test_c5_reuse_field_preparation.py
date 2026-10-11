"""Independent CPU fixtures only; no actual records are approved or deployed."""
import contextlib
import copy
import os
from pathlib import Path
import sqlite3

import pytest

from training.c5_reuse_evidence import canonical, sha
from training.c5_reuse_field_scope import bind, COMPARISON, LIMITS, STUDY, PROTOCOL, APPROVAL_BASIS
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_generation import GenerationPeer
from training.c5_reuse_field_wire import envelope
from training.c5_reuse_generation_audit import audit_generation
from training.c5_reuse_stop import stop_once
from training.c5_model_transport import request
from eval.test_c5_model_transport import Tokenizer


def records(tmp_path, *, plans=None):
    plans = plans or {'slot-base': {'route': 'base', 'steps': ['创建宽2深3高4毫米的盒体。']}}
    spec = {'protocol': PROTOCOL, 'study_id': STUDY, 'phase': 'development', 'instance_id': 'reuse-dev-cpu-test',
        'comparison': copy.deepcopy(COMPARISON), 'limits': copy.deepcopy(LIMITS), 'development_plan_sha256': sha(plans),
        'execution_ready': True, 'automatic_retry_allowed': False, 'private_formal_data_allowed': False,
        'default_route_change_allowed': False,
        'resources': {'lease_expiry_epoch': 10000, 'generation_cutoff_epoch': 9000, 'export_reserve_seconds': 1000,
            'prior_cumulative_upper_bound_seconds': 1000, 'remaining_gpu_seconds': 21600,
            'development_seconds_max': 3600, 'formal_seconds_max': 18000,
            'research_seconds_max': 21600, 'original_cumulative_seconds_max': 57600},
        'host_policy': {'instance_id': 'reuse-dev-cpu-test', 'accepted_by_owner': True,
            'acceptance_record_sha256': 'c'*64, 'readable_files_frozen': True, 'opaque_host_trusted': True,
            'full_byte_closure_claimed': False, 'baseline_before_generation': True,
            'new_events_after_baseline_allowed': False, 'external_readiness_and_final_capture_required': True}}
    runtime = {'protocol': PROTOCOL, 'study_id': STUDY, 'instance_id': spec['instance_id'], 'spec_sha256': sha(spec),
        'paths': {'source_root': str(tmp_path/'reuse-dev-cpu-test-source'),
                  'state_root': str(tmp_path/'reuse-dev-cpu-test-state'),
                  'admission_root': str(tmp_path/'c5-reuse-global-admission-v1')},
        'source_files': {'training/c5_contract.py': 'a'*64}, 'environment_sha256': 'a'*64,
        'model_assets_sha256': 'b'*64, 'host_readable_files_sha256': 'c'*64,
        'host_policy': copy.deepcopy(spec['host_policy']), 'resources': copy.deepcopy(spec['resources']), 'execution_ready': True}
    approval = {'study_id': STUDY, 'instance_id': spec['instance_id'], 'actor': 'repository_owner', 'approved': True,
                'spec_sha256': sha(spec), 'runtime_sha256': sha(runtime), 'approval_basis': APPROVAL_BASIS}
    return spec, runtime, approval, plans


def binding(tmp_path, *, plans=None):
    spec, runtime, approval, _ = records(tmp_path, plans=plans)
    return bind(spec, runtime, approval, now=100)


def test_binding_is_partial_not_owner_or_field_origin_proof(tmp_path):
    result = binding(tmp_path)
    assert result['record_binding_verified'] and not result['approval_origin_verified']
    assert not result['whole_field_authority_verified']
    assert not Path(result['paths']['state_root']).exists()


@pytest.mark.parametrize('change', ['old_study', 'formal_study', 'protocol', 'comparison', 'limits',
    'not_ready', 'no_assets', 'missing_host_acceptance', 'old_instance_acceptance', 'full_closure',
    'private', 'retry', 'route', 'expired', 'budget', 'export', 'prior', 'old_path', 'grant', 'bool'])
def test_scope_rejects_old_authority_missing_evidence_or_budget(tmp_path, change):
    spec, runtime, approval, _ = records(tmp_path)
    if change in ('old_study', 'formal_study'):
        spec['study_id'] = 'c5-rhino-paired-20-v1' if change == 'old_study' else 'c5-rhino-paired-20-reuse-v1'
    elif change == 'protocol': spec['protocol'] = 'old'
    elif change == 'comparison': spec['comparison']['checkpoint'] = 'other'
    elif change == 'limits': spec['limits']['generation_stages'] = 113
    elif change == 'not_ready': spec['execution_ready'] = False
    elif change == 'no_assets': runtime['model_assets_sha256'] = None
    elif change == 'missing_host_acceptance': spec['host_policy']['accepted_by_owner'] = False
    elif change == 'old_instance_acceptance': spec['host_policy']['instance_id'] = 'old'
    elif change == 'full_closure': spec['host_policy']['full_byte_closure_claimed'] = True
    elif change == 'private': spec['private_formal_data_allowed'] = True
    elif change == 'retry': spec['automatic_retry_allowed'] = True
    elif change == 'route': spec['default_route_change_allowed'] = True
    elif change == 'expired': spec['resources']['generation_cutoff_epoch'] = 99
    elif change == 'budget': spec['resources']['remaining_gpu_seconds'] = 100
    elif change == 'export': spec['resources']['export_reserve_seconds'] = 899
    elif change == 'prior': spec['resources']['prior_cumulative_upper_bound_seconds'] = 57600
    elif change == 'old_path': runtime['paths']['state_root'] = str(tmp_path/'formal20-state-v4')
    elif change == 'bool': spec['resources']['development_seconds_max'] = True
    else: approval['runtime_sha256'] = '0'*64
    # Rebind all other hashes; negative control is about policy, not only hash drift.
    runtime['spec_sha256'] = sha(spec)
    runtime['resources'] = copy.deepcopy(spec['resources']); runtime['host_policy'] = copy.deepcopy(spec['host_policy'])
    approval['spec_sha256'] = sha(spec)
    if change != 'grant': approval['runtime_sha256'] = sha(runtime)
    with pytest.raises(ValueError): bind(spec, runtime, approval, now=100)
    assert not Path(runtime['paths']['state_root']).exists()


def test_admission_cannot_be_bypassed_with_new_directory_or_runtime(tmp_path):
    b = binding(tmp_path)
    with AdmissionRegistry(b, create=True) as registry:
        registry.claim('worker')
    b2 = copy.deepcopy(b)
    b2['instance_id'] = 'reuse-dev-other'
    b2['runtime_sha256'] = 'f'*64
    b2['paths']['source_root'] = str(tmp_path/'reuse-dev-other-source')
    b2['paths']['state_root'] = str(tmp_path/'reuse-dev-other-state')
    with AdmissionRegistry(b2) as registry:
        with pytest.raises(FileExistsError): registry.claim('worker')
        assert len(registry.audit()['rows']) == 1


@pytest.mark.parametrize('boundary', ['after_tombstone','after_commit'])
def test_admission_crash_never_resets_or_replays(tmp_path, boundary):
    b = binding(tmp_path)
    def fail(where):
        if where == boundary: raise OSError('CPU crash')
    with AdmissionRegistry(b, create=True) as registry:
        with pytest.raises(OSError): registry.claim('worker', fault=fail)
    if boundary == 'after_tombstone':
        with pytest.raises(ValueError, match='unknown_no_retry'): AdmissionRegistry(b)
    else:
        with AdmissionRegistry(b) as registry:
            with pytest.raises(FileExistsError): registry.claim('worker')
    assert (Path(b['paths']['admission_root'])/'worker.consumed.json').exists()


def test_cross_process_registry_lock_and_extra_schema_fail_closed(tmp_path):
    b = binding(tmp_path)
    with AdmissionRegistry(b, create=True) as registry:
        with pytest.raises(BlockingIOError): AdmissionRegistry(b)
        registry.db.execute('CREATE TABLE alternate(x INTEGER)'); registry.db.commit()
        with pytest.raises(ValueError, match='schema'): registry.claim('worker')


def peer(tmp_path, *, generate=None):
    b = binding(tmp_path)
    Path(b['paths']['state_root']).mkdir(mode=0o700)
    registry = AdmissionRegistry(b, create=True)
    calls = []
    def good(prompt, stage):
        calls.append(stage)
        raw = '{"tool":"create_box"}' if stage=='selector' else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'
        return {'raw':raw, 'tokens':10, 'seconds':0.01,
                'prompt_sha256':sha_raw(prompt), 'output_sha256':sha_raw(raw)}
    plans = records(tmp_path)[3]
    p = GenerationPeer(b, registry, plans, Tokenizer(), generate or good, lambda route:contextlib.nullcontext(),
                       lambda:None, lambda:None)
    sent = request(STUDY,'slot-base','base',0,plans['slot-base']['steps'][0],
                   {'unit':'Millimeters','objects':[],'groups':{}},
                   {'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64},b['runtime_sha256'],'new-request')
    return p, registry, envelope(b, sent), calls


def sha_raw(raw):
    from training.c5_reuse_evidence import raw_sha
    return raw_sha(raw.encode())


def test_peer_records_before_generation_and_raw_replay(tmp_path):
    p, registry, sent, calls = peer(tmp_path)
    try:
        actual = p.generate
        def generate(prompt, stage):
            assert p.journal.records[-1]['kind'] == 'generation_intent'
            persisted = p.journal.root/('raw-%04d.json' % (len(p.journal.records)-1))
            from plugin.rhino_listener.c5_research_native import canonical as public_canonical
            assert persisted.read_bytes() == public_canonical(p.journal.records[-1]).encode() + b'\n'
            return actual(prompt, stage)
        p.generate = generate
        result = p.infer(sent)
        assert calls == ['selector','invocation'] and result['observation']['status'] == 'schema_valid_not_authorized'
        counts = audit_generation(p.journal.records,p.binding,p.journal.head,plans=p.plans,tokenizer=Tokenizer())
        assert counts['recorded_generation_attempts'] == counts['recorded_generation_returns'] == 2
        assert counts['coverage_complete'] and not counts['execution_ready']
        with pytest.raises(ValueError): p.infer(sent)
        assert calls == ['selector','invocation']
    finally: registry.close()


def test_unknown_generation_blocks_new_request_and_reconstructor(tmp_path):
    def fail(prompt, stage): raise OSError('CPU injected generation uncertainty')
    p, registry, sent, _ = peer(tmp_path, generate=fail)
    try:
        result = p.infer(sent)
        assert result['observation']['status'] == 'operational_failure_no_retry'
        counts = audit_generation(p.journal.records,p.binding,p.journal.head,plans=p.plans,tokenizer=Tokenizer())
        assert counts['unknown_attempts'] == 1 and not counts['coverage_complete']
        sent['request']['request_id'] = 'different-request'
        with pytest.raises(ValueError, match='no_retry'): p.infer(sent)
    finally: registry.close()
    with AdmissionRegistry(p.binding) as reopened:
        with pytest.raises(FileExistsError): GenerationPeer(p.binding,reopened,p.plans,Tokenizer(),fail,
            lambda route:contextlib.nullcontext(),lambda:None,lambda:None)


class Ops:
    def __init__(self, expected, *, drift=False, fail=False):
        self.expected, self.drift, self.fail, self.calls = expected, drift, fail, []
    def guard(self): self.calls.append('guard')
    def pin(self, pid): self.calls.append('pin'); return 10
    def identity(self, pid): return dict(self.expected, start_ticks=999) if self.drift else self.expected
    def exited(self, fd): return False
    def send(self, fd):
        self.calls.append('send')
        if self.fail: raise OSError('CPU unknown syscall')
    def wait(self, fd, seconds): self.calls.append('wait'); return True
    def close(self, fd): self.calls.append('close')


@pytest.mark.parametrize('kind', ['success','drift','syscall_unknown','journal_failure'])
def test_stop_is_one_exact_pidfd_attempt_and_no_retry(tmp_path, kind):
    b = binding(tmp_path)
    expected = {'pid':100,'uid':1000,'boot_id':'a'*36,'start_ticks':100,
                'executable_sha256':'a'*64,'argv_sha256':'b'*64,'cwd':'/cpu-fixture'}
    grant = {'study_id':STUDY,'actor':'repository_owner','approved':True,
             'spec_sha256':b['spec_sha256'],'runtime_sha256':b['runtime_sha256'],
             'target_identity_sha256':sha(expected),'signal':'SIGTERM','signals_max':1,
             'approval_basis':'direct repository_owner exact reuse stop scope approval'}
    ops = Ops(expected,drift=kind=='drift',fail=kind=='syscall_unknown')
    events = []
    def journal(kind_, value):
        if kind == 'journal_failure' and kind_ == 'signal_intent': raise OSError('CPU disk failure')
        events.append((kind_,value))
    with AdmissionRegistry(b,create=True) as registry:
        if kind == 'success':
            r = stop_once(b,expected,grant,registry,journal,ops)
            assert r['exit_observed'] and r['gpu_absence_independently_verified'] is None
        else:
            with pytest.raises((OSError,ValueError)): stop_once(b,expected,grant,registry,journal,ops)
        assert ops.calls.count('send') == int(kind in ('success','syscall_unknown'))
        with pytest.raises(FileExistsError): stop_once(b,expected,grant,registry,journal,ops)


def test_new_host_scope_uses_retained_observer_and_independent_audit(tmp_path):
    from plugin.rhino_listener.c5_reuse_host_session import ReuseHostSession
    from training.c5_host_assurance_audit import audit_host_continuity
    from eval.test_c5_host_assurance_session import Backend
    b = binding(tmp_path)
    Path(b['paths']['state_root']).mkdir(mode=0o700)
    backend = Backend()
    with AdmissionRegistry(b,create=True) as registry:
        host = ReuseHostSession(b,registry,backend,lambda:'a'*64,'a'*64)
        assert backend.calls == []
        host.seal_baseline(); host.checkpoint('cpu_step'); receipt = host.finish()
        result = audit_host_continuity(host.state,STUDY,b['runtime_sha256'],'a'*64,receipt['seal_sha256'],
                                      normal_limit=2048,cleanup_limit=256,journal_limit=4096)
        assert result['status'] == 'limited_host_continuity_audit_verified'
        with pytest.raises(FileExistsError):
            ReuseHostSession(b,registry,Backend(),lambda:'a'*64,'a'*64).seal_baseline()
