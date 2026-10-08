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

from plugin.rhino_listener.c5_formal20_scope_v2 import (
    STUDY_ID, REMOTE_SOURCE, REMOTE_STATE, REMOTE_ENV, SPEC_FILE, FREEZE_FILE, authority,
)
from plugin.rhino_listener.c5_research_channel import publish_json, read_json, private_directory
from plugin.rhino_listener.c5_research_native import require, digest
from plugin.rhino_listener.c5_research_provenance import SourceGuard
from training.c5_formal20_runtime import FormalModelSession, validate_hashed_plans
from training.c5_formal20_budget_v2 import FormalBudgetV2 as FormalBudget
from training.c5_startup_transport import startup_receipt
from training.c5_modelbridge_runtime import file_sha, runtime_preflight, verify_loaded_environment
from training.c5_model_transport import strict_json, frame, LIMIT

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
    'eval/c5/rhino-resource-boundary-v7-formal20-20261007.json',
    'eval/c5/final-holdout-commitment.json',
    'eval/c5/dataset-v2-freeze-manifest.json',
    'eval/c5/historical-exclusions.json')


def public(path):
    require(path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= LIMIT, 'formal public file invalid')
    return strict_json(path.read_bytes())


def preflight():
    require(ROOT == REMOTE_SOURCE and sys.platform == 'linux', 'fixed formal Linux deployment required')
    from training.c5_execution import verify_snapshot
    registry = public(ROOT / 'eval/c5/gpu-formal-registry-20261001.json')
    manifest = ASSET / 'base-snapshot-manifest.json'
    require(file_sha(manifest) == '5b9ad4c8257ed072cfdee022e4b92303ffc849f53014dbf76d0986b3d1428cdd', 'formal base manifest drift')
    snapshot = Path(public(manifest)['snapshot_dir'])
    verified = verify_snapshot(snapshot, manifest)
    require(registry['selected_checkpoint'] == 'checkpoint-132' and digest(registry['files']) == registry['adapter_sha256']
        and all(file_sha(ADAPTER / n) == sha for n, sha in registry['files'].items()), 'formal adapter asset drift')
    environment, inventory = runtime_preflight(REMOTE_ENV)
    source = {p.relative_to(ROOT).as_posix(): file_sha(p) for folder in ('agent', 'training', 'tools', 'plugin', 'data_pipeline', 'eval')
        for p in sorted((ROOT / folder).rglob('*.py'))}
    return {**environment, 'snapshot': verified, 'adapter_sha256': registry['adapter_sha256'],
        'adapter_files': registry['files'], 'source_files': source,
        'source_inventory_sha256': digest(source), 'fixed_public_files': {n: file_sha(ROOT / n) for n in PUBLIC_FILES},
        'status': 'formal20_readonly_preflight_not_execution_authority'}, inventory, snapshot


