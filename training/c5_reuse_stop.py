"""Injected, exact-identity pidfd stop boundary; no signals on import.

No process enumeration, name-based kill, reconnect, SIGKILL or retry. The
trusted entry must verify frozen stop code/environment and the exact grant.
Physical exit and GPU absence are separate evidence, never inferred here.
"""
import selectors
import signal
import os

from training.c5_reuse_evidence import canonical, exact, is_sha, require, sha, strict
from training.c5_reuse_field_scope import STUDY, validate_binding, path


def target(value):
    exact(value, ('pid', 'uid', 'boot_id', 'start_ticks', 'executable_sha256', 'argv_sha256', 'cwd'))
    require(type(value['pid']) is int and value['pid'] > 1 and type(value['uid']) is int and value['uid'] >= 0
            and type(value['start_ticks']) is int and value['start_ticks'] > 0
            and type(value['boot_id']) is str and len(value['boot_id']) == 36
            and is_sha(value['executable_sha256']) and is_sha(value['argv_sha256'])
            and type(value['cwd']) is str and value['cwd'].startswith('/'), 'stop_target_identity')
    path(value['cwd'])


def stop_once(binding, expected, approval, registry, journal, ops):
    validate_binding(binding)
    require(binding['endpoint']=='gpu', 'stop_gpu_endpoint_required')
    binding, expected, approval = (strict(canonical(v)) for v in (binding, expected, approval))
    target(expected)
    grant = {'study_id': binding['study_id'], 'actor': 'repository_owner', 'approved': True,
             'spec_sha256': binding['spec_sha256'], 'runtime_sha256': binding['runtime_sha256'],
             'target_identity_sha256': sha(expected), 'signal': 'SIGTERM', 'signals_max': 1,
             'approval_basis': 'direct repository_owner exact reuse stop scope approval'}
    require(canonical(approval) == canonical(grant), 'exact_new_stop_approval')
    require(registry.binding == binding, 'stop_registry_binding')
    ops.guard()
    admission = registry.claim('stop')
    journal('stop_admitted', {'admission': admission, 'target': expected})
    fd = None
    result = {'study_id': binding['study_id'], 'signal_attempts': 0, 'exit_observed': False,
              'gpu_absence_independently_verified': None, 'replay_allowed': False,
              'status': 'stop_unknown_no_retry'}
    try:
        fd = ops.pin(expected['pid'])
        require(canonical(ops.identity(expected['pid'])) == canonical(expected), 'stop_pid_reuse_or_drift')
        require(not ops.exited(fd), 'stop_target_already_exited')
        ops.guard()
        journal('signal_intent', {'target_identity_sha256': sha(expected), 'signal': 'SIGTERM', 'attempts_max': 1})
        ops.guard()
        require(canonical(ops.identity(expected['pid'])) == canonical(expected), 'stop_identity_after_intent')
        result['signal_attempts'] = 1
        ops.send(fd)
        result['exit_observed'] = ops.wait(fd, 30)
        result['status'] = 'exit_observed_pending_independent_gpu_check' if result['exit_observed'] else 'stop_unknown_no_retry'
    finally:
        try:
            if fd is not None:
                ops.close(fd)
        finally:
            journal('stop_result', result)
    return result


class PidfdOperations:
    """Linux-only narrow effects. Identity reader and guard come from frozen entry."""
    def __init__(self, guard, identity_reader):
        self.guard, self.identity = guard, identity_reader

    def pin(self, pid):
        require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'pidfd_unavailable')
        return os.pidfd_open(pid, 0)

    def exited(self, fd):
        return self.wait(fd, 0)

    def send(self, fd):
        signal.pidfd_send_signal(fd, signal.SIGTERM, None, 0)

    def wait(self, fd, seconds):
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            return bool(selector.select(seconds))

    close = staticmethod(os.close)
