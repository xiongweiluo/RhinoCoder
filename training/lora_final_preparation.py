"""Inert final public specification and actual shared-entry CPU preparation."""
import json
from pathlib import Path

from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.lora_development_admission import source_guard
from plugin.rhino_listener.lora_development_runtime import common_configuration
from training.lora_comparison_plan import FINAL_STUDY, proposal, validate_compiled

CHOICES_SHA = '807fe4847d2077c888012d106bfbd2cc341d6a18214cc75389af5ad3dd138377'


def validate_spec(spec):
    require(spec['kind'] == FINAL_STUDY and spec['comparison_plan'] == proposal()
            and spec['limits'] == common_configuration(proposal())
            and spec['choices_sha256'] == CHOICES_SHA
            and digest(spec['choices']) == CHOICES_SHA
            and spec['execution_authorized'] is False and 'compiled' not in spec,
            'fixed public final specification required')
    from training.lora_development_loader import POLICY
    require(spec['loader_policy'] == POLICY and set(spec['model_identities']) == {'base', 'current_lora'},
            'fixed two-model loader required')
    require(spec['model_identities'] == {
        'base': digest({'base': spec['assets']['base_files'], 'loader_policy': POLICY}),
        'current_lora': digest({'base': spec['assets']['base_files'], 'adapter': spec['assets']['adapter_files'], 'loader_policy': POLICY})},
        'model asset identity differs')
    return spec


def prepare(root, spec, endpoint):
    """Same imports/tokenizer/config as live path, but no private inputs or grant."""
    validate_spec(spec); source_guard(root, spec['source_files'])
    require(endpoint in {'mac', 'gpu'}, 'explicit CPU endpoint required')
    from training.lora_development_loader import cpu_dependencies
    _, load_config, _ = cpu_dependencies()
    load_config(Path(root)/'eval/c5/c5-engineering-config.json')
    from training.lora_development_controller import DevelopmentController
    from training.lora_development_scope import DevelopmentJournal
    from training.lora_development_process import JsonPipe
    from training.lora_development_gpu_entry import supervise, worker
    from training.lora_common_chain import CommonChain
    tokenizer, check = None, lambda: None
    if endpoint == 'mac':
        from training.lora_development_local_tokenizer import load_tokenizer, verify_environment
        tokenizer = load_tokenizer(spec['assets'])
        environment = json.loads((Path(root)/'lora-development-mac-environment.json').read_text())
        require(digest(environment) == spec['endpoints']['mac']['environment_sha256'], 'CPU environment differs')
        def check(): verify_environment(environment)
        check(); check()
    return {'config': spec['limits'], 'schemas': json.loads((Path(root)/'eval/c5/rhino-runtime-schema-v1.json').read_text())['core_parameters'],
        'tokenizer': tokenizer, 'check_environment': check, 'controller': DevelopmentController,
        'journal': DevelopmentJournal, 'pipe': JsonPipe, 'supervise': supervise, 'worker': worker,
        'contract_class': CommonChain}


def runtime_ready(root, package, endpoint):
    spec = {k:v for k,v in package.items() if k != 'compiled'}
    ready = prepare(root, spec, endpoint)
    validate_compiled(package['comparison_plan'], package['compiled'])
    ready['schedule'] = package['compiled']['views']['schedule']
    if endpoint == 'mac':
        from plugin.rhino_listener.c5_research_channel import read_json
        from training.lora_comparison_plan import compile_cases
        cases = read_json(Path(package['endpoints']['mac']['state_root']), 'scorer-cases.json')
        require(compile_cases(package['comparison_plan'], cases) == package['compiled'], 'sealed scorer differs')
        ready['cases'] = cases
    return ready


def report(root, spec, endpoint):
    ready = prepare(root, spec, endpoint); ready['check_environment']()
    return {'status':'passed', 'endpoint':endpoint, 'spec_sha256':digest(spec),
        'source_inventory_sha256':digest(spec['source_files']), 'configuration':ready['config'],
        'actual_entry_preparation_used':True, 'private_inputs_read':False,
        'grant_or_live_state_created':False, 'model_calls':0, 'rhino_calls':0,
        'execution_authorized':False, 'model_or_native_readiness_proven':False}