def approved_scope():
    spec, freeze = public(ROOT / SPEC_FILE), public(ROOT / FREEZE_FILE)
    fd = private_directory(REMOTE_STATE); os.close(fd)
    approval = read_json(REMOTE_STATE, 'owner-approval.json')
    freeze_sha = authority(spec, freeze, approval)
    require(ROOT == REMOTE_SOURCE and sys.platform == 'linux' and file_sha(ROOT / SPEC_FILE) == freeze['spec_file_sha256'],
        'formal deployed spec/source differs')
    source = SourceGuard(ROOT, freeze['source_files'], freeze['source_inventory_sha256'],
        project_prefixes=('agent', 'training', 'tools', 'plugin', 'data_pipeline'))
    source()
    actual, inventory, snapshot = preflight()
    require(actual['environment_sha256'] == freeze['environment_sha256']
        and actual['source_files'] == freeze['source_files']
        and actual['fixed_public_files'] == freeze['fixed_public_files']
        and {'base': digest(actual['snapshot']), 'lora': actual['adapter_sha256']} == freeze['model_identities'],
        'formal deployed environment/assets/config differs')
    return spec, freeze, freeze_sha, source, actual, inventory, snapshot


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
    source();verify_loaded_environment(REMOTE_ENV,inventory)
    require(not torch.cuda.is_initialized(),'formal import preflight initialized CUDA')
    return {'status':'formal_readonly_loader_closure_verified_not_execution_authority',
        'environment_sha256':assets['environment_sha256'],'source_inventory_sha256':assets['source_inventory_sha256'],
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


def serve():
    os.environ['HF_HUB_OFFLINE'] = '1'; os.environ['TRANSFORMERS_OFFLINE'] = '1'; os.umask(0o077)
    spec, freeze, freeze_sha, source, assets, inventory, snapshot = approved_scope()
    publish_json(REMOTE_STATE, 'formal20.worker-started.claim.json', {'study_id': STUDY_ID,
        'runtime_freeze_sha256': freeze_sha, 'replay_allowed': False})
    budget = FormalBudget(freeze['resource_boundary'])
    output, settled, status = sys.stdout.buffer, False, 'formal_worker_failed_no_replay'
    def alarm(*_): raise TimeoutError('formal worker resource stop')
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, budget.check())
    try:
        with contextlib.redirect_stdout(sys.stderr):
            import torch
            from peft import PeftModel, prepare_model_for_kbit_training
            from transformers import AutoModelForCausalLM, BitsAndBytesConfig
            from training.c5_execution import generation, load_config, load_pinned_tokenizer
            require(torch.cuda.is_available() and torch.cuda.is_bf16_supported()
                and torch.cuda.mem_get_info()[0] >= 16 * 1024**3, 'formal CUDA/BF16/free memory unavailable')
            for line in (ROOT / 'requirements-training.txt').read_text().splitlines():
                if '==' in line and not line.startswith('#'):
                    name, version = line.split('==')
                    require(importlib.metadata.version(name).split('+')[0] == version, 'formal locked package version differs')
            tokenizer = load_pinned_tokenizer(snapshot, config=load_config())
            torch.manual_seed(20260928); torch.cuda.manual_seed_all(20260928)
            torch.backends.cuda.matmul.allow_tf32 = True
            quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16)
            base = AutoModelForCausalLM.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False,
                quantization_config=quant, dtype=torch.bfloat16, device_map={'': 0})
            base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=False)
            base.config.use_cache = False
            model = PeftModel.from_pretrained(base, ADAPTER, local_files_only=True, is_trainable=False)
            model.eval(); torch.cuda.reset_peak_memory_stats()
        def guard():
            from plugin.rhino_listener.c5_formal20_environment import verify_project_origins
            source(); verify_project_origins(ROOT, freeze['source_files']); verify_loaded_environment(REMOTE_ENV, inventory)
            require(file_sha(ROOT/SPEC_FILE)==freeze['spec_file_sha256']
                and digest(public(ROOT/FREEZE_FILE))==freeze_sha
                and read_json(REMOTE_STATE,'owner-approval.json')=={
                    'study_id':STUDY_ID,'actor':'repository_owner','approved':True,
                    'spec_sha256':digest(spec),'runtime_freeze_sha256':freeze_sha,
                    'approval_basis':'direct repository_owner approval of complete C5-6 formal20 spec and runtime freeze'},
                'formal exact spec/runtime/grant drifted')
            require(all(file_sha(ROOT/n)==sha for n,sha in freeze['fixed_public_files'].items()),
                'formal public config drifted')
        guard(); budget.check()
        loaded = {'study_id': STUDY_ID, 'environment_sha256': assets['environment_sha256'],
            'source_inventory_sha256': freeze['source_inventory_sha256'], 'model_identities': freeze['model_identities'],
            'torch_cuda': torch.version.cuda, 'gpu': torch.cuda.get_device_name(0),
            'base_dtype_cast': 'prepare_model_for_kbit_training_no_checkpoint_hooks',
            'base_route': 'same PEFT-wrapped base with disable_adapter context', 'default_route_changed': False}
        publish_json(REMOTE_STATE, 'loaded-runtime.json', loaded)
        ready=startup_receipt(STUDY_ID,freeze_sha,freeze['source_inventory_sha256'],
            assets['environment_sha256'],freeze['model_identities'])
        publish_json(REMOTE_STATE,'worker-startup-ready.json',ready)
        output.write(frame(ready));output.flush()
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
        publish_json(REMOTE_STATE, 'bootstrap.json', bootstrap)
        require(sum(p['max_steps'] for p in plans.values())<=spec['max_model_requests'],
            'formal hashed plan exceeds fixed strata budget')
        stages = [0]
        def generate(prompt, stage):
            guard(); budget.check()
            require(stages[0] < spec['max_generation_stages'], 'formal stage ceiling reached before generation')
            stages[0] += 1
            with contextlib.redirect_stdout(sys.stderr): return generation(model, tokenizer, prompt, stage)
        session = FormalModelSession(freeze_sha, plans, REMOTE_STATE, tokenizer, generate,
            lambda route: model.disable_adapter() if route == 'base' else contextlib.nullcontext(),
            freeze['model_identities'], guard, budget.check)
        ready_reply={'status':'formal_worker_ready','request_sha256':digest(bootstrap),
            'runtime_freeze_sha256':freeze_sha,'model_identities':freeze['model_identities'],'startup_receipt':ready}
        publish_json(REMOTE_STATE,'worker-bootstrap-response.json',ready_reply)
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
                        'key': sent['key'], 'records': step_evidence(REMOTE_STATE, sent['key'])}
                    output.write(frame(value)); output.flush(); continue
                require(set(sent) == {'kind', 'study_id', 'runtime_freeze_sha256'}, 'formal stop fields differ')
                status = 'formal_worker_stopped_no_replay'
                summary = {'requests': count, 'generation_stages': stages[0],
                    'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                    'peak_reserved_bytes': torch.cuda.max_memory_reserved(), 'attempted_keys': attempted}
                publish_json(REMOTE_STATE, 'worker-summary.json', summary)
                resource = budget.settle(REMOTE_STATE, status); settled = True
                # Commit raw inventory while the worker is still present. Keys/weights are excluded.
                names = ['bootstrap.json', 'loaded-runtime.json', 'worker-summary.json', 'resource-settlement.json',
                    'formal20.worker-started.claim.json','worker-startup-ready.json','worker-bootstrap-response.json',
                    'owner-approval.json']
                raw_records = {n: read_json(REMOTE_STATE, n) for n in names}
                files = {p.name: file_sha(p) for p in sorted(REMOTE_STATE.glob('*.json'))}
                output.write(frame({'status': 'formal_worker_stopped', 'request_sha256': digest(sent),
                    'runtime_freeze_sha256': freeze_sha, 'raw_records': raw_records, 'file_sha256': files,
                    'asset_environment_preflight': assets, 'resource': resource})); output.flush()
                break
            require(not session.blocked and count < min(spec['max_model_requests'],sum(p['max_steps'] for p in plans.values())), 'formal worker blocked/exhausted')
            budget.check(); guard()
            key = digest({'slot': sent.get('slot_id'), 'step': sent.get('step_index'), 'freeze': freeze_sha})
            publish_json(REMOTE_STATE, key + '-request.json', sent)
            attempted.append(key); count += 1
            value = session.infer(sent)
            output.write(frame(value)); output.flush()
            # An operational model failure allows evidence export and stop, never another infer.
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if not settled: budget.settle(REMOTE_STATE, status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'import-preflight', 'serve'))
    args = parser.parse_args()
    if args.mode == 'preflight': print(frame(preflight()[0]).decode(), end='')
    elif args.mode=='import-preflight':print(frame(import_preflight()).decode(),end='')
    else: serve()


if __name__ == '__main__': main()
