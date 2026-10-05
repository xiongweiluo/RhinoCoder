"""Forty fresh headless slots; only the frozen owner entry attaches this hub.

Fixture construction is separately claimed/audited before model permissions.
Partial construction retains the fixture and blocks the hub; no second open.
"""
from __future__ import annotations

import hashlib
import hmac
import time

from .c5_formal20_scope import STUDY_ID, native_plans
from .c5_research_channel import publish_json, read_json, remove_private_key
from .c5_research_gate import ResearchGate, signature
from .c5_research_native import NativeDoc, require, digest, active_content_digest, validate_native_arguments
from .candidate_atomic_gate import RhinoAtomicGate, rhino_scene_digest
from .c5_research_session import IdleBridge


class FormalHub:
    def __init__(self, state, spec, freeze, plans, schemas, source, active, *, clock=time.time):
        self.state, self.spec, self.freeze, self.plans = state, spec, freeze, native_plans(plans)
        require(digest(plans['slot_order']) == spec['slot_order_sha256'], 'formal private order commitment differs')
        self.schemas, self.source, self.active = schemas, source, active
        self.active_serial, self.initial_active = int(active.RuntimeSerialNumber), active_content_digest(active)
        self.secret = bytes.fromhex(read_json(state, 'hub.key')['key_hex'])
        self.clock, self.seq = clock, 1
        self.child, self.fixture = None, None
        self.opened, self.control_ids = [], set()
        self.blocked, self.stopped, self.attached = False, False, False
        self._callback = self.tick

    def guard(self):
        import Rhino
        require(self.source() == self.freeze['source_inventory_sha256'], 'formal source closure drift')
        require(Rhino.RhinoApp.IsOnMainThread and Rhino.RhinoDoc.ActiveDoc is not None
            and int(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber) == self.active_serial
            and active_content_digest(self.active) == self.initial_active, 'formal active content changed')

    def attach(self):
        import Rhino
        self.guard()
        require(not self.attached and not self.stopped, 'formal hub already attached/stopped')
        publish_json(self.state, 'hub-bootstrap.json', {'study_id': STUDY_ID,
            'runtime_freeze_sha256': digest(self.freeze), 'source_sha256': self.freeze['source_inventory_sha256'],
            'native_plans_sha256': digest(self.plans), 'active_serial': self.active_serial,
            'active_sha256': self.initial_active})
        Rhino.RhinoApp.Idle += self._callback
        self.attached = True

    def handle(self, envelope):
        self.guard()
        require(isinstance(envelope, dict) and set(envelope) == {'payload', 'signature'}, 'exact signed formal hub control')
        p = envelope['payload']
        require(isinstance(p, dict) and set(p) == {'version', 'request_id', 'action', 'slot_id', 'owner_freeze_sha256', 'expires_at'}
            and type(p['version']) is int and p['version'] == 1 and p['action'] in {'open', 'stop'}
            and p['owner_freeze_sha256'] == digest(self.freeze)
            and isinstance(p['request_id'], str) and 16 <= len(p['request_id']) <= 128
            and p['request_id'] not in self.control_ids and type(p['expires_at']) is int
            and 0 < p['expires_at'] - self.clock() <= 120 and isinstance(envelope['signature'], str)
            and hmac.compare_digest(signature(self.secret, p), envelope['signature']), 'formal hub control rejected')
        self.control_ids.add(p['request_id'])
        if p['action'] == 'stop':
            current_closed = self.fixture is None or (self.child is not None
                and self.child.gate.backend.doc is self.fixture and self.child.stopped and self.child.gate.backend.closed)
            require(p['slot_id'] is None and current_closed, 'formal live/unbridged fixture needs reconciliation')
            import Rhino
            unused = []
            for slot in self.plans['slot_order']:
                if slot['slot_id'] not in self.opened:
                    proof = remove_private_key(self.state / slot['slot_id'], 'handoff.key')
                    require(proof['actual_absence_checked'], 'formal unused key absence missing')
                    unused.append(slot['slot_id'])
            hub_key = remove_private_key(self.state, 'hub.key')
            Rhino.RhinoApp.Idle -= self._callback
            self.attached, self.stopped = False, True
            self.guard()
            value = {'status': 'hub_stopped', 'opened_slots': list(self.opened), 'unused_keys_removed': unused,
                'hub_key_absence': hub_key, 'hook_removed_in_same_callback': True, 'active_serial': self.active_serial,
                'active_sha256': self.initial_active, 'source_sha256': self.freeze['source_inventory_sha256'],
                'had_failure': self.blocked}
            publish_json(self.state, 'hub-stop.json', value)
            return value
        require(not self.blocked and self.clock() < self.spec['model_generation_cutoff_epoch'], 'formal hub blocked/past cutoff')
        require(self.child is None or self.child.stopped, 'previous formal fixture not stopped')
        order = self.plans['slot_order']
        require(len(self.opened) < 40 and p['slot_id'] == order[len(self.opened)]['slot_id'], 'formal forty-slot order differs')
        slot = p['slot_id']; directory = self.state / slot; plan = self.plans['plans'][slot]
        for row in plan['fixture_recipe']:
            validate_native_arguments(row['operation'], row['arguments'], self.schemas)
        publish_json(self.state, slot + '.engine-started.claim.json', {'study_id': STUDY_ID, 'slot_id': slot,
            'runtime_freeze_sha256': digest(self.freeze), 'replay_allowed': False})
        import Rhino
        fixture = Rhino.RhinoDoc.CreateHeadless(None)
        require(fixture is not None, 'formal headless open unknown')
        self.fixture = fixture
        self.opened.append(slot)
        publish_json(directory, 'engine-created.json', {'fixture_serial': int(fixture.RuntimeSerialNumber),
            'active_serial': self.active_serial, 'runtime_freeze_sha256': digest(self.freeze),
            'rhino_version': str(Rhino.RhinoApp.Version), 'python_major_minor': [3, 9], 'rhino_major': 8})
        fixture.ModelUnitSystem = Rhino.UnitSystem.Millimeters
        fixture.ModelAbsoluteTolerance = 0.000001
        backend = NativeDoc(fixture, self.active, self.schemas)
        for index, row in enumerate(plan['fixture_recipe']):
            # Seed operations are authorized fixture setup, not model writes.
            publish_json(directory, 'seed-%02d.claim.json' % index, {'index': index, 'operation': row['operation'],
                'arguments': row['arguments'], 'runtime_freeze_sha256': digest(self.freeze), 'replay_allowed': False})
            before = backend.readback()
            result = backend.dispatch(row['operation'], row['arguments'])
            after = backend.readback()
            publish_json(directory, 'seed-%02d.result.json' % index, {'index': index, 'before': before,
                'after': after, 'result': result, 'operation': row['operation'], 'arguments': row['arguments']})
        atomic = RhinoAtomicGate(directory / 'fixture.sqlite3', str(fixture.RuntimeSerialNumber),
            lambda: rhino_scene_digest(fixture), create_ledger=True)
        secret = bytes.fromhex(read_json(directory, 'handoff.key')['key_hex'])
        gate = ResearchGate(backend, atomic, secret, digest(self.freeze),
            task_sha256=hashlib.sha256(plan['task_text'].encode()).hexdigest(),
            max_writes=plan['max_writes'], max_reads=plan['max_reads'])
        self.child = IdleBridge(gate, directory, key_name='handoff.key',
            source_sha256=self.freeze['source_inventory_sha256'], guard_source=self.source, max_messages=128)
        self.child.attach()
        return {'status': 'slot_opened', 'slot_id': slot, 'fixture_serial': int(fixture.RuntimeSerialNumber)}

    def tick(self, sender=None, event=None):
        if self.stopped: return
        import Rhino
        if getattr(Rhino.RhinoApp, 'InCommand', False): return
        name = 'hub-request-%04d.json' % self.seq
        if not (self.state / name).exists(): return
        try:
            require(self.seq <= 41, 'formal hub controls exhausted')
            value = self.handle(read_json(self.state, name))
        except BaseException as exc:
            self.blocked = True
            value = {'status': 'hub_failed_no_retry', 'error_type': type(exc).__name__,
                'manual_reconciliation_required': True}
        publish_json(self.state, 'hub-response-%04d.json' % self.seq, value)
        self.seq += 1
