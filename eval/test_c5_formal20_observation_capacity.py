"""No private/live data: quota and frozen synthetic capacity controls."""
import pytest

from plugin.rhino_listener.c5_formal20_observation_capacity import (
    LIMITS, ObservationCapacity, validate_limits, validate_settle_sample_count,
)


def test_known_synthetic_high_traffic_matrix_exceeds_old_512():
    from tools.c5_formal20_capacity_synthetic import characterize
    result = characterize()
    assert result['slots'] == 40 and result['model_requests'] == 56
    assert result['generation_stages'] == 104
    assert result['source_guard_calls'] == 1403
    assert result['native_request_count'] == 1136
    assert result['maximum_child_request_count'] == 67
    assert result['source_guard_calls'] > 512
    assert result['real_model_Rhino_GPU_holdout_calls'] == 0
    assert result['owner_private_cases_or_keys_read'] is False
    assert result['formal_quality_claim'] is False


@pytest.mark.parametrize('key', list(LIMITS))
def test_changed_or_boolean_limit_rejected(key):
    for wrong in (True, float(LIMITS[key]), LIMITS[key] + 1, LIMITS[key] - 1):
        value = dict(LIMITS); value[key] = wrong
        with pytest.raises(ValueError): validate_limits(value)


def test_normal_exhaustion_is_sticky_but_cleanup_record_reserve_survives():
    quota = ObservationCapacity(LIMITS)
    for _ in range(2048): quota.admit_record('checkpoint')
    with pytest.raises(ValueError): quota.admit_record('checkpoint')
    assert (quota.normal, quota.cleanup, quota.records) == (2048, 0, 2048)
    assert quota.dispatch_blocked
    quota.admit_record('failure')
    for _ in range(256):
        assert quota.admit_record('cleanup_checkpoint')['execution_authority'] is False
    with pytest.raises(ValueError): quota.admit_record('cleanup_checkpoint')
    with pytest.raises(ValueError): quota.admit_record('checkpoint')
    assert quota.records == 2305


def test_record_quota_is_not_unbounded_and_unknown_kind_does_not_mutate():
    quota = ObservationCapacity(LIMITS)
    with pytest.raises(ValueError): quota.admit_record('ignore_unknown_assembly')
    assert quota.records == 0
    for _ in range(4096): quota.admit_record('detach_attempt')
    with pytest.raises(ValueError): quota.admit_record('failure')
    assert quota.records == 4096 and quota.dispatch_blocked


def test_failure_blocks_dispatch_not_merely_a_logged_warning():
    quota = ObservationCapacity(LIMITS)
    quota.admit_record('failure')
    with pytest.raises(ValueError): quota.admit_record('checkpoint')
    assert quota.admit_record('cleanup_checkpoint')['dispatch_blocked']


@pytest.mark.parametrize('count', [-1, 9, True, 8.0, None])
def test_invalid_settle_sample_count_rejected(count):
    with pytest.raises(ValueError): validate_settle_sample_count(count)


def test_eight_samples_are_a_bound_not_eight_dispatches():
    assert validate_settle_sample_count(8) == 8
    assert not hasattr(ObservationCapacity(LIMITS), 'dispatch')
