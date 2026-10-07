"""Synthetic metadata only: no live CLR/Rhino/GPU or private cases."""
import copy
import json

import pytest

from eval.test_c5_host_assurance_v2 import data
from plugin.rhino_listener.c5_host_assurance_v2 import POLICY, ASSUMPTIONS
from plugin.rhino_listener.c5_host_assurance_session import (
    DEV_ID, STUDIES, HostAssuranceSession, host_policy, validate_study_binding,
)
from plugin.rhino_listener.c5_research_native import digest, NativeError
from training.c5_host_assurance_audit import audit_host_continuity
from training.c5_host_assurance_audit import audit_request_checkpoint_bindings
from plugin.rhino_listener.c5_research_channel import publish_json


def authority():
    transition = {'policy_id': POLICY, 'purpose': 'guarantee_transition_preparation_only_no_execution',
        'assumptions': copy.deepcopy(ASSUMPTIONS), 'default_admission_enabled': False,
        'model_or_fixture_or_holdout_authorized': False}
    consent = {'actor': 'repository_owner', 'approved': True, 'policy_id': POLICY,
        'transition_spec_sha256': digest(transition),
        'approval_basis': 'direct owner acceptance of weaker host assurance and research-exclusive preparation; no study execution'}
    spec = {'study_id': DEV_ID, 'execution_ready': True, 'host_assurance': host_policy(transition, consent),
        'automatic_retry_allowed': False, 'default_route_change_allowed': False}
    freeze = {'study_id': DEV_ID, 'execution_ready': True, 'spec_sha256': digest(spec),
        'host_assurance': copy.deepcopy(spec['host_assurance'])}
    grant = {'study_id': DEV_ID, 'actor': 'repository_owner', 'approved': True,
        'spec_sha256': digest(spec), 'runtime_freeze_sha256': digest(freeze), 'approval_basis': STUDIES[DEV_ID]}
    return spec, freeze, grant, transition, consent


class Backend:
    def __init__(self):
        self.value, _, self.events = data()
        self.calls, self.active, self.fail = [], False, None
    def subscribe(self):
        self.calls.append('subscribe')
        self.active = True
        if self.fail == 'subscribe': raise RuntimeError('synthetic uncertain subscription')
    def unsubscribe(self):
        self.calls.append('unsubscribe')
        if self.fail == 'detach': raise RuntimeError('synthetic uncertain detach')
        self.active = False
    def snapshot(self):
        self.calls.append('snapshot')
        if self.fail == 'snapshot': raise RuntimeError('synthetic failed capture')
        return copy.deepcopy(self.value)
    def drain_events(self):
        result = copy.deepcopy(self.events)
        self.events = {'events': [], 'errors': [], 'dropped': 0}
        return result


def session(tmp_path, backend=None, guard=None):
    state = tmp_path / 'state'
    state.mkdir(mode=0o700)
    records = authority()
    binding = validate_study_binding(*records)
    backend = backend or Backend()
    return HostAssuranceSession(state, binding, backend, guard or (lambda: 'a'*64), 'a'*64), backend


def audit(s, receipt):
    return audit_host_continuity(s.state, DEV_ID, s.binding['runtime_freeze_sha256'], 'a'*64, receipt['seal_sha256'])


def test_raw_full_lifecycle_and_independent_replay(tmp_path):
    s, backend = session(tmp_path)
    assert backend.calls == []
    s.seal_baseline()
    assert s.checkpoint('slot_open') == 'a'*64
    assert s.cleanup_checkpoint('slot_close') == 'a'*64
    receipt = s.finish()
    value = audit(s, receipt)
    assert value['limited_visible_continuity_verified'] and not backend.active
    assert not value['execution_authority'] and not value['legacy_byte_closure_verified']
    with pytest.raises(NativeError): s.finish()
    with pytest.raises(NativeError): s.checkpoint('cannot_resume')


@pytest.mark.parametrize('mutation', ['surface', 'module', 'native', 'event', 'drop', 'event_error', 'document'])
def test_sticky_drift_retains_cleanup_but_cannot_pass(tmp_path, mutation):
    s, b = session(tmp_path); s.seal_baseline()
    if mutation == 'surface':
        b.value['assemblies'][0]['visible_type_count'] = 1
        row = b.value['assemblies'][0]; row['surface_sha256'] = digest({k:v for k,v in row.items() if k != 'surface_sha256'})
    elif mutation == 'module': b.value['python_origins'].append({'module': 'unexpected'})
    elif mutation == 'native': b.value['native_images'].append({'origin_sha256': 'new'})
    elif mutation == 'event': b.events['events'] = [{'same_name_not_exempt': True}]
    elif mutation == 'drop': b.events['dropped'] = 1
    elif mutation == 'event_error': b.events['errors'] = ['unknown callback']
    elif mutation == 'document': b.value['active_sha256'] = 'c'*64
    with pytest.raises(RuntimeError): s.checkpoint('before_dispatch')
    with pytest.raises(NativeError): s.checkpoint('no_second_dispatch')
    assert s.cleanup_checkpoint('authorized_close_only') == 'a'*64
    result = audit(s, s.finish())
    assert not result['limited_visible_continuity_verified']
    assert result['status'] == 'host_continuity_failed_or_incomplete_no_replay'


@pytest.mark.parametrize('failure', ['subscribe', 'snapshot', 'detach', 'source'])
def test_operational_failures_detach_once_never_claim_success(tmp_path, failure):
    b = Backend()
    guard = (lambda: '0'*64) if failure == 'source' else None
    b.fail = failure
    s, _ = session(tmp_path, b, guard)
    if failure == 'detach': s.seal_baseline()
    else:
        with pytest.raises((RuntimeError, NativeError)): s.seal_baseline()
    receipt = s.finish()
    assert receipt['blocked']
    assert b.calls.count('unsubscribe') <= 1
    assert audit(s, receipt)['limited_visible_continuity_verified'] is False


