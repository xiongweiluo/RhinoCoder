"""Final study binding, shared with Rhino's Python 3.9; no execution on import.

Public preparation is not a grant. Private runtime views are opened only after
the separate owner record binds the source specification and sealed receipt.
"""
import json
from pathlib import Path
import time

from .c5_research_channel import read_json
from .c5_research_native import digest, require
from .lora_development_admission import source_guard

STUDY = 'lora-common-final-comparison-v1'
CATEGORIES = ('training_validation_development', 'original20', 'original80', 'a5_p2',
              'phase1_eight', 'v1_v2_and_native_probes', 'other_exposed_and_derivatives')
FLAGS = ('complete_exclusion_inventory_reviewed', 'independent_of_model_and_prompt_selection',
         'frozen_training_split_file_identities_checked', 'semantic_near_duplicates_reviewed',
         'fixture_and_expected_geometry_reviewed_without_model_trials', 'encryption_roundtrip_verified',
         'keys_and_plaintext_not_shared_with_agent', 'not_consumed_by_model_or_formal_runner')


def approval_record(spec, receipt):
    return {'actor': 'repository_owner', 'approved': True, 'study_id': STUDY,
        'scope': 'one_frozen_final_comparison_no_training_no_replay',
        'spec_sha256': digest(spec), 'receipt_sha256': digest(receipt),
        'package_sha256': receipt['runtime_package_sha256']}


def validate_receipt(spec, receipt):
    require(receipt['study_id'] == STUDY and receipt['spec_sha256'] == digest(spec)
            and receipt['choices_sha256'] == spec['choices_sha256']
            and receipt['status'] == 'owner_sealed_unconsumed_not_execution_authority'
            and receipt['family_count'] == 40 and receipt['slot_count'] == 80
            and receipt['strata'] == spec['comparison_plan']['strata']
            and receipt['execution_authorized'] is False,
            'sealed owner receipt differs')
    attestation = receipt['custodian_attestation']
    require(set(attestation) == {'actor', 'sealed_at_utc', *FLAGS}
            and attestation['actor'] == 'repository_owner' and all(attestation[k] is True for k in FLAGS)
            and receipt['automated_overlap_count'] == 0 and receipt['agent_private_access'] is False
            and receipt['model_calls'] == receipt['rhino_calls'] == 0
            and set(receipt['exclusions']) == set(CATEGORIES), 'complete unconsumed owner custody required')
    for key, n in spec['exclusion_reference']['minimum_counts'].items():
        require(type(receipt['exclusions'][key]['rows']) is int and receipt['exclusions'][key]['rows'] >= n,
                'owner exclusion population incomplete')
    for key in ('runtime_package_sha256', 'cases_sha256', 'compiled_sha256', 'schedule_sha256'):
        value = receipt[key]
        require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                'exact sealed digest required')


def validate_runtime(spec, receipt, package):
    validate_receipt(spec, receipt)
    require(set(package) == set(spec) | {'compiled'}
            and all(package[k] == v for k, v in spec.items())
            and digest(package) == receipt['runtime_package_sha256']
            and digest(package['compiled']) == receipt['compiled_sha256']
            and package['compiled']['cases_sha256'] == receipt['cases_sha256']
            and digest(package['compiled']['views']['schedule']) == receipt['schedule_sha256'],
            'private runtime binding differs')
    return package


def admit(root, endpoint, *, cleanup=False):
    root = Path(root)
    spec = json.loads((root/'lora-final-spec.json').read_text())
    require(spec['kind'] == STUDY and str(root) == spec['endpoints'][endpoint]['source_root'],
            'fixed final endpoint required')
    source_guard(root, spec['source_files'])
    state = Path(spec['endpoints'][endpoint]['state_root'])
    receipt = read_json(state, 'owner-receipt.json')
    validate_receipt(spec, receipt)
    require(read_json(state, 'owner-approval.json') == approval_record(spec, receipt),
            'separate exact final approval required')
    if not cleanup:
        require(time.time() < spec['lease_end_epoch'] - spec['limits']['cleanup_export_seconds'], 'final lease cutoff')
    # No answers in this common runtime package; scorer cases stay on the Mac.
    package = validate_runtime(spec, receipt, read_json(state, 'runtime-package.json'))
    return package, state, receipt
