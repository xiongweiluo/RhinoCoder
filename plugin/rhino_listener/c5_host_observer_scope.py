"""Fixed observer authority. No subscription, canary, Rhino or task on import."""
import hashlib
import json
from pathlib import Path

from .c5_host_observer import PROBE_ID
from .c5_research_channel import read_json
from .c5_research_native import digest, require
from .c5_research_provenance import SourceGuard

ROOT=Path(__file__).resolve().parents[2]
STATE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/host-observer-state-20261006-A')
SPEC='eval/c5/host-observer-spec-20261006-a.json'
FREEZE='eval/c5/host-observer-runtime-freeze-20261006-a.json'
BASIS='direct repository_owner approval of exact C5 host observer capability spec/runtime; no field or formal execution'


def public(name):
    path=ROOT/name
    require(path.is_file() and path.resolve()==path and 0<path.stat().st_size<=1048576,
        'bounded fixed observer public file required')
    def pairs(items):
        value={}
        for key,child in items:
            require(key not in value,'duplicate observer public key')
            value[key]=child
        return value
    return json.loads(path.read_bytes(),object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite observer public value')))


def file_sha(path):
    require(path.is_file() and path.resolve()==path,'observer frozen file path differs')
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def validate_authority(spec, freeze, approval):
    require(spec.get('probe_id')==freeze.get('probe_id')==PROBE_ID
        and spec.get('purpose')=='existing_host_capability_only_not_clean_baseline'
        and spec.get('state_root')==str(STATE) and spec.get('max_seconds')==180
        and spec.get('max_subscriptions')==1 and spec.get('max_canary_assemblies')==2
        and spec.get('max_empty_types')==1 and spec.get('canary_access')=='Run_noncollectible_until_host_exit'
        and spec.get('observer_prepared') is True
        and spec.get('canary_names')=={'subscribed':'C5OBS_20261006_A_SUBSCRIBED',
            'detached':'C5OBS_20261006_A_DETACHED'}, 'fixed observer capability scope differs')
    require(all(spec.get(k) is False for k in ('model_allowed','tool_dispatch_allowed','fixture_allowed',
        'holdout_allowed','default_route_change_allowed','legacy_guard_relaxation_allowed','automatic_retry_allowed')),
        'observer no-model/no-tool/no-holdout boundaries differ')
    require(freeze.get('spec_sha256')==digest(spec) and freeze.get('formal_execution_ready') is False
        and freeze.get('complete_runtime_closure_claimed') is False,
        'observer freeze must not claim admission/complete closure')
    require(approval=={'probe_id':PROBE_ID,'actor':'repository_owner','approved':True,
        'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),'approval_basis':BASIS},
        'new exact observer owner approval required')
    return digest(freeze)


def scope():
    spec,freeze=public(SPEC),public(FREEZE)
    approval=read_json(STATE,'owner-approval.json')
    validate_authority(spec,freeze,approval)
    require(str(ROOT)==freeze['source_root'] and file_sha(ROOT/SPEC)==freeze['spec_file_sha256'],
        'observer source/spec location differs')
    guard=SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],
        project_prefixes=(__name__.split('.')[0],))
    def check():
        guard()
        require(all(file_sha(Path(p))==sha for p,sha in freeze['frozen_observed_host_files'].items()),
            'observer known host bytes changed')
    check()
    return spec,freeze,approval,check
