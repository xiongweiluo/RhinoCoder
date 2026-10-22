import copy
import importlib.util
import json
from pathlib import Path
import sys
import pytest

REPO=Path(__file__).resolve().parents[1]
import training.c5_formal_reuse_supervisor as candidate
from plugin.rhino_listener.c5_research_native import NativeError
SPEC=json.loads((REPO/'eval/c5/formal-reuse-spec-20261022.json').read_bytes())
LIMITS={'model_seconds':360,'startup_seconds':600,'first_request_idle_seconds':600,'between_requests_idle_seconds':3600}

def test_actual_approved_spec_missing_watchdog_is_rejected_before_all_effects(tmp_path,monkeypatch):
    assert 'runtime_limits' not in SPEC
    state=tmp_path/'must-remain-absent'
    def forbidden(*args,**kw):pytest.fail('worker effect preceded complete public configuration validation')
    monkeypatch.setattr(candidate.os,'fork',forbidden)
    monkeypatch.setattr(candidate,'claim_gpu_role',forbidden)
    with pytest.raises((ValueError,NativeError),match='formal_reuse_complete_frozen_watchdog_limits_required'):
        candidate.supervise(state,SPEC,{},1,forbidden,forbidden)
    assert not state.exists()

def test_real_spec_with_explicit_finite_limits_constructs_original_watchdog():
    spec={**SPEC,'runtime_limits':dict(LIMITS)}
    limits=candidate.watchdog_limits(spec)
    clock=[1.]
    watch=candidate.FormalWatchdog(1,64740,clock=lambda:clock[0],limits=limits)
    watch.feed(candidate.PACKET.pack(b'L',clock[0]))
    clock[0]+=1000
    assert watch.check()>60000
    watch.feed(candidate.PACKET.pack(b'B',clock[0]))
    for _ in range(56):
        clock[0]+=1
        for kind in (b'R',b'S',b'E',b'D'):watch.feed(candidate.PACKET.pack(kind,clock[0]))
    with pytest.raises((ValueError,NativeError)):watch.feed(candidate.PACKET.pack(b'R',clock[0]))

@pytest.mark.parametrize('change',[
    {'model_seconds':True},{'startup_seconds':600.0},{'first_request_idle_seconds':None},
    {'between_requests_idle_seconds':3601},{'extra':1}])
def test_malformed_or_expanded_frozen_limits_rejected(change):
    spec={**SPEC,'runtime_limits':{**LIMITS,**change}}
    with pytest.raises((ValueError,NativeError),match='formal_reuse_complete_frozen_watchdog_limits_required'):
        candidate.watchdog_limits(spec)

@pytest.mark.parametrize('key,value',[('startup_timeout_seconds',601),('per_request_timeout_seconds',361)])
def test_watchdog_and_wire_limits_cannot_disagree(key,value):
    spec={**SPEC,'runtime_limits':dict(LIMITS),key:value}
    with pytest.raises((ValueError,NativeError)):candidate.watchdog_limits(spec)
