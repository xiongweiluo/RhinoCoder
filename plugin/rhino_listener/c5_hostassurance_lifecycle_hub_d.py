"""D-only completion timing sidecars. Inert import; no alternate execution."""
import time
from .c5_hostassurance_development_hub import HostAwareDevelopmentHub, CleanupAwareBridge
from .c5_lifecycle_deadlines import PhaseClock
from .c5_research_channel import publish_json, read_json
from .c5_research_native import digest, require


def finish_service(directory, prefix, seq, phase, freeze_sha, *, valid=True):
    # Original reply is atomically published first; controller MUST await
    # this separate post-publication record, so a late done is not accepted.
    request = read_json(directory, prefix+"request-%04d.json" % seq)
    response = read_json(directory, prefix+"response-%04d.json" % seq)
    value = phase.receipt(valid=valid, role="hub" if prefix else "native", sequence=seq,
        runtime_freeze_sha256=freeze_sha, request_sha256=digest(request), response_sha256=digest(response))
    publish_json(directory, prefix+"service-time-%04d.json" % seq, value)
    return value["completed_in_budget"]


class LifecycleBridgeD(CleanupAwareBridge):
    def __init__(self, *args, lifecycle, **kwargs):
        self.lifecycle, self.service_phase, self.settle_phase = lifecycle, None, None
        self.timing_invalid = False
        super().__init__(*args, **kwargs)

    def _source(self):
        if self.service_phase is None:
            return super()._source()
        # No cache/name exceptions. Measure full unchanged guard boundaries.
        return self.service_phase.call("source", super()._source)

    def handle(self, request):
        value = super().handle(request)
        if self.pending is not None:
            self.settle_phase = PhaseClock(self.lifecycle["settle_seconds"], clock=self.monotonic)
            self.pending["deadline"] = self.settle_phase.start+self.settle_phase.cap
        return value

    def settle(self):
        require(self.pending is not None and self.settle_phase is not None, "known D settling phase required")
        phase = self.settle_phase
        # Both entry AND completion of expensive guards/capture are checked.
        phase.call("source", self._source)
        capture = phase.call("capture", self._capture)
        current = digest(capture)
        self.pending["samples"].append(capture)
        self.pending["stable"] = self.pending["stable"]+1 if current == self.pending["last"] else 1
        self.pending["last"] = current
        phase.check("sample-finished")
        if self.pending["stable"] < 3:
            return None
        raw = self.pending["receipt"]
        final = {**raw, "after": capture["native"], "after_state": capture["state"],
            "immediate_after": raw["after"], "immediate_after_state": raw["after_state"],
            "settling_samples": self.pending["samples"], "stable_idle_samples": 3}
        phase.check("before-final-response")
        publish_json(self.directory, self.pending["response_name"], final)
        phase.check("after-final-response")
        request = read_json(self.directory, "request-%04d.json" % self.seq)
        timing = phase.receipt(role="settle", sequence=self.seq,
            runtime_freeze_sha256=self.gate.owner_freeze, request_sha256=digest(request), response_sha256=digest(final))
        require(timing["completed_in_budget"] is True, "complete D settle phase expired")
        publish_json(self.directory, "settle-time-%04d.json" % self.seq, timing)
        phase.check("after-settle-timing-publish")
        self.pending = None
        return final

    def tick(self, sender=None, event=None):
        if self.stopped:
            return
        import Rhino
        if getattr(Rhino.RhinoApp, "InCommand", False):
            return
        seq = self.seq
        if self.pending is None and not (self.directory/("request-%04d.json" % seq)).exists():
            return
        if self.service_phase is None:
            self.service_phase = PhaseClock(self.lifecycle["native_ack_seconds"], clock=self.monotonic)
            self.timing_invalid = False
        phase = self.service_phase
        try:
            super().tick(sender, event)
        except BaseException:
            self.timing_invalid, self.blocked = True, True
            raise
        finally:
            if self.seq != seq:
                # A post-publication deadline error must not turn the
                # already-written done payload into a timely acceptance.
                if not finish_service(self.directory, "", seq, phase, self.gate.owner_freeze,
                                      valid=not self.timing_invalid):
                    self.blocked = True
                self.service_phase, self.settle_phase = None, None


class HostAwareLifecycleHubD(HostAwareDevelopmentHub):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lifecycle = self.spec["lifecycle_protocol"]
        self.bridge_factory = lambda *a, **k: LifecycleBridgeD(*a, lifecycle=self.lifecycle,
            cleanup_source=self.cleanup_guard, assurance=self.assurance, **k)
        self.monotonic = time.monotonic

    def tick(self, sender=None, event=None):
        if self.stopped:
            return
        import Rhino
        if getattr(Rhino.RhinoApp, "InCommand", False):
            return
        seq = self.seq
        if not (self.state/("hub-request-%04d.json" % seq)).exists():
            return
        phase = PhaseClock(self.lifecycle["native_ack_seconds"], clock=self.monotonic)
        super().tick(sender, event)
        if self.seq != seq and not finish_service(self.state, "hub-", seq, phase, digest(self.freeze)):
            self.blocked = True
