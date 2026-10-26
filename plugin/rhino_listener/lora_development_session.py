"""One UI-idle callback for bounded new headless fixtures, no autonomous start.

An expired slot or broken controller stops work and attempts only disposal of
its owned fixture. Idle cannot preempt a blocked native call; that uncertainty
must remain explicit, and no application-level kill is authorized here.
"""
import os
import time

from .c5_research_channel import publish_json, read_json
from .c5_research_native import digest, require


class DevelopmentSession:
    def __init__(self, host, state, runtime, *, attach, detach, work_guard, cleanup_guard, idle_allowed=lambda: True, clock=time.monotonic):
        self.host, self.state, self.runtime = host, state, runtime
        self.attach, self.detach, self.work_guard, self.cleanup_guard, self.clock = attach, detach, work_guard, cleanup_guard, clock
        self.idle_allowed = idle_allowed
        self.callback = self.tick  # Retain this exact delegate identity for removal.
        self.started, self.stopped, self.busy, self.slot_started = False, False, False, None
        self.released, self.ready = False, False

    def start(self):
        require(not self.started, 'one listener subscription only')
        publish_json(self.state, 'attach.claim.json', {'runtime_sha256': self.runtime})
        self.attach(self.callback)
        self.started = True

    def release(self):
        require(self.started and not self.released, 'entry return release only once')
        publish_json(self.state, 'entry-return-release.json', {'runtime_sha256': self.runtime})
        self.released = True

    def tick(self, sender=None, event=None):
        if self.busy or self.stopped: return
        self.busy = True
        try:
            if os.path.lexists(self.state / 'shutdown.request.json'):
                request = read_json(self.state, 'shutdown.request.json')
                require(request == {'runtime_sha256': self.runtime, 'action': 'shutdown'}, 'shutdown binding differs')
                self.finish('controller_shutdown'); return
            if not self.released or not self.idle_allowed(): return
            self.work_guard()
            if not self.ready:
                publish_json(self.state, 'host-ready.json', {'runtime_sha256': self.runtime, 'status': 'ready',
                    'existing_project_content_read': False, 'whole_host_byte_closure_claimed': False,
                    'entry_return_release_observed': True})
                self.ready = True
            if self.slot_started is not None:
                require(self.clock() - self.slot_started < 150, 'native slot deadline')
            name = 'request-%04d.json' % self.host.sequence
            if not os.path.lexists(self.state / name): return
            request = read_json(self.state, name)
            seq = self.host.sequence
            action = request['payload']['request']['action']
            if action == 'open': self.slot_started = self.clock()
            response = self.host.handle(request)
            publish_json(self.state, 'response-%04d.json' % seq, response)
            if action == 'stop' and self.host.current is None: self.slot_started = None
        except BaseException as exc:
            self.finish(type(exc).__name__)
        finally:
            self.busy = False

    def finish(self, reason):
        if self.stopped: return
        self.stopped = True  # No callback work even if removal fails.
        error, close, detached = None, None, False
        try:
            self.cleanup_guard()
            if self.host.current is not None and self.host.session is not None and not self.host.close_attempted:
                self.host.close_attempted = True
                close = self.host.session.close()
                require(close.get('fixture_registry_absent') is True, 'emergency fixture closure unknown')
                self.host.closed = True
            require(self.host.current is None or self.host.closed, 'fixture remains unverified')
        except BaseException as exc: error = type(exc).__name__
        try:
            self.detach(self.callback)
            detached = True
        except BaseException as exc: error = error or type(exc).__name__
        value = {'status': 'host_stopped' if error is None else 'host_cleanup_unknown', 'reason': reason,
            'runtime_sha256': self.runtime, 'close': close, 'exact_delegate_remove_returned': detached,
            'all_other_host_handlers_absent_claimed': False, 'error_type': error}
        publish_json(self.state, 'host-settlement.json', value)
        return value
