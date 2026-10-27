#!/usr/bin/env python3
"""Freeze public final-study code/specification only; no cases or grant."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def build(root=ROOT):
    from tools.build_lora_development_package import source_manifest
    from training.lora_comparison_plan import proposal
    from plugin.rhino_listener.lora_development_runtime import common_configuration
    from training.lora_final_preparation import validate_spec
    from plugin.rhino_listener.c5_research_native import digest
    record = root/'eval/lora-development'
    previous = json.loads((record/'development-package-recovery-20261026.json').read_text())
    preparation = json.loads((record/'final-comparison-preparation-20261027.json').read_text())
    choices = {k:preparation[k] for k in preparation['phase_one_completion']['choices_fields']}
    value = {key: previous[key] for key in ('model_path_bindings', 'model_identities', 'assets', 'loader_policy',
        'gpu_hardware', 'lease_end_epoch', 'stop_policy')}
    plan = proposal()
    value.update(schema_version=1, kind=plan['study_id'], study_id=plan['study_id'], comparison_plan=plan,
        choices=choices, choices_sha256=digest(choices), limits=common_configuration(plan), execution_authorized=False,
        resource_policy={'lease_paid':True, 'new_paid_service_or_renewal':False, 'actual_cost_reporting':True},
        host_policy={'only_new_local_documents':True, 'fixture_documents_max':80,
                     'state_contract':'controlled_snapshot_v1', 'existing_project_content_access':False,
                     'external_modify_restore_detection':False, 'legacy_whole_host_byte_closure_claim':False},
        entrypoints={'mac':'tools/run_lora_final_mac.py', 'gpu':'tools/run_lora_final_gpu.py',
                     'rhino':'tools/run_lora_final_rhino.py'},
        endpoints=json.loads(json.dumps(previous['endpoints'])))
    original = json.loads((root/'eval/c5/final-holdout-commitment.json').read_text())
    historical = json.loads((root/'eval/c5/historical-exclusions.json').read_text())
    value['exclusion_reference'] = {
        'original80_merkle_root': original['fingerprints']['family_merkle_root_sha256'],
        'historical_numeric_hashes': historical['all_historical_numeric_text_hashes'],
        'minimum_counts': {'training_validation_development':440,'original20':20,'original80':80,
                          'a5_p2':1,'phase1_eight':8,'v1_v2_and_native_probes':1,'other_exposed_and_derivatives':1}}
    for endpoint, prefix in [('mac','/Users/xiongweiluo/.rhinocoder-final/comparison-20261027'),
                             ('gpu','/data/lora-final-comparison-20261027')]:
        value['endpoints'][endpoint].update(source_root=prefix+'/source', state_root=prefix+'/state')
    files = source_manifest(root)
    names = [p.relative_to(root).as_posix() for p in (root/'tools').glob('*lora_final*.py')]
    names += ['tools/c5_rhino_formal20_owner_exclusion.py', 'tools/build_lora_development_package.py', 'tools/run_lora_common_probe_rhino.py',
        'eval/c5/dataset-v2-freeze-manifest.json', 'eval/c5/historical-exclusions.json', 'eval/c5/final-holdout-commitment.json']
    for name in names: files[name] = hashlib.sha256((root/name).read_bytes()).hexdigest()
    value['source_files'] = dict(sorted(files.items()))
    return validate_spec(value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    value=build()
    with args.output.open('x') as output: json.dump(value,output,ensure_ascii=False,sort_keys=True,indent=2); output.write('\n')
    from plugin.rhino_listener.c5_research_native import digest
    print(json.dumps({'spec_sha256':digest(value),'private_data_bound':False,'execution_authorized':False}))


if __name__=='__main__': main()
