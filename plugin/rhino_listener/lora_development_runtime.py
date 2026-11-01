"""Shared development lifecycle contract. Python 3.9; no host/model imports.

The same configuration is read by the controller, worker and host. Failure
records describe execution; they never alter a task score or authorize work.
"""
import traceback
import json
from pathlib import Path

from .c5_research_native import require


OPERATIONS = {
    'host_ready_seconds': 180, 'gpu_ready_seconds': 1250,
    'host_cleanup_seconds': 30, 'gpu_stop_seconds': 180,
    'export_seconds': 180, 'transport_exit_seconds': 40,
    'protocol_reply_seconds': 10, 'export_bytes_max': 514 * 1024 * 1024,
}
RECOVERY = {
    'replay_consumed_slots': False,
    'resume_unattempted_after_verified_cleanup': True,
    'incomplete_selection': 'retain_original_without_candidate_promotion',
    'unknown_native_effect_or_cleanup': 'stop_and_reconcile',
    'failure_record': 'stage_message_traceback_and_separate_lifecycle',
}


def configuration(package):
    """One source of operational limits; callers must not invent defaults."""
    if package.get('kind') == 'lora-common-final-comparison-v1':
        return common_configuration(package['comparison_plan'])
    limits = package['limits']
    require(limits['slot_seconds'] == 150 and limits['load_seconds'] == 600
            and limits['cleanup_export_seconds'] == 900, 'fixed development operation limits differ')
    if package.get('schema_version') == 5:
        require(package['runtime_policy'] == {'operations': OPERATIONS, 'recovery': RECOVERY},
                'shared lifecycle contract differs')
    return dict(limits, **OPERATIONS)


def history(package):
    if package.get('schema_version') != 5:
        return {}
    review = package['campaign_policy']['resume']['review']
    row = review['first_slot']
    # The complete old row, including false/unknown fields, is retained.
    return {row['identity']['slot_id']: row}


def active_schedule(package):
    if package.get('kind') == 'lora-common-final-comparison-v1':
        return package['compiled']['views']['schedule']
    consumed = history(package)
    return [row for row in package['native_scope']['schedule'] if row['slot_id'] not in consumed]


def common_capacity(plan):
    """Pure shared arithmetic; case/authority validation belongs to the entry."""
    routes = len(plan['routes'])
    slots = routes * sum(plan['strata'].values())
    steps = routes * sum(n * (3 if layer in {'multistep', 'error_recovery'} else 1)
                         for layer, n in plan['strata'].items())
    messages = 5 * slots + 14 * steps  # two captures + eleven signer captures + dispatch
    peer_files = 8 * steps + 32
    scoped = plan['study_id'] == 'lora-common-document-scope-probe-v1'
    snapshot = plan['study_id'] == 'lora-common-controlled-snapshot-probe-v1'
    continuity = plan['study_id'] == 'lora-common-controlled-continuity-probe-v1'
    diagnostic = plan['study_id'] == 'lora-common-state-diagnostic-v1' or scoped or snapshot or continuity
    probe = plan['study_id'] in {'lora-common-native-probe-v1', 'lora-common-state-diagnostic-v1'} or scoped or snapshot or continuity
    value = {'families': sum(plan['strata'].values()), 'slots': slots,
        'model_step_requests_max': 0 if probe else steps, 'scripted_step_requests_max': steps if probe else 0,
        'generation_stages_max': 0 if probe else 2*steps,
        'host_messages_max': messages, 'signer_captures_per_step_max': 11,
        'peer_files_max': peer_files, 'evidence_files_max': 6*messages + peer_files + 40*slots + 64,
        'worst_window_seconds': slots*plan['limits']['slot_seconds'] + plan['limits']['host_ready_seconds']
            + plan['limits']['load_seconds'] + plan['limits']['cleanup_export_seconds'],
        'execution_authorized': False}
    if diagnostic:
        # A capture takes two snapshots; an execution at most five. Recording
        # each already-required fingerprint adds files, not native operations.
        value['fingerprint_records_max'] = 5 * messages
        value['evidence_files_max'] += value['fingerprint_records_max']
    if scoped:
        value['additional_fixture_operations_max'] = 3
        value['isolated_documents_max'] = 2
        value['document_events_max'] = 256
        value['fingerprint_records_max'] += 2  # native scope-check atomic snapshots
        value['evidence_files_max'] += 18  # two snapshots plus bounded scope/cleanup records
    if continuity:
        value['additional_fixture_operations_max'] = 0
        value['isolated_documents_max'] = 1
    if snapshot:
        value['additional_fixture_operations_max'] = 2
        value['isolated_documents_max'] = 1
        value['fingerprint_records_max'] += 8
        value['evidence_files_max'] += 24  # fingerprints, 2 fixed claims/results, separate fixed ledger
    return value


def common_configuration(plan):
    require(plan['study_id'] == 'lora-common-final-comparison-v1'
            and plan['routes'] == ['base', 'current_lora'] and plan['system'] == 'original'
            and plan['execution_authorized'] is False, 'new two-route preparation contract required')
    cap = common_capacity(plan)
    return {**OPERATIONS, **plan['limits'], 'max_load_attempts': 1, 'max_infrastructure_recoveries': 0,
        'gpu_residency_seconds': cap['worst_window_seconds'], 'gpu_ready_seconds': plan['limits']['load_seconds'],
        'host_messages_max': cap['host_messages_max'], 'export_files_max': cap['peer_files_max']+32,
        'evidence_files_max': cap['evidence_files_max'],
        'evidence_work_bytes_max': 256*1024*1024, 'evidence_total_bytes_max': 1024*1024*1024,
        'gpu_archive_reserve_bytes': 512*1024*1024,
        'gpu_evidence_work_bytes_max': 384*1024*1024, 'gpu_evidence_total_bytes_max': 512*1024*1024,
        'evidence_cleanup_reserve_bytes': 256*1024*1024, 'minimum_free_bytes': 4*1024**3}


def recovery_context(package):
    if package.get('schema_version') != 5: return None
    return {'history': history(package), 'resolved_without_native_effect': list(history(package)),
            'review_sha256': package['campaign_policy']['resume']['review_sha256'],
            'incomplete_selection': RECOVERY['incomplete_selection']}


def prepare_host(root, package):
    """Shared by real Rhino entry and CPU preparation; creates no document."""
    from .lora_development_admission import source_guard
    source_guard(root, package['source_files'])
    return {'config': configuration(package), 'schedule': active_schedule(package),
            'schemas': json.loads((Path(root) / 'eval/c5/rhino-runtime-schema-v1.json').read_text())['core_parameters']}


def failure_record(exc, stage):
    """Private run evidence; public reports must sanitize before publishing."""
    return {'stage': stage, 'type': type(exc).__name__, 'message': str(exc)[:2048],
            'traceback': ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-16384:]}


def lifecycle(*, model_requested, model_returned, native_requested, native_verified,
              fixture_attempted, fixture_closed, listener_stopped, integrity_verified, native_writes=False):
    effect = 'verified_reads' if native_requested and native_verified else 'unknown' if native_requested else 'none'
    if native_writes and native_requested and native_verified:
        effect = 'verified_writes'
    cleanup = ('not_created' if not fixture_attempted else
               'verified' if fixture_closed and listener_stopped else 'unknown')
    return {
        'model_request': 'returned' if model_returned else 'response_unknown' if model_requested else 'not_sent',
        'native_effect': effect, 'fixture_cleanup': cleanup,
        'evidence_integrity': 'verified' if integrity_verified else 'not_verified',
        'resume_eligible': effect != 'unknown' and cleanup != 'unknown' and integrity_verified,
    }
