"""New fixed development authority, Python 3.9; no effects on import."""
from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path

from .c5_host_assurance_session_d import DEV_D_ID, validate_study_binding
from .c5_research_channel import read_json
from .c5_research_native import digest, require
from .c5_research_provenance import SourceGuard

ID = DEV_D_ID
MAC_SOURCE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-source-20261007-D')
STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-state-20261007-D')
REMOTE_SOURCE = Path('/data/RhinoCoder-c5-hostassurance-dev-D')
REMOTE_STATE = Path('/data/c5-hostassurance-dev-state-20261007-D')
ENV = Path('/data/conda-envs/rhinocoder')
SOCKET = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/ssh-22159.control')
PIN = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/known-hosts-22159')
PIN_SHA = 'ae41a99e39f76b1be352f0098439b126fe5b8465c358b8dabbb7a71e53d2d1a9'
SPEC = 'eval/c5/hostassurance-development-spec-20261007-d.json'
FREEZE = 'eval/c5/hostassurance-development-runtime-freeze-20261007-d.json'
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
    lifecycle = {'protocol':'c5-native-completion-timing-v1','native_ack_seconds':120,'settle_seconds':60,
        'timer_before_client_guard':True,'full_decode_validation_in_window':True,
        'post_publication_service_record_required':True,'settle_entry_and_completion_checked':True,
        'source_checks_retained_without_cache':True,'failure_unknown_no_retry':True,
        'logical_deadline_not_CLR_preemption':True}
    require(digest(spec.get('lifecycle_protocol')) == digest(lifecycle)
        and digest(freeze.get('lifecycle_protocol')) == digest(lifecycle), 'D complete lifecycle contract required')
    fixed = {'mac_source_root':str(MAC_SOURCE), 'mac_state_root':str(STATE),
        'remote_source_root':str(REMOTE_SOURCE), 'remote_state_root':str(REMOTE_STATE),
        'environment_root':str(ENV), 'ssh_socket':str(SOCKET), 'ssh_host':'175.155.64.171',
        'ssh_port':22159, 'ssh_known_hosts_file':str(PIN), 'ssh_known_hosts_file_sha256':PIN_SHA,
        'base_revision':'c03e6d358207e414f1eca0bb1891e29f1db0e242', 'adapter_sha256':ADAPTER,
        'contract_id':'qwen25-v4-selector-v3-json-invoker-c5-v1'}
    require(all(spec.get(k) == v for k,v in fixed.items()), 'new fixed development roots/transport/models differ')
    protocol=spec.get('entry_return_protocol',{})
    expected_wrapper='#! python 3\nimport runpy\nscope = runpy.run_path("'+str(MAC_SOURCE)+'/tools/c5_rhino_hostassurance_dev_d.py", run_name="__main__")\nscope["ENTRY_RETURN_BARRIER"].release_after_entry_return()\n'
    require(protocol=={'wrapper_code':expected_wrapper,'release_called_after_run_path_returns':True,
        'first_non_command_idle_seals_once':True,'seal_callback_dispatches_no_task':True,
        'no_main_module_whitelist_or_ignore':True,'baseline_failure_cannot_retry':True}
        and all(protocol[k] is True for k in protocol if k!='wrapper_code'),
        'exact post-runpy-return release/first-idle protocol required')
    require(spec.get('startup_protocol')=={'protocol':'c5-modelbridge-startup-ready-v1',
        'ready_after_actual_model_load_and_source_environment_checks':True,
        'ready_before_any_private_or_development_task_transmission':True,
        'ready_before_any_model_fixture_open':True,'ready_consumption_counts_zero':True,
        'wrong_or_unknown_ready_blocks_without_reconnect':True,'request_timer_starts_after_ready':True,
        'byte_checks_retained_no_cache_or_weaker_comparison':True}
        and all(v is True for k,v in spec['startup_protocol'].items() if k!='protocol')
        and type(spec.get('startup_timeout_seconds')) is int and spec['startup_timeout_seconds']==180
        and type(spec.get('per_request_timeout_seconds')) is int and spec['per_request_timeout_seconds']==180,
        'new separate loaded readiness and request time budgets required')
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
    require(all(type(spec.get(k)) is int for k in ('generation_requests_max','generation_calls_max',
        'holdout_calls','training_calls','max_sequence_tokens','selector_output_tokens','invocation_output_tokens'))
        and spec['max_sequence_tokens']==2048 and spec['selector_output_tokens']==128
        and spec['invocation_output_tokens']==512, 'unchanged integer D model/output budgets required')
    for slot in order:
        p, limits = spec['task_plans'][slot], spec['slot_policies'][slot]
        require(set(p) == {'route','steps'} and p['route'] == slot.rsplit('-',1)[1]
            and isinstance(p['steps'], list) and len(p['steps']) == 1 and isinstance(p['steps'][0], str)
            and 0 < len(p['steps'][0].encode()) <= 4096
            and limits == {'max_writes':int(slot.startswith('write-')), 'max_reads':int(slot.startswith('read-'))},
            'new fixed task/permission policy differs')
        require(all(type(v) is int for v in limits.values()), 'exact integer D tool allowance required')
    boundary = freeze.get('resource_boundary',{})
    require(all(type(boundary.get(k)) is int for k in ('hard_stop_epoch','provider_expiry_epoch',
        'export_reserve_seconds','development_max_seconds','original_cumulative_max_seconds'))
        and type(boundary.get('prior_cumulative_seconds')) in (int,float)
        and math.isfinite(boundary['prior_cumulative_seconds']), 'typed finite D resource boundary required')
    require(boundary.get('owner_confirmed') is True and boundary.get('hard_stop_epoch') == 1791489600
        and boundary.get('provider_expiry_epoch') == 1791489600
        and boundary.get('export_reserve_seconds') == 900
        and 0 < boundary.get('development_max_seconds',0) <= 2470
        and boundary.get('prior_cumulative_seconds',0) >= 8329.012193825008
        and boundary.get('original_cumulative_max_seconds') == 57600,
        'remaining development/lease/cumulative boundary missing')
    require(boundary['prior_cumulative_seconds']+boundary['development_max_seconds']<=57600,
            'D cannot exceed original cumulative GPU allocation')
    if check_time: require(time.time() < 1791488700, 'development generation cutoff reached')
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
