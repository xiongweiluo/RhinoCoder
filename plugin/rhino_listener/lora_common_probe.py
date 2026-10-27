"""Shared preparation for one public, zero-model native seam probe package.

Python 3.9. No automatic startup, old grant inheritance, or final-test access.
"""
import json
from pathlib import Path
import time

from .c5_research_channel import read_json
from .c5_research_native import CORE, digest, require
from .lora_development_admission import source_guard


def prepare(root, package):
    source_guard(root, package['source_files'])
    choices = {'public_common_native_probe_v1': ('lora-common-native-probe-v1', 2),
               'public_common_state_diagnostic_v1': ('lora-common-state-diagnostic-v1', 1),
               'public_common_document_scope_probe_v1': ('lora-common-document-scope-probe-v1', 1)}
    require(package['kind'] in choices, 'known zero-model probe package required')
    study, slots = choices[package['kind']]
    require(package['model_loads'] == 0 and package['execution_authorized'] is False
            and package['plan']['study_id'] == study
            and package['plan']['routes'] == ['scripted_probe']
            and package['plan']['system'] == 'original' and set(package['plan']['tools']) == CORE
            and len(package['compiled']['views']['schedule']) == slots,
            'exact scripted public probe scope only')
    schemas = json.loads((Path(root)/'eval/c5/rhino-runtime-schema-v1.json').read_text())['core_parameters']
    return {'schemas': schemas, 'views': package['compiled']['views'], 'capacity': package['capacity']}


def approval_record(package):
    return {'actor': 'repository_owner', 'approved': True, 'package_sha256': digest(package),
            'scope': ('one_document_scope_and_move_read_probe_zero_models_no_final_test'
                      if package['kind'] == 'public_common_document_scope_probe_v1' else
                      'one_move_fingerprint_diagnostic_zero_models_no_final_test'
                      if package['kind'] == 'public_common_state_diagnostic_v1' else
                      'two_new_public_scripted_native_probes_zero_models_no_final_test')}


def admit(root, package):
    prepare(root, package)
    require(str(root) == package['source_root'], 'fixed source root required')
    state = Path(package['state_root'])
    require(read_json(state, 'owner-approval.json') == approval_record(package), 'new exact owner approval required')
    # Retire the disproven candidate in newly built source. The consumed frozen
    # bundle and its failure evidence remain unchanged. RhinoDoc static events
    # do not fire for headless documents; headless EventWatcher is a Rhino 9 API.
    require(package['kind'] != 'public_common_document_scope_probe_v1',
            'retired static-event candidate: incompatible with pinned Rhino 8 headless documents')
    require(time.time() < package['lease_end_epoch'] - package['capacity']['worst_window_seconds'],
            'complete probe window unavailable')
    return state
