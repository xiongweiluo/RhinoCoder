"""Versioned, bounded research fixture lifecycle; never a product listener.

The injected backend owns UI-thread checks and exactly one disposable fixture.
CPU fakes exercise ordering, not evidence of an actual Rhino execution.
"""
from __future__ import annotations

from .research_safety import require, verify_final_active_capture


class ResearchLifecycle:
    def __init__(self, backend):
        self.backend = backend
        self.initial_sha256 = backend.active_digest()
        self.current = None
        self.pending = None
        self.seq = 1
        self.stopped = False
        self.close_attempted = False
        self.failed = False

    def handle(self, request):
        require(not self.stopped, "controller already stopped")
        require(isinstance(request, dict) and set(request) == {"version", "seq", "action", "fixture", "case_id"}
                and type(request["version"]) is int and request["version"] == 2
                and type(request["seq"]) is int and request["seq"] == self.seq
                and isinstance(request["case_id"], str) and 1 <= len(request["case_id"]) <= 64,
                "invalid research lifecycle request")
        self.backend.guard()
        action = request["action"]
        if action == "open":
            require(not self.failed and self.current is None and self.pending is None
                    and request["fixture"] == "empty", "research open conflict")
            require(self.backend.active_digest() == self.initial_sha256, "active document changed before open")
            # No retry if creation partly succeeds; backend must retain identity
            # for manual cleanup. This controller never guesses a session path.
            self.failed = True
            session_dir = self.backend.open_empty()
            self.current = (request["case_id"], session_dir)
            self.pending = request["case_id"]
            self.failed = False
            return None
        if action == "close":
            require(self.current is not None and self.pending is None and not self.close_attempted
                    and request["case_id"] == self.current[0] and request["fixture"] == "none",
                    "research close conflict or uncertain previous close")
            self.close_attempted = True
            case_id, session_dir = self.current
            before = self.backend.active_digest()
            # Same handle()/Rhino Idle callback, with no await between captures.
            closed_dir, key_removed = self.backend.close_known(session_dir)
            after = self.backend.active_digest()
            require(closed_dir == session_dir and key_removed is True, "closure identity/key unverified")
            capture = {
                "version": 1, "case_id": case_id, "session_dir": session_dir, "close_seq": self.seq,
                "initial_active_sha256": self.initial_sha256,
                "before_close_active_sha256": before, "after_close_active_sha256": after,
                "capture_scope": "same_ui_callback_before_and_after_fixture_close",
                "on_rhino_main_thread": True, "fixture_closed": True, "key_removed": True,
            }
            # Preserve capture even if active-content checks fail. Do not label
            # a closed fixture as a passed task, nor silently drop a failure.
            self.backend.publish_capture(capture)
            self.current = None
            self.seq += 1
            self.failed = True
            verify_final_active_capture(capture, case_id=case_id, session_dir=session_dir,
                                        initial_sha256=self.initial_sha256)
            self.failed = False
            self.close_attempted = False
            return {"status": "closed", "case_id": case_id, "session_dir": session_dir,
                    "key_removed": True, "final_active_capture": capture}
        require(action == "stop" and request["fixture"] == "none" and self.current is None
                and self.pending is None, "research stop with unknown/unclosed fixture")
        self.stopped = True
        self.backend.stop()
        self.seq += 1
        return {"status": "stopped", "case_id": request["case_id"],
                "active_sha256_at_stop": self.backend.active_digest(), "had_failure": self.failed}

    def finish_open(self):
        if self.pending is None:
            return None
        self.backend.guard()
        case_id, session_dir = self.current
        if not self.backend.ready_empty(session_dir):
            return None
        require(self.backend.active_digest() == self.initial_sha256, "active document changed during open")
        self.pending = None
        self.seq += 1
        return {"status": "opened", "case_id": case_id, "session_dir": session_dir,
                "fixture": "empty", "initial_active_sha256": self.initial_sha256}
