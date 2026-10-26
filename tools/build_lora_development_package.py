#!/usr/bin/env python3
"""Build a public, inert exact development package. Never creates a grant.

No SSH, deployment, private data, model imports, training or Rhino effects.
Execution readiness here means prepared bytes; authority is a separate exact
owner record checked by every live entry. Final tests remain excluded.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def build(root=ROOT):
    from plugin.rhino_listener.c5_research_native import digest
    from training.lora_development_authority import validate_package
    from training.lora_development_loader import POLICY
    from training.lora_development_scope import field_views
    record = root / 'eval/lora-development'
    plan = json.loads((record / 'proposed-development-plan-r2-20261026.json').read_text())
    prior = json.loads((record / 'development-package-20261026.json').read_text())
    prior_review = json.loads((record / 'execution-review-20261026.json').read_text())
    model = json.loads((record / 'readonly-resources-20261026.json').read_text())['model_assets']
    gpu = json.loads((record / 'gpu-environment-20261026.json').read_text())
    mac = json.loads((record / 'mac-environment-20261026.json').read_text())
    # Public project source, not old private run packages, logs or datasets.
    names = {p.relative_to(root).as_posix() for folder in ('training', 'plugin', 'agent')
             for p in (root / folder).rglob('*.py') if '__pycache__' not in p.parts}
    names |= {p.relative_to(root).as_posix() for p in (root / 'tools').glob('*lora_development*.py')}
    names |= {'eval/c5/c5-engineering-config.json', 'eval/c5/rhino-runtime-schema-v1.json'}
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(names)}
    views = field_views(plan)
    assets = {'snapshot_dir': '/data/hf-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots/' + model['base_revision'],
        'adapter_root': '/data/c5-runs-20261001/formal/checkpoint-132',
        'base_files': model['base_files'], 'adapter_files': model['adapter_files'],
        'local_tokenizer_dir': '/Users/xiongweiluo/RhinoCoder/data/training/c5/modelbridge-tokenizer/' + model['base_revision'],
        'tokenizer_files': {n: model['base_files'][n] for n in ('config.json', 'generation_config.json', 'merges.txt',
                                                            'tokenizer.json', 'tokenizer_config.json', 'vocab.json')}}
    value = {'schema_version': 2, 'study_id': plan['study_id'], 'development_plan': plan, 'source_files': files,
        'model_path_bindings': json.loads((record / 'model-path-bindings-20261026.json').read_text()),
        'continuation': {'prior_package_sha256': digest(prior), 'prior_review': prior_review,
            'prior_review_sha256': digest(prior_review), 'prior_endpoints': prior['endpoints'],
            'charged_prior_seconds': 180, 'cumulative_seconds_limit': 7200,
            'prior_load_attempts': 2, 'cumulative_load_attempts_limit': 3},
        'model_identities': {'base': digest({'base': assets['base_files'], 'loader_policy': POLICY}),
            'current_lora': digest({'base': assets['base_files'], 'adapter': assets['adapter_files'], 'loader_policy': POLICY})},
        'assets': assets, 'loader_policy': POLICY,
        'gpu_hardware': {'name': 'NVIDIA GeForce RTX 3090', 'memory_mib': 24576,
            'driver_version': '550.107.02', 'uuid': 'GPU-0e00f0ad-fa5a-eed9-6eee-5877984e02f9'},
        'native_scope': {'schedule': views['schedule'], 'native': views['native']},
        'endpoints': {
            'mac': {'source_root': '/Users/xiongweiluo/RhinoCoder/data/lora-development-20261026-r2/source',
                'state_root': '/Users/xiongweiluo/RhinoCoder/data/lora-development-20261026-r2/state-lora-development',
                'python': '/opt/anaconda3/bin/python3.13', 'environment_sha256': digest(mac)},
            'gpu': {'source_root': '/data/lora-development-20261026-r2/source',
                'state_root': '/data/lora-development-20261026-r2/state-lora-development',
                'python': gpu['python_path'], 'environment_sha256': digest(gpu)}},
        'limits': plan['limits'], 'lease_end_epoch': int(datetime.fromisoformat('2026-10-30T20:00:00+01:00').timestamp()),
        'resource_policy': {'lease_paid': True, 'additional_cost_ceiling': 0, 'new_paid_service_or_renewal': False,
                            'historical_budget_reuse': False},
        'host_policy': {'only_new_local_documents': True, 'model_writes': 0, 'existing_project_content_access': False,
            'fixture_documents_max': 32, 'auxiliary_documents_max': 0, 'close_after_use': True,
            'legacy_whole_host_byte_closure_claim': False},
        'stop_policy': {'target': 'only_new_direct_child_pinned_by_pidfd', 'natural_exit_wait_seconds': 5,
            'sigterm_max': 1, 'sigterm_wait_seconds': 10, 'sigkill_max': 1, 'sigkill_wait_seconds': 10,
            'unknown_exit_blocks_recovery': True},
        'evidence_policy': {'old_private_materials': False, 'new_public_development_raw_outputs': True,
            'private_owner_controlled_storage': True, 'public_output': 'sanitized_statistics_hashes_and_audit_only'},
        'historical_family_overlap': {'status': 'unknown_disclosed_public_development_only', 'owner_summary_sha256': None},
        'execution_ready': True}
    validate_package(value)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = build()
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    from plugin.rhino_listener.c5_research_native import digest
    print(json.dumps({'package_sha256': digest(value), 'source_files': len(value['source_files']),
        'execution_authorized': False, 'phase_one_complete': False}))
