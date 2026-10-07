"""D-only full decode/validation timing; old framing code stays untouched."""
from training.c5_startup_transport import StartupReadyPipe
from training.c5_model_transport import validate_response
from plugin.rhino_listener.c5_lifecycle_deadlines import PhaseClock
from plugin.rhino_listener.c5_research_native import digest, require


class LifecycleReadyPipe(StartupReadyPipe):
    def __init__(self, *args, model_identities, **kwargs):
        super().__init__(*args, **kwargs)
        self.identities, self.last_phase, self.phase_seq = model_identities, None, 0

    def wait_ready(self):
        if self.blocked or self.ready:
            self.blocked = True
            require(False, "D startup already spent or unresolved")
        phase = PhaseClock(self.startup_timeout, clock=self.clock)
        try:
            value = super().wait_ready()
            phase.check("ready-full-validation")
            self.last_phase = phase.receipt(final_event="response-validated", role="startup", sequence=0,
                runtime_freeze_sha256=self.expected["runtime_freeze_sha256"],
                request_sha256=digest(None), response_sha256=digest(value))
            require(self.last_phase["completed_in_budget"] is True, "startup full validation expired")
            return value
        except BaseException:
            self.blocked = True
            raise

    def exchange(self, sent):
        if self.blocked or not self.ready:
            self.blocked = True
            require(False, "D model channel not ready or unresolved")
        phase = PhaseClock(self.timeout, clock=self.clock)
        try:
            value = super().exchange(sent)
            # Validator returns an observation projection; do not replace
            # the original raw frame with it or silently alter the wire.
            validate_response(value, sent, self.identities[sent["route"]])
            phase.check("model-full-validation")
            self.phase_seq += 1
            self.last_phase = phase.receipt(final_event="response-validated", role="model", sequence=self.phase_seq,
                runtime_freeze_sha256=sent["runtime_freeze_sha256"],
                request_sha256=digest(sent), response_sha256=digest(value))
            require(self.last_phase["completed_in_budget"] is True, "model full validation expired")
            return value
        except BaseException:
            self.blocked = True
            raise
