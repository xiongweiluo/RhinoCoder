"""The actual entries' CPU preparation, also callable with --check.

No grant/state creation, model loader, GPU query, SSH or Rhino invocation.
It checks the shipped package rather than reconstructing a test-only config.
"""
import json
from pathlib import Path

from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.lora_development_runtime import configuration, active_schedule, prepare_host
from training.lora_development_authority import validate_package, verify_source


def prepare(root, package, endpoint):
    root = Path(root)
    require(endpoint in {'mac', 'gpu'}, 'explicit CPU endpoint required')
    validate_package(package)
    verify_source(root, package['source_files'])
    config = configuration(package)
    # Resolve exactly the lazy helper used by the real weight loader, without
    # invoking that loader or substituting a test configuration.
    from training.lora_development_loader import cpu_dependencies
    _, load_config, _ = cpu_dependencies()
    load_config(root / 'eval/c5/c5-engineering-config.json')
    from training.lora_development_controller import DevelopmentController
    from training.lora_development_scope import DevelopmentJournal
    from training.lora_development_gpu_entry import supervise, worker
    from training.lora_development_process import JsonPipe
    host = prepare_host(root, package)
    tokenizer, check = None, lambda: None
    if endpoint == 'mac':
        from training.lora_development_local_tokenizer import load_tokenizer, verify_environment
        tokenizer = load_tokenizer(package['assets'])
        environment = json.loads((root / 'lora-development-mac-environment.json').read_text())
        require(digest(environment) == package['endpoints']['mac']['environment_sha256'], 'CPU environment binding differs')
        def check(): verify_environment(environment)
        check(); check()  # Auditing must not alter import state on its first pass.
    return {'config': config, 'schedule': active_schedule(package), 'schemas': host['schemas'],
            'tokenizer': tokenizer, 'check_environment': check,
            'controller': DevelopmentController, 'journal': DevelopmentJournal, 'pipe': JsonPipe,
            'supervise': supervise, 'worker': worker}


def report(root, package, endpoint):
    ready = prepare(root, package, endpoint)
    ready['check_environment']()
    return {'status': 'passed', 'endpoint': endpoint, 'package_sha256': digest(package),
            'source_inventory_sha256': digest(package['source_files']),
            'configuration': ready['config'], 'pending_slots': [r['slot_id'] for r in ready['schedule']],
            'actual_entry_preparation_used': True, 'grant_or_live_state_created': False,
            'model_calls': 0, 'rhino_calls': 0, 'execution_authorized': False,
            'model_or_native_readiness_proven': False}
