"""Opt-in trusted-host checkpoint lifecycle; no host effects on import.

This is NOT the legacy full-byte guard. The field entry must separately
verify its fixed deployment/model/budget and exact study authorization.
Injected backend construction, declared warmup and subscription are covered
by that study grant, not by guarantee-transition consent. No canary is made.
"""
from __future__ import annotations

import math
import time

from .c5_host_assurance_v2 import POLICY, validate_transition, compare_visible_continuity
from .c5_host_observer import validate_snapshot
from .c5_research_channel import publish_json
from .c5_research_native import digest, require

DEV_ID = 'C5DEV-HOSTASSURANCE-20261007-A'
STUDIES = {
    DEV_ID: 'direct repository_owner approval of new host-assurance development spec and complete runtime freeze',
    'c5-rhino-paired-20-v1': 'direct repository_owner approval of complete C5-6 formal20 spec and runtime freeze',
}


def host_policy(transition, transition_approval):
    validate_transition(transition, transition_approval)
    return {'policy_id': POLICY, 'transition_spec_sha256': digest(transition),
        'transition_approval_sha256': digest(transition_approval), 'legacy_byte_closure_verified': False,
        'checkpoint_limit': 512, 'max_subscriptions': 1, 'canary_assemblies': 0,
        'baseline_sealing': 'after_declared_import_type_controller_warmup_before_any_model_generation',
        'event_policy': 'no_new_events_or_visible_changes_after_seal_no_exceptions',
        'detach_proof': 'exact_delegate_remove_call_and_observed_queue_only_not_full_handler_absence'}


def validate_study_binding(spec, freeze, approval, transition, transition_approval):
    """Partial host-policy binding, never a whole field admission proof."""
    selected = validate_transition(transition, transition_approval)
    study = spec.get('study_id')
    require(study in STUDIES and freeze.get('study_id') == study
        and spec.get('execution_ready') is True and freeze.get('execution_ready') is True
        and freeze.get('spec_sha256') == digest(spec), 'new complete study binding required')
    require(type(approval.get('approved')) is bool and approval == {'study_id': study, 'actor': 'repository_owner', 'approved': True,
        'spec_sha256': digest(spec), 'runtime_freeze_sha256': digest(freeze),
        'approval_basis': STUDIES[study]}, 'new exact study grant required; transition alone cannot run')
    policy = host_policy(transition, transition_approval)
    require(spec.get('host_assurance') == freeze.get('host_assurance') == policy
        and spec['host_assurance']['legacy_byte_closure_verified'] is False
        and freeze['host_assurance']['legacy_byte_closure_verified'] is False
        and all(type(record[k]) is int for record in (spec['host_assurance'],freeze['host_assurance'])
            for k in ('checkpoint_limit','max_subscriptions','canary_assemblies')),
        'explicit weaker policy must be bound in both new frozen records')
    require(spec.get('automatic_retry_allowed') is False and spec.get('default_route_change_allowed') is False,
        'no replay/default-route mutation permitted')
    return {**selected, 'study_id': study, 'runtime_freeze_sha256': digest(freeze),
        'policy_binding_verified': True, 'whole_field_authority_verified': False}


