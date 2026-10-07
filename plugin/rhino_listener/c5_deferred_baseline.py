"""Pure one-use entry-return/Idle admission; no name exceptions or host import.

The separately frozen wrapper releases only AFTER run_path has returned and
restored its temporary modules. The first non-command Idle seals once and
publishes readiness. Never process a request on that same callback. A failed
seal is sticky; it cannot retry or silently resnapshot/expand a baseline.
"""
from .c5_research_native import require


class DeferredBaselineAdmission:
    def __init__(self, *, source_guard, seal, publish_ready, mark_failure, dispatch, publish_release=lambda:None):
        self.source_guard, self.seal, self.publish_ready = source_guard, seal, publish_ready
        self.mark_failure, self.dispatch = mark_failure, dispatch
        self.publish_release=publish_release
        self.state = 'await_entry_return'

    def release_after_entry_return(self):
        require(self.state == 'await_entry_return', 'entry-return release cannot repeat')
        self.state = 'releasing_once'
        try:
            self.source_guard()
            self.publish_release()
            self.state = 'await_first_idle'
        except BaseException as exc:
            self.state='failed'
            self.mark_failure(type(exc).__name__)
            raise

    def tick(self, *, in_command, sender=None, event=None):
        require(type(in_command) is bool, 'explicit host command state required')
        if in_command or self.state in {'await_entry_return', 'failed'}: return
        if self.state == 'await_first_idle':
            self.state = 'sealing_once'
            try:
                self.source_guard()
                self.seal()
                self.publish_ready()
                self.state = 'ready'
            except BaseException as exc:
                self.state = 'failed'
                self.mark_failure(type(exc).__name__)
            return  # Even a queued request cannot race baseline publication.
        require(self.state == 'ready', 'reentrant/unknown baseline state')
        self.dispatch(sender,event)
