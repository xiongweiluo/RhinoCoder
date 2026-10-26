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
    consumed = history(package)
    return [row for row in package['native_scope']['schedule'] if row['slot_id'] not in consumed]


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
              fixture_attempted, fixture_closed, listener_stopped, integrity_verified):
    effect = 'verified_reads' if native_requested and native_verified else 'unknown' if native_requested else 'none'
    cleanup = ('not_created' if not fixture_attempted else
               'verified' if fixture_closed and listener_stopped else 'unknown')
    return {
        'model_request': 'returned' if model_returned else 'response_unknown' if model_requested else 'not_sent',
        'native_effect': effect, 'fixture_cleanup': cleanup,
        'evidence_integrity': 'verified' if integrity_verified else 'not_verified',
        'resume_eligible': effect != 'unknown' and cleanup != 'unknown' and integrity_verified,
    }