@pytest.mark.parametrize('mutation', ['old_study', 'broad_grant', 'only_transition', 'strong_byte_claim', 'changed_spec'])
def test_transition_consent_is_not_study_execution_grant(mutation):
    spec, freeze, grant, transition, consent = authority()
    if mutation == 'old_study': spec['study_id'] = freeze['study_id'] = 'C5DEV-MODELBRIDGE-20261003-B'
    elif mutation == 'broad_grant': grant = {'approved': True, 'actor': 'repository_owner'}
    elif mutation == 'only_transition': grant = consent
    elif mutation == 'strong_byte_claim': freeze['host_assurance']['legacy_byte_closure_verified'] = True
    elif mutation == 'changed_spec': spec['automatic_retry_allowed'] = True
    with pytest.raises(NativeError): validate_study_binding(spec, freeze, grant, transition, consent)


@pytest.mark.parametrize('mutation', ['raw_snapshot', 'chain', 'extra', 'external_receipt', 'producer_claim'])
def test_independent_audit_rejects_raw_tampering(tmp_path, mutation):
    s, _ = session(tmp_path); s.seal_baseline(); receipt = s.finish()
    if mutation == 'external_receipt': receipt['seal_sha256'] = '0'*64
    elif mutation == 'extra': (s.state/'host-continuity-0900.json').write_text('{}')
    elif mutation == 'producer_claim':
        path = s.state/'host-continuity-seal.json'; v = json.loads(path.read_text()); v['legacy_byte_closure_verified'] = True
        path.write_text(json.dumps(v)); receipt['seal_sha256'] = digest(v)
    else:
        path = s.state/'host-continuity-0003.json'; v = json.loads(path.read_text())
        if mutation == 'chain': v['previous_sha256'] = '0'*64
        else: v['payload']['snapshot']['native_images'] = []
        path.write_text(json.dumps(v))
    with pytest.raises((NativeError, ValueError)): audit(s, receipt)


def test_permanent_claim_does_not_allow_fresh_instance_replay(tmp_path):
    s, b = session(tmp_path); s.seal_baseline(); s.finish()
    another = HostAssuranceSession(s.state, s.binding, b, lambda:'a'*64, 'a'*64)
    with pytest.raises(FileExistsError): another.seal_baseline()


def test_unsealed_or_exhausted_session_rejects_dispatch(tmp_path):
    s, _ = session(tmp_path)
    with pytest.raises(NativeError): s.checkpoint('premature')
    s.seal_baseline(); s.checkpoints = 512
    with pytest.raises(NativeError): s.checkpoint('over_limit')
    # Detach still executes once; cap exhaustion cannot be claimed clean.
    receipt = s.finish(); assert receipt['blocked']


@pytest.mark.parametrize('mutation',[None,'missing','request','head','cleanup_borrow'])
def test_every_raw_request_requires_correct_anchored_host_checkpoint(tmp_path,mutation):
    s,_=session(tmp_path);s.seal_baseline()
    slot=s.state/'write-base';slot.mkdir(mode=0o700)
    sent={'kind':'control','envelope':{'payload':{'action':'capture'}}}
    s.checkpoint('synthetic_native_capture')
    check={'request_sha256':digest(sent),'host_record_sha256':s.head,'host_sequence':s.sequence-1,
        'runtime_freeze_sha256':s.binding['runtime_freeze_sha256']}
    if mutation=='request':check['request_sha256']='0'*64
    elif mutation=='head':check['host_record_sha256']='0'*64
    elif mutation=='cleanup_borrow':sent['envelope']['payload']['action']='close';check['request_sha256']=digest(sent)
    publish_json(slot,'request-0001.json',sent)
    if mutation!='missing':publish_json(slot,'host-check-0001.json',check)
    receipt=s.finish();assert audit(s,receipt)['limited_visible_continuity_verified']
    if mutation is None:
        assert audit_request_checkpoint_bindings(s.state,['write-base'],s.binding['runtime_freeze_sha256'])[
            'raw_requests_bound_to_anchored_checkpoints']==1
    else:
        with pytest.raises(NativeError):audit_request_checkpoint_bindings(s.state,['write-base'],s.binding['runtime_freeze_sha256'])


@pytest.mark.parametrize('mutation',[None,'ready','terminal','extra_sidecar'])
def test_actual_entry_sidecars_are_bound_not_ignored_or_counted_as_extra_raw_records(tmp_path,mutation):
    s,_=session(tmp_path);s.seal_baseline();receipt=s.finish()
    ready={'study_id':DEV_ID,'runtime_freeze_sha256':s.binding['runtime_freeze_sha256'],
        'legacy_byte_closure_verified':False,'sealed_before_model_generation':True}
    terminal=copy.deepcopy(receipt)
    if mutation=='ready':ready['legacy_byte_closure_verified']=True
    elif mutation=='terminal':terminal['seal_sha256']='0'*64
    publish_json(s.state,'host-continuity-ready.json',ready)
    publish_json(s.state,'host-continuity-terminal-receipt.json',terminal)
    if mutation=='extra_sidecar':publish_json(s.state,'host-continuity-unknown.json',{})
    if mutation is None:assert audit(s,receipt)['limited_visible_continuity_verified']
    else:
        with pytest.raises(NativeError):audit(s,receipt)
