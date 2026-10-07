"""Inert, injected logical timing. No CLR preemption or execution authority."""
import math
import time


def require(ok, message):
    if not ok:
        raise ValueError(message)


class PhaseClock:
    def __init__(self, seconds, *, clock=time.monotonic):
        require(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 180,
                "bounded finite logical phase required")
        self.clock, self.cap = clock, seconds
        self.start = clock()
        require(type(self.start) in (int, float) and math.isfinite(self.start), "finite monotonic start required")
        self.last, self.events = self.start, [{"event": "started", "elapsed_seconds": 0.0}]

    def mark(self, label, *, record=True):
        now = self.clock()
        require(type(now) in (int, float) and math.isfinite(now) and now >= self.last,
                "monotonic clock invalid")
        require(type(label) is str and label.isascii() and 0 < len(label) <= 64
                and (not record or len(self.events) < 64), "bounded phase event required")
        self.last = now
        if record:
            self.events.append({"event": label, "elapsed_seconds": now-self.start})
        return now-self.start

    def check(self, label, *, record=True):
        require(self.mark(label, record=record) < self.cap, "logical phase expired; no replay or hard-preemption claim")

    def call(self, label, operation):
        self.check(label+"-enter")
        value = operation()
        self.check(label+"-exit")
        return value

    def receipt(self, *, final_event="response-written", valid=True, **binding):
        elapsed = self.mark(final_event)
        return {**binding, "version": 1, "cap_seconds": self.cap, "elapsed_seconds": elapsed,
                "events": list(self.events), "completed_in_budget": valid is True and elapsed < self.cap,
                "hard_preemption_proven": False, "execution_success_claimed": False}
