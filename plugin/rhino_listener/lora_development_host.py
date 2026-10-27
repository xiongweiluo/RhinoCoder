"""Bounded signed host dispatcher; native operations are lazily injected.

No effects on import or autonomous approval. The exact approved UI entry
creates this host, binds its source and subscribes one callback. Only new
headless fixtures may be owned. Cleanup does not grant another dispatch.
"""
from __future__ import annotations

import hmac

from .c5_research_channel import publish_json
from .c5_research_gate import signature
from .c5_research_native import CORE, READS, digest, require
from .lora_development_channel import STUDY, detached, host_response
from .lora_development_runtime import failure_record


def signed_request(secret, runtime, slot, sequence, request):
    p = {"runtime_sha256": runtime, "slot_id": slot, "sequence": sequence, "request": request}
    return detached({"payload": p, "signature": signature(secret, p)})


class DevelopmentHost:
    def __init__(self, *, state, runtime, native_views, schedule, secret, factory, guard, cleanup_guard,
                 operations=READS, messages_max=512, study=STUDY):
        self.state, self.runtime, self.views, self.schedule = state, runtime, detached(native_views), detached(schedule)
        self.secret, self.factory, self.guard, self.cleanup_guard = secret, factory, guard, cleanup_guard
        self.sequence, self.opened = 1, []
        self.current, self.session = None, None
        self.blocked, self.closed, self.stopped = False, False, False
        self.close_attempted = False
        require(frozenset(operations) in {READS, CORE} and type(messages_max) is int
                and messages_max > 0, 'explicit bounded host contract required')
        self.operations, self.messages_max = frozenset(operations), messages_max
        self.study = study

    def handle(self, envelope):
        envelope = detached(envelope)
        require(not self.stopped and set(envelope) == {"payload", "signature"}, "inactive or invalid host channel")
        p = envelope['payload']
        require(type(p) is dict and set(p) == {'runtime_sha256', 'slot_id', 'sequence', 'request'}
                and p['runtime_sha256'] == self.runtime and type(p['sequence']) is int
                and p['sequence'] == self.sequence and self.sequence <= self.messages_max,
                "host runtime/sequence/cap differs")
        require(type(envelope['signature']) is str and hmac.compare_digest(signature(self.secret, p), envelope['signature']),
                "host request signature differs")
        slot, request, seq = p['slot_id'], p['request'], self.sequence
        require(slot in self.views and type(request) is dict and request.get('action') in
                {'open', 'capture', 'execute', 'close', 'stop'}, "unapproved host action or slot")
        action = request['action']
        require(set(request) == ({'action', 'envelope'} if action == 'execute' else {'action'}), "host request fields differ")
        # Persist intent before all possible native effects; never replay it.
        publish_json(self.state, 'host-%04d.request.json' % seq, envelope)
        self.sequence += 1
        try:
            if action in {'close', 'stop'}: self.cleanup_guard()
            else:
                require(not self.blocked, "uncertain host blocks work")
                self.guard()
            value = self._action(slot, action, request)
        except BaseException as exc:
            self.blocked = True
            value = {'status': 'host_failure_no_retry', 'action': action, 'error_type': type(exc).__name__,
                     'effect_state': 'unknown', 'cleanup_verified': False, 'failure': failure_record(exc, 'host_' + action)}
        response = host_response(self.secret, self.runtime, slot, seq, request, value, study=self.study)
        publish_json(self.state, 'host-%04d.response.json' % seq, response)
        return response

    def _action(self, slot, action, request):
        if action == 'open':
            require(self.current is None and len(self.opened) < len(self.schedule)
                    and self.schedule[len(self.opened)]['slot_id'] == slot, "fixed host slot order differs")
            self.current, self.closed, self.close_attempted = slot, False, False
            self.opened.append(slot)
            # Factory creates nothing until .open(); retaining the object first
            # permits cleanup after a partially created/seeded fixture.
            self.session = self.factory(self.views[slot], self.runtime, self.secret)
            return self.session.open()
        require(slot == self.current and self.session is not None, "wrong owned fixture")
        if action == 'capture':
            require(not self.closed and not self.close_attempted, "capture after closure")
            return self.session.capture()
        if action == 'execute':
            require(not self.closed and not self.close_attempted, "execute after closure")
            p = request['envelope']['payload']
            require(p['operation'] in self.operations, "operation outside frozen host contract")
            return self.session.execute(request['envelope'])
        if action == 'close':
            require(not self.close_attempted, "close already attempted; no replay")
            self.close_attempted = True
            value = self.session.close()
            require(value.get('status') == 'closed' and value.get('fixture_registry_absent') is True,
                    "owned fixture closure unverified")
            self.closed = True
            return value
        require(self.closed, "cannot stop unclosed fixture")
        value = self.session.finish()
        require(value.get('status') == 'stopped', "fixture accounting stop unverified")
        self.current, self.session = None, None
        return {**value, 'host_blocked': self.blocked}

    def finish(self):
        self.cleanup_guard()
        require(self.current is None, "unclosed fixture remains")
        self.stopped = True
        return {'status': 'host_stopped', 'opened_slots': self.opened, 'blocked': self.blocked,
                'owned_fixture_remaining': False}


