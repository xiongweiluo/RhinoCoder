#!/usr/bin/env python3
"""Fixed formal20 worker. Preflight is read-only; serve needs exact new grant.

No training, final80 entry, arbitrary task file, checkpoint selection or
automatic restart. Actual zero-task loading/readiness precedes hash plans.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from plugin.rhino_listener.c5_formal_reuse_scope import (
    STUDY_ID, REMOTE_SOURCE, REMOTE_STATE, REMOTE_ENV, SPEC_FILE, FREEZE_FILE, RESOURCE_FILE, authority,
)
from plugin.rhino_listener.c5_research_channel import publish_json, read_json, private_directory
from plugin.rhino_listener.c5_research_native import require, digest
from plugin.rhino_listener.c5_formal_reuse_source_guard import SourceGuard
from training.c5_formal_reuse_runtime import FormalModelSession, validate_hashed_plans
from training.c5_formal_reuse_budget import FormalBudgetV2 as FormalBudget
from training.c5_startup_transport import startup_receipt
from training.c5_modelbridge_runtime import file_sha
from training.c5_followup_compatible_runtime import verify_loaded_environment
from training.c5_formal_reuse_model_wire import strict_json, frame, LIMIT

ASSET = Path('/data/RhinoCoder-c5')
ADAPTER = Path('/data/c5-runs-20261001/formal/checkpoint-132')
PUBLIC_FILES = ('eval/c5/rhino-runtime-schema-v1.json', 'eval/c5/gpu-formal-registry-20261001.json',
    'eval/c5/c5-engineering-config.json', 'requirements-training.txt', 'requirements.txt',
    'eval/c5/formal20-observation-capacity-proposal-20261007.json',
    'eval/c5/formal20-capacity-owner-acceptance-20261007.json',
    'eval/c5/host-assurance-transition-spec-v2-20261006.json',
    'eval/c5/host-assurance-transition-owner-approval-v2-20261006.json',
    'eval/c5/hostassurance-development-independent-audit-20261007-d.json',
    'eval/c5/rhino-formal20-public-commitment-v1.json',
    RESOURCE_FILE,
    'eval/c5/final-holdout-commitment.json',
    'eval/c5/dataset-v2-freeze-manifest.json',
    'eval/c5/historical-exclusions.json')


def public(path):
    require(path.resolve()==path and path.is_file() and 0<path.stat().st_size<=2097152,
        'formal_reuse_bounded_public_file')
    from plugin.rhino_listener.c5_reuse_field_scope import strict
    return strict(path.read_bytes())


def preflight():
    require(ROOT==REMOTE_SOURCE and sys.platform=='linux','formal_reuse_fixed_linux_deployment')
    freeze=public(ROOT/FREEZE_FILE)
    from training.c5_followup_gpu_loader import preflight as verify
    from training.c5_execution import verify_snapshot
    source=SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],
        project_prefixes=('agent','training','tools','plugin','data_pipeline'))
    inventory=verify(freeze,freeze['field_plan'],source)
    snapshot=Path(freeze['model_assets']['snapshot_dir'])
    verified=verify_snapshot(snapshot,Path('/data/RhinoCoder-c5/base-snapshot-manifest.json'))
    assets={'environment':freeze['environment'],'environment_sha256':freeze['environment_sha256'],
        'snapshot':verified,'adapter_sha256':freeze['model_identities']['lora'],
        'adapter_files':freeze['model_assets']['adapter_files'],'source_files':freeze['source_files'],
        'source_inventory_sha256':freeze['source_inventory_sha256'],
        'fixed_public_files':{n:file_sha(ROOT/n) for n in freeze['fixed_public_files']}}
    require(assets['fixed_public_files']==freeze['fixed_public_files'],'formal_reuse_public_deployment_drift')
    return assets,inventory,snapshot

def approved_scope():
    spec,freeze=public(ROOT/SPEC_FILE),public(ROOT/FREEZE_FILE)
    approval=read_json(REMOTE_STATE,'owner-approval.json')
    freeze_sha=authority(spec,freeze,approval,check_time=False)
    require(ROOT==REMOTE_SOURCE and sys.platform=='linux' and file_sha(ROOT/SPEC_FILE)==freeze['spec_file_sha256'],
        'formal_reuse_actual_gpu_source')
    project=SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],
        project_prefixes=('agent','training','tools','plugin','data_pipeline'))
    from training.c5_formal_reuse_admission import history_guard
    historical=history_guard('gpu',freeze['history'])
    def source():
        historical();project()
        require(public(ROOT/FREEZE_FILE)==freeze and public(ROOT/SPEC_FILE)==spec
            and read_json(REMOTE_STATE,'owner-approval.json')==approval,'formal_reuse_gpu_material_drift')
        return freeze['source_inventory_sha256']
    from training.c5_formal_reuse_revision import verify_endpoint
    lineage=verify_endpoint('gpu',freeze)
    original=source
    def guarded():lineage();return original()
    source=guarded
    source();actual,inventory,snapshot=preflight()
    return spec,freeze,freeze_sha,source,actual,inventory,snapshot


def import_preflight():
    """Read-only actual loader closure; no model construction/CUDA init."""
    assets,inventory,_=preflight()
    source=SourceGuard(ROOT,assets['source_files'],assets['source_inventory_sha256'],
        project_prefixes=('agent','training','tools','plugin','data_pipeline'))
    import torch
    from peft import PeftModel,prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM,BitsAndBytesConfig
    from training.c5_execution import generation,load_config,load_pinned_tokenizer
    require(all(v is not None for v in (PeftModel,prepare_model_for_kbit_training,AutoModelForCausalLM,
        BitsAndBytesConfig,generation,load_config,load_pinned_tokenizer)), 'formal loader imports missing')
    source();verify_loaded_environment(Path('/data/conda-envs/rhinocoder'),inventory)
    require(not torch.cuda.is_initialized(),'formal import preflight initialized CUDA')
    return {'status':'formal_readonly_loader_closure_verified_not_execution_authority',
        'environment_sha256':assets['environment_sha256'],'source_inventory_sha256':assets['source_inventory_sha256'],
        'source_code_inventory_sha256':digest({n:h for n,h in assets['source_files'].items() if n.endswith('.py')}),
        'epoch':__import__('time').time(),
        'torch_version':torch.__version__,'cuda_initialized':False,'model_loaded':False,
        'holdout_rows_read':0,'generation_calls':0}


def step_evidence(state, key):
    """All raw files of an already attempted step; no generation or retry."""
    require(isinstance(key, str) and len(key) == 64 and all(c in '0123456789abcdef' for c in key), 'formal evidence key invalid')
    claim = 'generation-' + key + '.claim.json'
    read_json(state, claim)
    names = [claim, key + '-request.json'] + sorted(p.name for p in state.glob(key + '-*.json')
        if p.name != key + '-request.json')
    require(len(names) == len(set(names)) and 4 <= len(names) <= 10, 'formal raw step population invalid')
    return {name: read_json(state, name) for name in names}


def capture_parent_grant(state,spec,freeze,guard):
    """Snapshot the already validated parent grant for this attempt's export.

    This does not create authority: approved_scope() and the pre-load permit
    gate precede the child, and exact parent bytes are checked before/after.
    """
    from plugin.rhino_listener.c5_formal_reuse_scope import expected_grant
    guard();value=read_json(REMOTE_STATE,'owner-approval.json')
    require(value==expected_grant(spec,freeze),'formal_reuse_original_parent_grant_required')
    publish_json(state,'owner-approval.json',value)
    guard();require(read_json(REMOTE_STATE,'owner-approval.json')==value,
        'formal_reuse_parent_grant_changed_during_capture')


def serve_child(progress_fd,attempt):
    from training.c5_formal_reuse_admission import attempt_state
    from training.c5_formal_reuse_supervisor import progress
    state=attempt_state('gpu',attempt)
    os.environ['HF_HUB_OFFLINE'] = '1'; os.environ['TRANSFORMERS_OFFLINE'] = '1'; os.umask(0o077)
    spec, freeze, freeze_sha, source, assets, inventory, snapshot = approved_scope()
    capture_parent_grant(state,spec,freeze,source)
    publish_json(state, 'formal20.worker-started.claim.json', {'study_id': STUDY_ID,
        'runtime_freeze_sha256': freeze_sha, 'replay_allowed': False})
    permit=read_json(state,'load-permit.json')
    now,mono=__import__('time').time(),__import__('time').monotonic()
    budget=FormalBudget(freeze['resource_boundary'],start={'wall':permit['first_load_epoch'],
        'mono':mono-(now-permit['first_load_epoch'])})
    output, settled, status = sys.stdout.buffer, False, 'formal_worker_failed_no_replay'
    def alarm(*_): raise TimeoutError('formal worker resource stop')
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, budget.check())
    try:
        from training.c5_followup_gpu_loader import load
        tokenizer,original_generate,route_context,check=load(ROOT,inventory,source,budget.check,
            runtime=freeze,plan=freeze['field_plan'])
        import torch
        def guard():check()
        guard();budget.check()
        loaded = {'study_id': STUDY_ID, 'environment_sha256': assets['environment_sha256'],
            'source_inventory_sha256': freeze['source_inventory_sha256'], 'model_identities': freeze['model_identities'],
            'torch_cuda': torch.version.cuda, 'gpu': torch.cuda.get_device_name(0),
            'base_dtype_cast': 'prepare_model_for_kbit_training_no_checkpoint_hooks',
            'base_route': 'same PEFT-wrapped base with disable_adapter context', 'default_route_changed': False}
        publish_json(state, 'loaded-runtime.json', loaded)
        ready=startup_receipt(STUDY_ID,freeze_sha,freeze['source_inventory_sha256'],
            assets['environment_sha256'],freeze['model_identities'])
        publish_json(state,'worker-startup-ready.json',ready)
        output.write(frame(ready));output.flush();progress(progress_fd,b'L')
        # No task/hash plan/private body was read before actual load + ready.
        first=sys.stdin.buffer.readline(LIMIT+1)
        require(first.endswith(b'\n') and len(first)<=LIMIT,'complete one-time bootstrap required')
        bootstrap=strict_json(first)
        if bootstrap.get('kind')=='formal_abort_before_bootstrap':
            require(bootstrap=={'kind':'formal_abort_before_bootstrap','study_id':STUDY_ID,
                'runtime_freeze_sha256':freeze_sha},'exact zero-stage abort required')
            status='formal_prebootstrap_aborted_zero_generation'
            output.write(frame({'status':status,'request_sha256':digest(bootstrap),
                'runtime_freeze_sha256':freeze_sha,'generation_requests':0}));output.flush()
            return
        require(set(bootstrap) == {'kind', 'study_id', 'runtime_freeze_sha256', 'started', 'plans'}
            and bootstrap['kind'] == 'formal_bootstrap' and bootstrap['study_id'] == STUDY_ID
            and bootstrap['runtime_freeze_sha256'] == freeze_sha and bootstrap['started'] == {
                'study_id': STUDY_ID, 'spec_sha256': digest(spec), 'runtime_freeze_sha256': freeze_sha,
                'public_commitment_sha256': spec['public_commitment_sha256'], 'replay_allowed': False},
            'formal Mac started/bootstrap scope differs')
        plans = validate_hashed_plans(bootstrap['plans'])
        publish_json(state, 'bootstrap.json', bootstrap);progress(progress_fd,b'B')
        require(sum(p['max_steps'] for p in plans.values())<=spec['max_model_requests'],
            'formal hashed plan exceeds fixed strata budget')
        stages = [0]
        def generate(prompt, stage):
            guard(); budget.check()
            require(stages[0] < spec['max_generation_stages'], 'formal stage ceiling reached before generation')
            stages[0] += 1
            progress(progress_fd,b'S')
            value=original_generate(prompt,stage)
            progress(progress_fd,b'E');return value
        session = FormalModelSession(freeze_sha, plans, state, tokenizer, generate,
            route_context,
            freeze['model_identities'], guard, budget.check)
        ready_reply={'status':'formal_worker_ready','request_sha256':digest(bootstrap),
            'runtime_freeze_sha256':freeze_sha,'model_identities':freeze['model_identities'],'startup_receipt':ready}
        publish_json(state,'worker-bootstrap-response.json',ready_reply)
        output.write(frame(ready_reply));output.flush()
        attempted, count = [], 0
        while True:
            raw = sys.stdin.buffer.readline(LIMIT + 1)
            require(raw and raw.endswith(b'\n') and len(raw) <= LIMIT, 'formal EOF/frame uncertainty')
            sent = strict_json(raw)
            if sent.get('kind') in {'formal_export_step', 'formal_stop'}:
                require(sent.get('study_id') == STUDY_ID and sent.get('runtime_freeze_sha256') == freeze_sha,
                    'formal control identity differs')
                guard()
                if sent['kind'] == 'formal_export_step':
                    require(set(sent) == {'kind', 'study_id', 'runtime_freeze_sha256', 'key'} and sent['key'] in attempted,
                        'formal export outside attempted steps')
                    value = {'status': 'formal_raw_step_evidence', 'request_sha256': digest(sent),
                        'key': sent['key'], 'records': step_evidence(state, sent['key'])}
                    output.write(frame(value)); output.flush(); continue
                require(set(sent) == {'kind', 'study_id', 'runtime_freeze_sha256'}, 'formal stop fields differ')
                status = 'formal_worker_stopped_no_replay'
                summary = {'requests': count, 'generation_stages': stages[0],
                    'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                    'peak_reserved_bytes': torch.cuda.max_memory_reserved(), 'attempted_keys': attempted}
                publish_json(state, 'worker-summary.json', summary)
                resource = budget.settle(state, status); settled = True
                # Commit raw inventory while the worker is still present. Keys/weights are excluded.
                names = ['bootstrap.json', 'loaded-runtime.json', 'worker-summary.json', 'resource-settlement.json',
                    'formal20.worker-started.claim.json','worker-startup-ready.json','worker-bootstrap-response.json',
                    'owner-approval.json']
                raw_records = {n: read_json(state, n) for n in names}
                export_names=set(raw_records)
                for key in attempted:export_names.update(step_evidence(state,key))
                files={n:file_sha(state/n) for n in sorted(export_names)}
                output.write(frame({'status': 'formal_worker_stopped', 'request_sha256': digest(sent),
                    'runtime_freeze_sha256': freeze_sha, 'raw_records': raw_records, 'file_sha256': files,
                    'asset_environment_preflight': assets, 'resource': resource})); output.flush()
                break
            require(not session.blocked and count < min(spec['max_model_requests'],sum(p['max_steps'] for p in plans.values())), 'formal worker blocked/exhausted')
            budget.check(); guard()
            key = digest({'slot': sent.get('slot_id'), 'step': sent.get('step_index'), 'freeze': freeze_sha})
            publish_json(state, key + '-request.json', sent)
            attempted.append(key); count += 1
            progress(progress_fd,b'R')
            value = session.infer(sent)
            progress(progress_fd,b'D')
            output.write(frame(value)); output.flush()
            # An operational model failure allows evidence export and stop, never another infer.
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if not settled: budget.settle(state, status)


def serve(attempt):
    from training.c5_formal_reuse_admission import attempt_state
    from training.c5_formal_reuse_supervisor import supervise
    spec,freeze,_,guard,_,_,_=approved_scope()
    supervise(attempt_state('gpu',attempt),spec,freeze,attempt,guard,
        lambda fd:serve_child(fd,attempt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'import-preflight', 'serve', 'stop', 'export-supervisor'))
    parser.add_argument('--attempt',type=int,choices=(1,2,3),default=1)
    args = parser.parse_args()
    if args.mode == 'preflight': print(frame(preflight()[0]).decode(), end='')
    elif args.mode=='import-preflight':print(frame(import_preflight()).decode(),end='')
    elif args.mode=='serve':serve(args.attempt)
    else:
        from training.c5_formal_reuse_supervisor import independent_stop,export_supervisor
        from training.c5_formal_reuse_admission import attempt_state
        _,freeze,_,guard,_,_,_=approved_scope()
        state=attempt_state('gpu',args.attempt)
        result=independent_stop(state,guard) if args.mode=='stop' else export_supervisor(state,freeze,guard)
        print(frame(result).decode(),end='')

if __name__ == '__main__': main()
