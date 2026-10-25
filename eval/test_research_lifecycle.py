from __future__ import annotations

import pytest

from plugin.rhino_listener.research_lifecycle import ResearchLifecycle
from plugin.rhino_listener.research_safety import ResearchSafetyError


class Backend:
    def __init__(self):
        self.digest = "a"*64
        self.events = []
        self.ready = True
        self.close_error = False
        self.change_on_close = False
        self.capture = None

    def guard(self): self.events.append("guard")
    def active_digest(self):
        self.events.append("digest")
        return self.digest
    def open_empty(self):
        self.events.append("open")
        return "/tmp/private-session"
    def ready_empty(self, directory): return self.ready
    def close_known(self, directory):
        self.events.append("close")
        if self.close_error: raise TimeoutError("close uncertain")
        if self.change_on_close: self.digest = "b"*64
        return directory, True
    def publish_capture(self, capture): self.capture = capture
    def stop(self): self.events.append("stop")


def req(seq, action, *, case="RSDEV-ONE", fixture=None):
    return {"version": 2, "seq": seq, "action": action, "case_id": case,
            "fixture": ("empty" if action == "open" else "none") if fixture is None else fixture}


def opened():
    backend = Backend()
    lifecycle = ResearchLifecycle(backend)
    assert lifecycle.handle(req(1, "open")) is None
    assert lifecycle.finish_open()["status"] == "opened"
    return backend, lifecycle


def test_same_callback_close_raw_capture_and_stop():
    backend, lifecycle = opened()
    backend.events.clear()
    closed = lifecycle.handle(req(2, "close"))
    assert backend.events == ["guard", "digest", "close", "digest"]
    assert closed["final_active_capture"] == backend.capture
    assert lifecycle.handle(req(3, "stop"))["had_failure"] is False


def test_timeout_close_is_never_retried_or_stopped_as_closed():
    backend, lifecycle = opened()
    backend.close_error = True
    with pytest.raises(TimeoutError): lifecycle.handle(req(2, "close"))
    with pytest.raises(ResearchSafetyError): lifecycle.handle(req(2, "close"))
    with pytest.raises(ResearchSafetyError): lifecycle.handle(req(2, "stop"))
    assert backend.events.count("close") == 1


def test_active_drift_retains_raw_failed_capture():
    backend, lifecycle = opened()
    backend.change_on_close = True
    with pytest.raises(ResearchSafetyError): lifecycle.handle(req(2, "close"))
    assert backend.capture["before_close_active_sha256"] != backend.capture["after_close_active_sha256"]
    assert lifecycle.failed
    assert lifecycle.handle(req(3, "stop"))["had_failure"]


@pytest.mark.parametrize("payload", [req(1, "open", fixture="seeded_one"), req(True, "open"),
                                     {**req(1, "open"), "extra": True}, req(2, "open")])
def test_invalid_requests_do_not_open_fixture(payload):
    backend = Backend()
    lifecycle = ResearchLifecycle(backend)
    with pytest.raises(ResearchSafetyError): lifecycle.handle(payload)
    assert "open" not in backend.events


def test_late_open_requires_completion_before_close_or_stop():
    backend = Backend()
    backend.ready = False
    lifecycle = ResearchLifecycle(backend)
    lifecycle.handle(req(1, "open"))
    assert lifecycle.finish_open() is None
    with pytest.raises(ResearchSafetyError): lifecycle.handle(req(1, "close"))
    with pytest.raises(ResearchSafetyError): lifecycle.handle(req(1, "stop"))
    backend.ready = True
    assert lifecycle.finish_open()["case_id"] == "RSDEV-ONE"
    with pytest.raises(ResearchSafetyError): lifecycle.handle(req(2, "close", case="OTHER"))
