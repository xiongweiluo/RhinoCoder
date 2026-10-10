"""Pure bounded formal observation quota prototype; never field authority.

No host subscription, fixture, source bypass, task I/O or default-policy change.
The separately reviewed formal entry must bind this capacity in a NEW freeze.
Old host sessions retain their 512/1040 bounds and deployed bytes unchanged.
"""

LIMITS = {'normal_checkpoints': 2048, 'cleanup_checkpoints': 256,
          'journal_records': 4096, 'settle_samples_per_execute': 8}
KINDS = frozenset({'subscribe_attempt', 'subscribed', 'baseline', 'checkpoint',
    'cleanup_checkpoint', 'detach_attempt', 'detached', 'failure'})


def validate_limits(value):
    if not isinstance(value, dict) or set(value) != set(LIMITS):
        raise ValueError('exact formal observation capacity required')
    if any(type(value[key]) is not int or value[key] != LIMITS[key] for key in LIMITS):
        raise ValueError('fixed integer formal observation capacity required')
    return dict(value)


class ObservationCapacity:
    """Fail-closed accounting only. Cleanup quota never grants cleanup permission.

    A exhausted normal quota is sticky, while reserved record space remains
    available for already-owned, separately authorized cleanup and failure
    evidence. All checks precede counter mutation; no replay/reset API.
    """
    def __init__(self, limits):
        self.limits = validate_limits(limits)
        self.normal = self.cleanup = self.records = 0
        self.dispatch_blocked = False

    def admit_record(self, kind):
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError('unknown observation record kind')
        if self.records >= self.limits['journal_records']:
            self.dispatch_blocked = True
            raise ValueError('formal observation journal exhausted')
        if kind == 'checkpoint':
            if self.dispatch_blocked or self.normal >= self.limits['normal_checkpoints']:
                self.dispatch_blocked = True
                raise ValueError('formal normal observation quota exhausted; no dispatch')
        elif kind == 'cleanup_checkpoint':
            if self.cleanup >= self.limits['cleanup_checkpoints']:
                self.dispatch_blocked = True
                raise ValueError('formal cleanup observation quota exhausted')
        self.records += 1
        if kind == 'checkpoint': self.normal += 1
        if kind == 'cleanup_checkpoint': self.cleanup += 1
        if kind == 'failure': self.dispatch_blocked = True
        return {'normal': self.normal, 'cleanup': self.cleanup, 'records': self.records,
                'dispatch_blocked': self.dispatch_blocked, 'execution_authority': False}


def validate_settle_sample_count(count):
    if type(count) is not int or not 0 <= count <= LIMITS['settle_samples_per_execute']:
        raise ValueError('bounded formal settle sample count required')
    return count
