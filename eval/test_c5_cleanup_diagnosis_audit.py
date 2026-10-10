"""Independent synthetic receipt controls; zero live/holdout operations."""
import copy
import pytest
from training.c5_cleanup_diagnosis_audit import ID, SCOPE, ZERO, digest, audit_diagnosis


def records():
    s = {'study_id': ID, 'cleanup_authorized': False, 'replay_allowed': False,
         'historical_expected_state': {'revision': 0}, **{k: 0 for k in ZERO}}
    f = {'study_id': ID, 'spec_sha256': digest(s)}
    a = {'study_id': ID, 'actor': 'repository_owner', 'approved': True,
         'spec_sha256': digest(s), 'runtime_freeze_sha256': digest(f), 'scope': SCOPE}
    c = {'study_id': ID, 'runtime_freeze_sha256': digest(f), 'replay_allowed': False}
    p = {'study_id': ID, 'runtime_freeze_sha256': digest(f), 'status': 'readonly_diagnosis_observed_not_cleanup',
         'cleanup_authorized': False, 'execution_authority': False, 'whole_host_zero_effects_proven': False,
         'ledger_logical_rows_before_after_same': True,
         'original_result_sha256_after': '6093aa3ae6e25f31ecaaad551c368a919d499ff2e6c8aa57d674910295b3c3a9',
         'historical_expected_state': {'revision': 0}, 'stored_scene_rows': [{'revision': 1}],
         'checks': {'rhino_ui_thread_flag': {'status': 'observed', 'value': False},
                    'cached_owner': {'backend_thread_matches': True},
                    'stored_scene_matches_history': {'status': 'observed', 'value': False}}, **{k: 0 for k in ZERO}}
    return copy.deepcopy([s, f, a, c, p])


def test_off_ui_receipt_proves_no_document_reads_not_cleanup():
    s, f, a, c, p = records(); r = audit_diagnosis(s, f, a, c, p, digest(p))
    assert r['cleanup_authorized'] is False and r['execution_authority'] is False


def test_integer_claim_cannot_impersonate_false_boolean():
    s, f, a, c, p = records(); c['replay_allowed'] = 0
    with pytest.raises(ValueError): audit_diagnosis(s, f, a, c, p, digest(p))


def test_safe_UI_positive_and_integer_thread_negative_are_distinct():
    s, f, a, c, p = records()
    for name in ('rhino_ui_thread_flag', 'active_document_present', 'active_serial_matches',
                 'active_content_matches', 'fixture_registry_present', 'fixture_serial_matches',
                 'fixture_headless_unsaved', 'backend_document_serial_matches'):
        p['checks'][name] = {'status': 'observed', 'value': True}
    p['checks']['cached_owner'].update(backend_closed=False, hub_fixture_matches_backend=True, backend_serial_matches=True)
    p['checks']['fixture_geometry_summary'] = {'status': 'observed', 'value': {'empty': True}}
    assert audit_diagnosis(s, f, a, c, p, digest(p))['cleanup_authorized'] is False
    p['checks']['rhino_ui_thread_flag']['value'] = 1
    with pytest.raises(ValueError): audit_diagnosis(s, f, a, c, p, digest(p))


@pytest.mark.parametrize('bad', ['old_grant', 'old_claim', 'external', 'cleanup', 'geometry_off_ui',
                                'snapshot', 'ledger_changed', 'original_changed', 'whole_host_claim', 'compare_lie'])
def test_independent_scope_and_raw_graph_negative_controls(bad):
    s, f, a, c, p = records(); external = None
    if bad == 'old_grant': a['study_id'] = 'C5SAFE-HOSTASSURANCE-C-20261007-A'
    elif bad == 'old_claim': c['runtime_freeze_sha256'] = '0'*64
    elif bad == 'external': external = '0'*64
    elif bad == 'cleanup': p['cleanup_authorized'] = True
    elif bad == 'geometry_off_ui': p['checks']['fixture_geometry_summary'] = {'status': 'observed', 'value': {'empty': True}}
    elif bad == 'snapshot': p['atomic_snapshot_calls'] = 1
    elif bad == 'ledger_changed': p['ledger_logical_rows_before_after_same'] = False
    elif bad == 'original_changed': p['original_result_sha256_after'] = 'f'*64
    elif bad == 'whole_host_claim': p['whole_host_zero_effects_proven'] = True
    else: p['checks']['stored_scene_matches_history']['value'] = True
    with pytest.raises(ValueError): audit_diagnosis(s, f, a, c, p, external or digest(p))
