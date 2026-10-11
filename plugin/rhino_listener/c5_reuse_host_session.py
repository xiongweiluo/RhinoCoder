"""New reuse development host binding, reusing the finite raw observer.

No subscription/import of Rhino on import or construction. No new observers,
canaries or UI. Actual entry-return/Idle wiring and current host acceptance are
separate frozen requirements, never inherited from a retired host instance.
"""
import math
import time
from pathlib import Path

from plugin.rhino_listener.c5_host_assurance_session import HostAssuranceSession
from plugin.rhino_listener.c5_host_assurance_v2 import POLICY, compare_visible_continuity
from plugin.rhino_listener.c5_formal20_observation_capacity import LIMITS, ObservationCapacity
from plugin.rhino_listener.c5_research_channel import publish_json
from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.c5_reuse_field_scope import STUDY, validate_binding, strict, canonical


class ReuseHostSession(HostAssuranceSession):
    def __init__(self, field_binding, registry, backend, source_guard, source_sha, *, clock=time.monotonic):
        validate_binding(field_binding)
        require(field_binding['endpoint']=='mac', 'reuse_host_mac_endpoint_required')
        require(registry.binding == field_binding, 'reuse_host_registry_scope')
        self.state = Path(field_binding['paths']['state_root']) / 'host'
        self.field_binding, self.registry = strict(canonical(field_binding)), registry
        self.binding = {'study_id': STUDY, 'runtime_freeze_sha256': field_binding['runtime_sha256'],
                        'policy_id': POLICY, 'whole_field_authority_verified': False}
        self.backend, self.source_guard, self.source_sha, self.clock = backend, source_guard, source_sha, clock
        self.start_time = clock()
        self.genesis = digest({'study_id': STUDY, 'runtime_freeze_sha256': field_binding['runtime_sha256'],
                               'policy_id': POLICY, 'source_inventory_sha256': source_sha})
        self.head, self.sequence, self.checkpoints = self.genesis, 0, 0
        self.started = self.subscribe_attempted = self.detached = self.finished = self.blocked = False
        self.baseline = None
        self.quota = ObservationCapacity(LIMITS)

    def seal_baseline(self):
        require(not self.started and not self.finished, 'reuse_host_no_retry')
        self.registry.claim('host')  # Cross-directory admission precedes subscription.
        self.state.mkdir(mode=0o700)
        return super().seal_baseline()

    def _write(self, kind, payload):
        require(not self.finished, 'reuse_host_sealed')
        elapsed = self.clock() - self.start_time
        require(math.isfinite(elapsed) and elapsed >= 0, 'reuse_host_clock')
        self.quota.admit_record(kind)
        row = {'schema_version': 1, 'study_id': STUDY, 'policy_id': POLICY,
               'runtime_freeze_sha256': self.binding['runtime_freeze_sha256'], 'sequence': self.sequence,
               'elapsed_seconds': elapsed, 'previous_sha256': self.head, 'kind': kind, 'payload': payload}
        row['record_sha256'] = digest(row)
        publish_json(self.state, 'host-continuity-%04d.json' % self.sequence, row)
        self.head, self.sequence = row['record_sha256'], self.sequence + 1

    def _checkpoint(self, label, *, cleanup):
        require(type(label) is str and label.isascii() and 0 < len(label) <= 80
                and all(c.isalnum() or c in '-_.' for c in label), 'reuse_host_label')
        kind = 'cleanup_checkpoint' if cleanup else 'checkpoint'
        count, cap = (self.quota.cleanup, 256) if cleanup else (self.quota.normal, 2048)
        if count >= cap or (not cleanup and self.quota.dispatch_blocked):
            self.blocked = self.quota.dispatch_blocked = True
            raise RuntimeError('reuse_host_observation_capacity')
        self.checkpoints += 1
        try:
            self._source()
            raw = self._capture()
            error = None
            try:
                require(self.baseline is not None, 'reuse_host_baseline_required')
                compare_visible_continuity(self.baseline, raw['snapshot'], raw['events'])
            except BaseException as exc:
                self.blocked, error = True, type(exc).__name__
            self._write(kind, {'label': label, **raw, 'continuity_error_type': error,
                              'source_inventory_sha256': self.source_sha})
            if error is not None and not cleanup:
                raise RuntimeError('reuse_host_drift_no_dispatch')
            return self.source_sha
        except BaseException as exc:
            self.blocked = True
            self._write('failure', {'phase': 'cleanup' if cleanup else 'checkpoint', 'error_type': type(exc).__name__})
            raise
