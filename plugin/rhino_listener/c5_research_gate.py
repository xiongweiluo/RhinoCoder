"""Signed C5 research calls over the retained durable Rhino atomic barrier.

Python 3.9 stdlib; no routes, key provisioning, approval creation or model.
The trusted Mac signer must first consume an owner-scoped permission; its
raw SQLite row/event chain must be independently audited after execution.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import time
from contextlib import closing

from .c5_research_native import READS, canonical, digest, require, validate_native_arguments

SHA = re.compile(r"[0-9a-f]{64}\Z")
REQUEST = re.compile(r"[A-Za-z0-9_-]{24,128}\Z")
KEYS = frozenset({"version", "request_id", "task_sha256", "owner_freeze_sha256", "expected",
                  "operation", "arguments", "consent_row_sha256", "expires_at"})


def signature(secret, payload):
    require(isinstance(secret, bytes) and len(secret) >= 32, "private handoff key required")
    return hmac.new(secret, canonical(payload).encode(), hashlib.sha256).hexdigest()


class ResearchGate:
    def __init__(self, backend, atomic_gate, secret, owner_freeze_sha256, *, task_sha256, max_writes, max_reads, clock=time.time):
        require(isinstance(owner_freeze_sha256, str) and SHA.fullmatch(owner_freeze_sha256), "owner freeze binding required")
        require(isinstance(task_sha256, str) and SHA.fullmatch(task_sha256), "single task scope required")
        require(type(max_writes) is int and 0 <= max_writes <= 12 and type(max_reads) is int and 0 <= max_reads <= 12, "bounded request policy required")
        backend.guard()
        self.backend, self.atomic, self.secret = backend, atomic_gate, secret
        self.owner_freeze = owner_freeze_sha256
        self.task_sha = task_sha256
        self.max_writes, self.max_reads, self.clock = max_writes, max_reads, clock
        self.blocked = False
        signature(secret, {})
        with closing(sqlite3.connect(self.atomic.path)) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS c5_read (request_id TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL, state TEXT NOT NULL, result_sha256 TEXT)")
            db.commit()

    def _payload(self, envelope):
        require(isinstance(envelope, dict) and set(envelope) == {"payload", "signature"}, "signed envelope required")
        try: payload = json.loads(canonical(envelope["payload"]))
        except (ValueError, TypeError, RecursionError): raise ValueError("invalid detached payload") from None
        require(isinstance(payload, dict) and set(payload) == KEYS and type(payload["version"]) is int
                and payload["version"] == 1, "payload version/keys differ")
        supplied = envelope["signature"]
        require(isinstance(supplied, str) and SHA.fullmatch(supplied)
                and hmac.compare_digest(supplied, signature(self.secret,payload)), "handoff signature rejected")
        require(isinstance(payload["request_id"], str) and REQUEST.fullmatch(payload["request_id"]), "request identity invalid")
        require(payload["task_sha256"] == self.task_sha
                and payload["owner_freeze_sha256"] == self.owner_freeze, "task/owner scope differs")
        expiry = payload["expires_at"]
        require(type(expiry) is int and self.clock() < expiry <= self.clock()+300, "expired/oversized handoff TTL")
        expected = payload["expected"]
        require(isinstance(expected, dict) and set(expected) == {"document_key", "revision", "scene_sha256"}
                and type(expected["revision"]) is int and expected["revision"] >= 0
                and all(isinstance(expected[k], str) and SHA.fullmatch(expected[k]) for k in ("document_key", "scene_sha256")), "invalid scene binding")
        validate_native_arguments(payload["operation"],payload["arguments"],self.backend.schemas)
        if payload["operation"] in READS:
            require(payload["consent_row_sha256"] is None, "read cannot impersonate a write permission")
        else:
            require(isinstance(payload["consent_row_sha256"], str) and SHA.fullmatch(payload["consent_row_sha256"]), "consumed permission row binding missing")
        return payload

    def execute(self, envelope):
        self.backend.guard()
        require(not self.blocked, "uncertain session blocked; never replay")
        payload = self._payload(envelope)
        expected, op, args = payload["expected"], payload["operation"], payload["arguments"]
        require(self.atomic.snapshot() == expected, "scene changed before signed call")
        # Resolve all untrusted aliases before any reservation or mutation.
        targets = ([args["object_id"]] if "object_id" in args else [])
        for key in ("object_ids", "input0_ids", "input1_ids"): targets += args.get(key, [])
        for alias in targets: self.backend.target(alias, write=op not in READS)
        key = hashlib.sha256(payload["request_id"].encode()).hexdigest()
        with closing(sqlite3.connect(self.atomic.path)) as db:
            db.row_factory = sqlite3.Row
            require(db.execute("SELECT count(*) FROM candidate_write WHERE state!='done'").fetchone()[0] == 0,
                    "outstanding write reservation requires manual review")
            require(db.execute("SELECT count(*) FROM c5_read WHERE state!='done'").fetchone()[0] == 0,
                    "outstanding read reservation requires manual review")
            # No cross read/write reuse of one request identity.
            require(db.execute("SELECT count(*) FROM candidate_write WHERE idempotency_key=?",(key,)).fetchone()[0] == 0
                    and db.execute("SELECT count(*) FROM c5_read WHERE request_id=?",(payload["request_id"],)).fetchone()[0] == 0,
                    "duplicate signed request; never replay")
            table = "c5_read" if op in READS else "candidate_write"
            maximum = self.max_reads if op in READS else self.max_writes
            require(db.execute("SELECT count(*) FROM "+table).fetchone()[0] < maximum, "scoped request budget exhausted")
        before = self.backend.readback()
        require(self.atomic.snapshot() == expected, "scene changed during pre-call readback")
        if op in READS:
            with closing(sqlite3.connect(self.atomic.path)) as db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("INSERT INTO c5_read VALUES(?,?,?,NULL)",(payload["request_id"],digest(payload),"reserved"))
                db.commit()
        try:
            if op in READS:
                result = self.backend.dispatch(op,args)
            else:
                result = self.atomic.execute(key,expected,op,args,self.backend.dispatch)
            after = self.backend.readback()
            self.backend.guard()
            actual = self.atomic.snapshot()
            if op in READS:
                require(before == after and actual == expected, "read mutated scene")
                with closing(sqlite3.connect(self.atomic.path)) as db:
                    db.execute("PRAGMA synchronous=FULL")
                    db.execute("UPDATE c5_read SET state='done',result_sha256=? WHERE request_id=?",(digest(result),payload["request_id"]))
                    db.commit()
                ledger = None
            else:
                with closing(sqlite3.connect(self.atomic.path)) as db:
                    db.row_factory = sqlite3.Row
                    rows = db.execute("SELECT * FROM candidate_write WHERE idempotency_key=?",(key,)).fetchall()
                require(len(rows) == 1 and rows[0]["state"] == "done" and rows[0]["result_sha256"] == digest(result), "write result/ledger differs")
                ledger = dict(rows[0])
            return {"status":"done", "payload":payload, "before":before, "after":after,
                    "before_state":expected, "after_state":actual, "result":result,
                    "result_sha256":digest(result), "ledger_row":ledger,
                    "permission_and_cleanup_independently_audited":False}
        except BaseException:
            self.blocked = True
            # Never automatically roll back, retry, reuse consent, recover a
            # removed key or call another write after uncertain native work.
            raise
