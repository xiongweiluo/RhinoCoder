"""New fixed development authority, Python 3.9; no effects on import."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from .c5_host_assurance_session import DEV_B_ID, validate_study_binding
from .c5_research_channel import read_json
from .c5_research_native import digest, require
from .c5_research_provenance import SourceGuard

ID = DEV_B_ID
MAC_SOURCE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-source-20261007-B')
STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-state-20261007-B')
REMOTE_SOURCE = Path('/data/RhinoCoder-c5-hostassurance-dev-B')
REMOTE_STATE = Path('/data/c5-hostassurance-dev-state-20261007-B')
ENV = Path('/data/conda-envs/rhinocoder')
SOCKET = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/ssh-22159.control')
PIN = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/known-hosts-22159')
PIN_SHA = 'ae41a99e39f76b1be352f0098439b126fe5b8465c358b8dabbb7a71e53d2d1a9'
SPEC = 'eval/c5/hostassurance-development-spec-20261007-b.json'
FREEZE = 'eval/c5/hostassurance-development-runtime-freeze-20261007-b.json'
TRANSITION = 'eval/c5/host-assurance-transition-spec-v2-20261006.json'
CONSENT = 'eval/c5/host-assurance-transition-owner-approval-v2-20261006.json'
BASE = '63f7de2f37a997c829ec98eaf617cdc78808586bc9df1139a90c030c4d76ebae'
ADAPTER = '305d72703270d16e93233d1d34ae27cdaddd777e4530afead88c7edb8dc22cae'


def file_sha(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_file(), 'frozen regular code file required')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576), b''): value.update(block)
    return value.hexdigest()


def public(root, name):
    import json
    path = root / name
    require(path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= 1048576,
        'bounded fixed public file required')
    def pairs(items):
        value = {}
        for k,v in items:
            require(k not in value, 'duplicate public JSON key'); value[k] = v
        return value
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def authority(spec, freeze, approval, transition, consent, *, check_time=True):
    binding = validate_study_binding(spec, freeze, approval, transition, consent)
    require(spec['study_id'] == spec['probe_id'] == freeze.get('probe_id') == ID,
        'distinct new development ID required')
    fixed = {'mac_source_root':str(MAC_SOURCE), 'mac_state_root':str(STATE),
        'remote_source_root':str(REMOTE_SOURCE), 'remote_state_root':str(REMOTE_STATE),
        'environment_root':str(ENV), 'ssh_socket':str(SOCKET), 'ssh_host':'175.155.64.171',
        'ssh_port':22159, 'ssh_known_hosts_file':str(PIN), 'ssh_known_hosts_file_sha256':PIN_SHA,
        'base_revision':'c03e6d358207e414f1eca0bb1891e29f1db0e242', 'adapter_sha256':ADAPTER,
        'contract_id':'qwen25-v4-selector-v3-json-invoker-c5-v1'}
    require(all(spec.get(k) == v for k,v in fixed.items()), 'new fixed development roots/transport/models differ')
    protocol=spec.get('entry_return_protocol',{})
    expected_wrapper='#! python 3\nimport runpy\nscope = runpy.run_path("'+str(MAC_SOURCE)+'/tools/c5_rhino_hostassurance_dev_b.py", run_name="__main__")\nscope["ENTRY_RETURN_BARRIER"].release_after_entry_return()\n'
    require(protocol=={'wrapper_code':expected_wrapper,'release_called_after_run_path_returns':True,
        'first_non_command_idle_seals_once':True,'seal_callback_dispatches_no_task':True,
        'no_main_module_whitelist_or_ignore':True,'baseline_failure_cannot_retry':True}
        and all(protocol[k] is True for k in protocol if k!='wrapper_code'),
        'exact post-runpy-return release/first-idle protocol required')
    require(freeze.get('model_identities') == {'base':BASE,'lora':ADAPTER}
        and freeze.get('legacy_byte_closure_verified') is False
        and freeze.get('formal_execution_ready') is False
        and freeze.get('missing_metadata_files') == ['pip:../../../bin/pip3.13']
        and spec.get('pip_metadata_policy') == 'retain_exact_missing_nonloadable_pip3.13_launcher_no_install_no_byte_claim',
        'frozen model/limited-host/pip anomaly boundary differs')
    order = ['write-base','write-lora','read-lora','read-base','clarify-base','clarify-lora','unsupported-lora','unsupported-base']
    require(spec.get('slot_order') == order and set(spec.get('task_plans',{})) == set(order)
        and set(spec.get('slot_policies',{})) == set(order)
        and spec.get('generation_requests_max') == 8 and spec.get('generation_calls_max') == 16
        and spec.get('holdout_calls') == spec.get('training_calls') == 0,
        'exact eight public development slots required')
    for slot in order:
        p, limits = spec['task_plans'][slot], spec['slot_policies'][slot]
        require(set(p) == {'route','steps'} and p['route'] == slot.rsplit('-',1)[1]
            and isinstance(p['steps'], list) and len(p['steps']) == 1 and isinstance(p['steps'][0], str)
            and 0 < len(p['steps'][0].encode()) <= 4096
            and limits == {'max_writes':int(slot.startswith('write-')), 'max_reads':int(slot.startswith('read-'))},
            'new fixed task/permission policy differs')
    boundary = freeze.get('resource_boundary',{})
    require(boundary.get('owner_confirmed') is True and boundary.get('hard_stop_epoch') == 1791392400
        and boundary.get('provider_expiry_epoch') == 1791392400
        and boundary.get('export_reserve_seconds') == 900
        and 0 < boundary.get('development_max_seconds',0) <= 3222
        and boundary.get('prior_cumulative_seconds',0) >= 7577.8156609169965
        and boundary.get('original_cumulative_max_seconds') == 57600,
        'remaining development/lease/cumulative boundary missing')
    if check_time: require(time.time() < 1791391500, 'development generation cutoff reached')
    return binding


def scope(root, *, private_prefixes, check_time=True):
    require(root in {MAC_SOURCE, REMOTE_SOURCE}, 'new isolated deployed source root required')
    state = STATE if root == MAC_SOURCE else REMOTE_STATE
    spec, freeze = public(root,SPEC), public(root,FREEZE)
    approval = read_json(state,'owner-approval.json')
    binding = authority(spec,freeze,approval,public(root,TRANSITION),public(root,CONSENT),check_time=check_time)
    require(file_sha(root/SPEC) == freeze['spec_file_sha256'], 'actual new spec bytes differ')
    project = SourceGuard(root,freeze['source_files'],freeze['source_inventory_sha256'],project_prefixes=private_prefixes)
    def guard():
        project()
        require(file_sha(root/SPEC)==freeze['spec_file_sha256']
            and digest(public(root,FREEZE))==binding['runtime_freeze_sha256']
            and read_json(state,'owner-approval.json')==approval,
            'new approved spec/runtime/grant changed after admission')
        require(all(file_sha(root/n) == sha for n,sha in freeze['fixed_public_files'].items()), 'fixed public config drift')
        if root == MAC_SOURCE:
            require(all(file_sha(Path(n)) == sha for n,sha in freeze['frozen_observed_host_files'].items()),
                'readable frozen host file drift; opaque origins still NOT proven')
        return freeze['source_inventory_sha256']
    guard()
    return spec,freeze,approval,binding,guard
