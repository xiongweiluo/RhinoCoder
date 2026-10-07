"""Independent aggregate diagnosis replay, no producer/helper or live imports.

External receipt must come from the actual UI output, not be invented by
rehashing the result. Verification never grants cleanup or research authority.
"""
import hashlib
import json

ID = 'C5DIAG-HOSTASSURANCE-C-20261007-A'
SCOPE = 'retired C only; decomposed readonly live checks, no snapshot transaction, cleanup, key access, subscription, model or holdout'
ZERO = ('model_calls', 'gpu_calls', 'holdout_calls', 'tool_dispatches', 'fixture_creates', 'fixture_closes',
        'key_reads', 'key_removes', 'new_subscriptions', 'delegate_removes', 'atomic_snapshot_calls', 'ledger_updates')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def audit_diagnosis(spec, freeze, approval, claim, packet, external_packet_sha256):
    require(spec['study_id'] == freeze['study_id'] == ID and freeze['spec_sha256'] == digest(spec),
            'independent exact diagnosis freeze differs')
    expected = {'study_id': ID, 'actor': 'repository_owner', 'approved': True,
                'spec_sha256': digest(spec), 'runtime_freeze_sha256': digest(freeze), 'scope': SCOPE}
    require(digest(approval) == digest(expected)
            and digest(claim) == digest({'study_id': ID, 'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False}),
            'independent new one-use grant/claim differs')
    require(packet['study_id'] == ID and packet['runtime_freeze_sha256'] == digest(freeze)
            and digest(packet) == external_packet_sha256, 'actual external diagnosis receipt differs')
    require(packet['status'] == 'readonly_diagnosis_observed_not_cleanup'
            and packet['cleanup_authorized'] is False and packet['execution_authority'] is False
            and packet['whole_host_zero_effects_proven'] is False
            and spec['cleanup_authorized'] is False and spec['replay_allowed'] is False
            and all(type(spec[k]) is int and spec[k] == 0 and type(packet[k]) is int and packet[k] == 0 for k in ZERO),
            'readonly diagnostic scope or assurance falsely expanded')
    require(packet['ledger_logical_rows_before_after_same'] is True
            and packet['original_result_sha256_after'] == '6093aa3ae6e25f31ecaaad551c368a919d499ff2e6c8aa57d674910295b3c3a9'
            and packet['historical_expected_state'] == spec['historical_expected_state'],
            'logical ledger/original failure not preserved')
    checks = packet['checks']
    require(digest(checks['stored_scene_matches_history']) == digest({'status': 'observed',
            'value': packet['stored_scene_rows'] == [spec['historical_expected_state']]}), 'stored state comparison differs')
    def true(name):
        value = checks.get(name)
        return isinstance(value, dict) and set(value) == {'status', 'value'} and value['status'] == 'observed' and value['value'] is True
    if not true('rhino_ui_thread_flag') or checks['cached_owner']['backend_thread_matches'] is not True:
        require(not {'active_document_present', 'active_serial_matches', 'active_content_sha256_before',
                    'fixture_registry_present', 'fixture_geometry_summary', 'current_frozen_scene_digest'} & set(checks),
                'unsafe thread attempted document/geometry reads')
    if 'fixture_geometry_summary' in checks or 'current_frozen_scene_digest' in checks:
        require(all(true(k) for k in ('rhino_ui_thread_flag', 'active_document_present', 'active_serial_matches',
                'active_content_matches', 'fixture_registry_present', 'fixture_serial_matches',
                'fixture_headless_unsaved', 'backend_document_serial_matches'))
                and checks['cached_owner']['backend_thread_matches'] is True
                and checks['cached_owner']['backend_closed'] is False
                and checks['cached_owner']['hub_fixture_matches_backend'] is True
                and checks['cached_owner']['backend_serial_matches'] is True, 'geometry read bypassed a safe prerequisite')
    return {'study_id': ID, 'status': 'limited_readonly_diagnosis_packet_verified_not_cleanup',
            'cleanup_authorized': False, 'execution_authority': False,
            'opaque_host_code_or_zero_side_effects_proven': False,
            'external_packet_sha256': external_packet_sha256}