class HostAssuranceSession:
    """One-use journal; drift blocks dispatch but never fabricates cleanup.

    Source guard returns the frozen project inventory digest and rechecks
    readable frozen host files. Only narrowly authorized cleanup may invoke
    cleanup_checkpoint, which is deliberately NOT a dispatch guard. Any
    lifecycle/error/continuity failure is sticky and invalidates the audit.
    """
    def __init__(self, state, binding, backend, source_guard, source_sha, *, clock=time.monotonic):
        require(binding.get('policy_binding_verified') is True
            and binding.get('whole_field_authority_verified') is False
            and binding.get('policy_id') == POLICY and binding.get('study_id') in STUDIES,
            'validated explicit study host binding required')
        self.state, self.binding, self.backend = state, binding, backend
        self.source_guard, self.source_sha, self.clock = source_guard, source_sha, clock
        self.start_time = clock()
        self.genesis = digest({'study_id': binding['study_id'], 'runtime_freeze_sha256': binding['runtime_freeze_sha256'],
            'policy_id': POLICY, 'source_inventory_sha256': source_sha})
        self.head, self.sequence, self.checkpoints = self.genesis, 0, 0
        self.started, self.subscribe_attempted, self.detached, self.finished = False, False, False, False
        self.baseline, self.blocked = None, False

    def _write(self, kind, payload):
        require(not self.finished and self.sequence < 1040, 'bounded one-use host journal exhausted/sealed')
        elapsed = self.clock() - self.start_time
        require(math.isfinite(elapsed) and elapsed >= 0, 'host journal clock invalid')
        value = {'schema_version': 1, 'study_id': self.binding['study_id'], 'policy_id': POLICY,
            'runtime_freeze_sha256': self.binding['runtime_freeze_sha256'], 'sequence': self.sequence,
            'elapsed_seconds': elapsed, 'previous_sha256': self.head, 'kind': kind, 'payload': payload}
        value['record_sha256'] = digest(value)
        publish_json(self.state, 'host-continuity-%04d.json' % self.sequence, value)
        self.head, self.sequence = value['record_sha256'], self.sequence + 1

    def _source(self):
        require(self.source_guard() == self.source_sha, 'frozen source/readable host file drift')

    def _capture(self):
        before = self.backend.drain_events()
        snapshot = validate_snapshot(self.backend.snapshot())
        after = self.backend.drain_events()
        for batch in (before, after):
            require(isinstance(batch, dict) and set(batch) == {'events', 'errors', 'dropped'}
                and isinstance(batch['events'], list) and len(batch['events']) <= 256
                and isinstance(batch['errors'], list) and type(batch['dropped']) is int
                and batch['dropped'] >= 0, 'bounded raw host event batch required')
        return {'snapshot': snapshot, 'events': {'events': before['events'] + after['events'],
            'errors': before['errors'] + after['errors'], 'dropped': before['dropped'] + after['dropped']}}

    def seal_baseline(self):
        """After ALL approved warmup/delegates; one subscription, never retry."""
        require(not self.started and not self.finished, 'host session already started/retired')
        self.started = True
        publish_json(self.state, 'host-continuity.started.json', {'study_id': self.binding['study_id'],
            'runtime_freeze_sha256': self.binding['runtime_freeze_sha256'], 'replay_allowed': False})
        try:
            self._source()
            self._write('subscribe_attempt', {})
            self.subscribe_attempted = True
            self.backend.subscribe()
            self._write('subscribed', {})
            raw = self._capture()
            require(raw['events']['dropped'] == 0 and raw['events']['errors'] == [],
                'baseline event loss/error cannot be trusted')
            # Setup-generated events are retained, not promoted to source proof.
            self.baseline = raw['snapshot']
            compare_visible_continuity(self.baseline, self.baseline, {'events': [], 'errors': [], 'dropped': 0})
            self._source()
            self._write('baseline', raw)
            self.checkpoint('post_baseline')
        except BaseException as exc:
            self.blocked = True
            self._write('failure', {'phase': 'baseline', 'error_type': type(exc).__name__})
            raise

    def checkpoint(self, label):
        require(self.started and self.baseline is not None and not self.finished and not self.blocked,
            'host assurance not sealed or blocked; no dispatch')
        return self._checkpoint(label, cleanup=False)

    def cleanup_checkpoint(self, label):
        """Only close/stop/detach of an already-owned fixture, never dispatch."""
        require(self.started and not self.finished, 'cleanup outside started host session')
        return self._checkpoint(label, cleanup=True)

    def _checkpoint(self, label, *, cleanup):
        require(isinstance(label, str) and label.isascii() and 0 < len(label) <= 80
            and all(c.isalnum() or c in '-_.' for c in label) and self.checkpoints < 512,
            'bounded public checkpoint label required')
        self.checkpoints += 1
        try:
            self._source()
            raw = self._capture()
            error = None
            try:
                require(self.baseline is not None, 'baseline never sealed')
                compare_visible_continuity(self.baseline, raw['snapshot'], raw['events'])
            except BaseException as exc:
                self.blocked, error = True, type(exc).__name__
            self._write('cleanup_checkpoint' if cleanup else 'checkpoint', {'label': label, **raw,
                'continuity_error_type': error, 'source_inventory_sha256': self.source_sha})
            if error is not None and not cleanup:
                raise RuntimeError('host visible continuity drift; dispatch blocked without retry')
            return self.source_sha
        except BaseException as exc:
            self.blocked = True
            self._write('failure', {'phase': 'cleanup' if cleanup else 'checkpoint', 'error_type': type(exc).__name__})
            raise

    def finish(self):
        """One exact delegate removal; failures retained, cannot retry/reseal.

        Queue quietness is observational evidence, NOT a proof of complete
        removal/coverage. No field canary/fixture/tool/model is created here.
        """
        require(self.started and not self.finished, 'host session cannot finish twice')
        self._write('detach_attempt', {})
        try:
            require(self.subscribe_attempted, 'no subscription was attempted')
            self.backend.unsubscribe()
            self.detached = True
            self._write('detached', {'exact_remove_call_completed': True,
                'complete_handler_absence_proven': False})
            self.cleanup_checkpoint('after_detach')
        except BaseException as exc:
            self.blocked = True
            self._write('failure', {'phase': 'detach', 'error_type': type(exc).__name__})
        value = {'schema_version': 1, 'study_id': self.binding['study_id'], 'policy_id': POLICY,
            'runtime_freeze_sha256': self.binding['runtime_freeze_sha256'], 'genesis_sha256': self.genesis,
            'journal_head_sha256': self.head, 'record_count': self.sequence,
            'source_inventory_sha256': self.source_sha, 'blocked': self.blocked,
            'exact_remove_call_completed': self.detached, 'complete_handler_absence_proven': False,
            'legacy_byte_closure_verified': False, 'causal_origin_or_emitted_bytes_proven': False,
            'execution_authority': False}
        publish_json(self.state, 'host-continuity-seal.json', value)
        self.finished = True
        return {'study_id': self.binding['study_id'], 'seal_sha256': digest(value),
            'journal_head_sha256': self.head, 'record_count': self.sequence,
            'blocked': self.blocked, 'execution_authority': False}
