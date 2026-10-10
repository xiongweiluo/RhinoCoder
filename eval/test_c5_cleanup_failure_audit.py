"""CPU synthetic prefix audit controls; never invoke a live evidence entry."""
import copy
import pytest
from tools.audit_c5_retired_c_cleanup_failure import C_ID, C_FREEZE_SHA, POLICY, digest, verify_prefix


def rows():
    head = 'a' * 64
    values = []
    for n, kind in enumerate(('subscribe_attempt', 'subscribed', 'baseline')):
        row = {'schema_version': 1, 'sequence': n, 'study_id': C_ID, 'policy_id': POLICY,
               'runtime_freeze_sha256': C_FREEZE_SHA, 'previous_sha256': head,
               'elapsed_seconds': n, 'kind': kind, 'payload': {}}
        row['record_sha256'] = digest(row)
        head = row['record_sha256']
        values.append(row)
    return values


def test_unsealed_prefix_integrity_is_not_a_completed_safety_receipt():
    values = rows()
    head, kinds = verify_prefix(values, 'a' * 64)
    assert head == values[-1]['record_sha256']
    assert kinds == {'subscribe_attempt': 1, 'subscribed': 1, 'baseline': 1}
    assert not any(r['kind'] == 'detached' for r in values)


@pytest.mark.parametrize('field,value', [
    ('sequence', 99), ('sequence', True), ('study_id', 'formal20'), ('policy_id', 'full_byte_closure'),
    ('runtime_freeze_sha256', 'b' * 64), ('previous_sha256', 'c' * 64),
    ('record_sha256', 'd' * 64), ('elapsed_seconds', -1), ('elapsed_seconds', False),
])
def test_changed_chain_or_identity_never_passes(field, value):
    values = copy.deepcopy(rows())
    values[1][field] = value
    if field != 'record_sha256':
        values[1]['record_sha256'] = digest({k: v for k, v in values[1].items() if k != 'record_sha256'})
    with pytest.raises(ValueError):
        verify_prefix(values, 'a' * 64)


def test_import_is_stdlib_only_not_live_producer_execution():
    import tools.audit_c5_retired_c_cleanup_failure as module
    assert 'Rhino' not in module.__dict__ and 'torch' not in module.__dict__
    assert 'validate_retired' not in module.__dict__ and callable(module.audit)
