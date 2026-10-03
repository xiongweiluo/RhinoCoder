"""Trusted Mac signer over retained R consent transactions, not an approval API.

No executable, Rhino transport, model, default product route or human grant.
The lifecycle owner must independently verify the exact owner/source/spec grant
before constructing this signer. A constructor argument is not that evidence.
Every formal receipt must still be independently checked against raw databases.
"""
from __future__ import annotations

import hashlib
import secrets
import time

from plugin.rhino_listener.c5_research_gate import SHA, signature
from plugin.rhino_listener.c5_research_native import READS, digest, require, validate_native_arguments
from training.c5_contract import parse_invocation, parse_selection
from training.c5_inventory import load_public_mcp_tools
from training.c5_rhino_adapter import step_input
from training.consent_candidate import DELEGATED_HEADLESS_SCOPE
from training.tool_controller_candidate import SceneState, task_sha256


class SceneView:
    """Trusted proxy: actual fixture state, never expected scoring state."""
    def __init__(self, atomic, semantic_scene):
        self.atomic, self.semantic_scene = atomic, semantic_scene

    def snapshot(self):
        before = self.atomic.snapshot()
        summary = self.semantic_scene()
        require(self.atomic.snapshot() == before, "scene changed during permission readback")
        return SceneState(before["revision"], before["scene_sha256"], summary)


class ResearchSigner:
    def __init__(self, store, scene, secret, owner_freeze_sha256, task, *, max_writes, max_reads, clock=time.time):
        require(isinstance(owner_freeze_sha256, str) and SHA.fullmatch(owner_freeze_sha256), "owner source/spec binding required")
        require(isinstance(task, str) and 0 < len(task) <= 4096, "bounded task required")
        require(type(max_writes) is int and 0 <= max_writes <= 12 and type(max_reads) is int and 0 <= max_reads <= 12, "bounded task policy required")
        signature(secret,{})
        self.store, self.scene, self.secret, self.task = store, scene, secret, task
        self.owner_freeze, self.clock = owner_freeze_sha256, clock
        self.max_writes, self.max_reads, self.reads = max_writes, max_reads, 0
        self.blocked = False
        with store._tx() as db:
            db.execute("CREATE TABLE IF NOT EXISTS c5_model_handoff (observation_sha256 TEXT PRIMARY KEY, state TEXT NOT NULL, request_id TEXT UNIQUE, payload_sha256 TEXT)")

    def issue(self, observed, *, schemas):
        """Reparse raw outputs; no expected tool/args, correction or retry.

        Zero-write task policies deny model-selected writes before permission
        preparation. Once consumption/signing starts, uncertainty blocks the
        signer permanently; a returned envelope permits one bounded dispatch.
        """
        require(not self.blocked, "uncertain signer blocked")
        require(isinstance(observed, dict) and observed.get("status") == "schema_valid_not_authorized"
                and observed.get("repair_count") == 0 and observed.get("dispatch_count") == 0, "strict original model observation required")
        calls = observed.get("calls")
        require(isinstance(calls, list) and len(calls) == 2
                and [c.get("stage") for c in calls] == ["selector","invocation"], "two-stage evidence required")
        for call in calls:
            require(call.get("parsed") is True and isinstance(call.get("raw"),str)
                    and call.get("output_sha256") == hashlib.sha256(call["raw"].encode()).hexdigest(), "raw output receipt differs")
        tools = load_public_mcp_tools()
        selected = parse_selection(calls[0]["raw"],tools)
        parsed = parse_invocation(calls[1]["raw"],selected,tools)
        require(parsed["name"] == observed.get("name") and parsed["arguments"] == observed.get("arguments"), "model output/parsed call differs")
        op, args = parsed["name"], parsed["arguments"]
        validate_native_arguments(op,args,schemas)
        before = self.scene.atomic.snapshot()
        current = self.scene.snapshot()
        require(self.scene.atomic.snapshot() == before == observed.get("scene_binding"), "model generation scene changed or unbound")
        rendered = step_input(self.task,current.summary)
        require(hashlib.sha256(rendered.encode()).hexdigest() == observed.get("user_step_sha256"), "model task/semantic scene input differs")
        link = None
        if op in READS:
            require(self.reads < self.max_reads, "task read policy exhausted")
        else:
            with self.store._tx() as db:
                count = db.execute("SELECT count(*) FROM consent_requests").fetchone()[0]
            require(count < self.max_writes, "task write policy exhausted")
        # No caller may continue after a partially prepared/consumed handoff.
        self.blocked = True
        observation_sha = digest({"user_step_sha256":observed["user_step_sha256"],
                                  "scene_binding":observed["scene_binding"],
                                  "outputs":[c["output_sha256"] for c in calls]})
        with self.store._tx() as db:
            require(db.execute("SELECT count(*) FROM c5_model_handoff WHERE observation_sha256=?",(observation_sha,)).fetchone()[0] == 0,
                    "model observation already reserved; never reissue")
            db.execute("INSERT INTO c5_model_handoff VALUES(?,'reserved',NULL,NULL)",(observation_sha,))
        if op in READS:
            row_sha = None
            request_id = secrets.token_urlsafe(24)
            expiry = int(self.clock()) + 120
        else:
            link = self.store.prepare(self.task,op,args,scene=self.scene,
                                      ttl_seconds=120,delegated_scope=DELEGATED_HEADLESS_SCOPE)
            require(self.store.approve_delegated_headless(link) == "approved", "delegated disposable permission rejected")
            state = self.store._consume(link,task=self.task,tool_name=op,arguments=args,scene=self.scene)
            row, _ = self.store.inspect(link)
            require(row["status"] == "consumed", "permission not consumed")
            require(self.scene.snapshot() == state, "scene changed after consumption")
            row_sha, request_id, expiry = digest(row), link.request_id, row["expires_at"]
        expected = self.scene.atomic.snapshot()
        if link is not None:
            require(expected["revision"] == row["scene_revision"] and expected["scene_sha256"] == row["scene_sha256"], "scene changed before signature")
        payload = {"version":1,"request_id":request_id,"task_sha256":task_sha256(self.task),
                   "owner_freeze_sha256":self.owner_freeze,"expected":expected,"operation":op,
                   "arguments":args,"consent_row_sha256":row_sha,"expires_at":expiry}
        envelope = {"payload":payload,"signature":signature(self.secret,payload)}
        if link is not None:
            with self.store._tx() as db:
                self.store._event(db,link.request_id,"signed_handoff_issued",digest(payload))
        else:
            self.reads += 1
        with self.store._tx() as db:
            db.execute("UPDATE c5_model_handoff SET state='issued',request_id=?,payload_sha256=? WHERE observation_sha256=? AND state='reserved'",
                       (request_id,digest(payload),observation_sha))
        self.blocked = False
        # The envelope is private; never export a signing key or capability.
        return envelope