class RhinoSession:
    """Real implementation; only the separately approved UI entry calls it."""
    def __init__(self, plan, runtime, secret, *, directory, schemas, guard, fingerprint_limit=0):
        self.plan, self.runtime, self.secret = plan, runtime, secret
        self.directory, self.schemas, self.guard = directory, schemas, guard
        self.doc = self.backend = self.gate = None
        self.close_attempted = False
        self.fingerprint_limit, self.fingerprint_sequence = fingerprint_limit, 0

    def scene_digest(self):
        from .candidate_atomic_gate import rhino_scene_digest, rhino_scene_fingerprint
        if not self.fingerprint_limit:
            return rhino_scene_digest(self.doc)
        require(self.fingerprint_sequence < self.fingerprint_limit, 'fingerprint evidence capacity reached')
        value = rhino_scene_fingerprint(self.doc)
        self.fingerprint_sequence += 1
        publish_json(self.directory, 'fingerprint-%04d.json' % self.fingerprint_sequence,
                     {'sequence': self.fingerprint_sequence, **value})
        return value['scene_sha256']

    def open(self):
        import Rhino
        from .candidate_atomic_gate import RhinoAtomicGate
        from .c5_research_gate import ResearchGate
        from .c5_research_native import validate_native_arguments
        from .lora_development_native import DevelopmentDoc
        self.guard()
        require(Rhino.RhinoApp.IsOnMainThread and self.doc is None, "new UI-thread fixture required")
        self.doc = Rhino.RhinoDoc.CreateHeadless(None)
        require(self.doc is not None, "fixture creation unknown")
        self.doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
        self.doc.ModelAbsoluteTolerance = 0.000001
        self.backend = DevelopmentDoc(self.doc, self.schemas)
        publish_json(self.directory, 'created.json', {'serial': self.backend.serial, 'headless': True,
                     'runtime_sha256': self.runtime, 'existing_document_content_read': False})
        for index, row in enumerate(self.plan['fixture_recipe']):
            self.guard()
            validate_native_arguments(row['operation'], row['arguments'], self.schemas)
            publish_json(self.directory, 'seed-%02d.claim.json' % index, row)
            value = self.backend.dispatch(row['operation'], row['arguments'])
            publish_json(self.directory, 'seed-%02d.result.json' % index, {'result': value})
        atomic = RhinoAtomicGate(self.directory / 'fixture.sqlite3', str(self.backend.serial),
                                self.scene_digest, create_ledger=True)
        self.gate = ResearchGate(self.backend, atomic, self.secret, self.runtime,
            task_sha256=self.plan['task_sha256'], max_reads=self.plan['max_reads'], max_writes=self.plan['max_writes'])
        return {'status': 'opened', 'fixture_serial': self.backend.serial}

    def capture(self):
        self.guard()
        before = self.gate.atomic.snapshot()
        native = self.backend.readback()
        require(before == self.gate.atomic.snapshot(), "unstable actual capture")
        return {'status': 'captured', 'state': before, 'native': native}

    def execute(self, envelope):
        self.guard()
        return self.gate.execute(envelope)

    def close(self):
        import Rhino
        require(not self.close_attempted and Rhino.RhinoApp.IsOnMainThread, "one UI-thread closure attempt")
        self.close_attempted = True
        if self.backend is not None:
            return self.backend.close()
        # Opening can fail before backend construction. Only dispose the exact
        # unsaved headless reference returned by this session's CreateHeadless.
        if self.doc is not None:
            require(bool(self.doc.IsHeadless) and not self.doc.Path, "owned partial fixture differs")
            serial = int(self.doc.RuntimeSerialNumber)
            self.doc.Dispose()
            require(Rhino.RhinoDoc.FromRuntimeSerialNumber(serial) is None, "partial fixture still registered")
        return {'status': 'closed', 'fixture_registry_absent': True, 'partial_preparation': True}

    def finish(self):
        require(self.close_attempted and (self.backend is None or self.backend.closed), "fixture not closed")
        # Read-only snapshot of this new fixture's ledger, not any old study.
        import sqlite3
        from contextlib import closing
        rows = {'candidate_write': [], 'c5_read': []}
        if self.gate is not None:
            with closing(sqlite3.connect(self.gate.atomic.path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA query_only=ON')
                require(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', "new fixture ledger corrupt")
                rows = {name: [dict(r) for r in db.execute('SELECT * FROM ' + name)] for name in rows}
            require(len(rows['candidate_write']) <= self.plan['max_writes'], "unexpected model write ledger")
        return {'status': 'stopped', 'ledger': rows, 'fixture_registry_absent': True}
