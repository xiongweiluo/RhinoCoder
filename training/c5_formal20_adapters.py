"""Real private-channel native and SSH model adapters. Lazy field effects.

Constructors grant no authority. The frozen owner-side entry verifies scope
and creates started before preparation. Tests inject synthetic channels/pipes.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import subprocess
import time
from pathlib import Path

from plugin.rhino_listener.c5_formal20_scope import (
    STUDY_ID, REMOTE_SOURCE, REMOTE_ENV, SSH_SOCKET, SSH_PORT, SSH_KNOWN_HOSTS,
    SSH_KNOWN_HOSTS_SHA, native_plans,
)
from plugin.rhino_listener.c5_research_channel import publish_json, read_json, remove_private_key
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_formal20_runtime import hashed_model_plans
from training.c5_model_transport import request, FramedPipe, rebind_observation
from training.c5_modelbridge_joint_audit import semantic
from training.c5_modelbridge_runtime import file_sha
from training.c5_research_permission import ResearchSigner, SceneView
from training.consent_candidate import ConsentStore
from training.c5_inventory import load_public_mcp_tools


class NativeChannel:
    def __init__(self, directory, secret, freeze_sha, task=None, *, hub=False, guard=lambda: None,
                 pump=lambda: None, clock=time.monotonic):
        self.directory, self.secret, self.freeze, self.task, self.hub = directory, secret, freeze_sha, task, hub
        self.guard, self.pump, self.clock = guard, pump, clock
        self.seq, self.unresolved = 1, False

    def exchange(self, message):
        self.guard()
        require(not self.unresolved and self.seq <= (41 if self.hub else 128), 'formal unresolved/exhausted channel')
        self.unresolved = True
        prefix = 'hub-' if self.hub else ''
        publish_json(self.directory, prefix + 'request-%04d.json' % self.seq, message)
        deadline = self.clock() + 25
        name = prefix + 'response-%04d.json' % self.seq
        while not (self.directory / name).exists():
            require(self.clock() < deadline, 'formal unknown native acknowledgement')
            self.pump()
            time.sleep(0.01)
        value = read_json(self.directory, name)
        self.seq += 1
        self.unresolved = False
        return value

    def control(self, action, slot=None):
        p = {'version': 1, 'request_id': secrets.token_urlsafe(24), 'action': action,
             'owner_freeze_sha256': self.freeze, 'expires_at': int(time.time()) + 120}
        if self.hub:
            p['slot_id'] = slot
            return self.exchange({'payload': p, 'signature': signature(self.secret, p)})
        p['task_sha256'] = hashlib.sha256(self.task.encode()).hexdigest()
        return self.exchange({'kind': 'control', 'envelope': {'payload': p, 'signature': signature(self.secret, p)}})


class ActualScene:
    def __init__(self, channel, expected, record): self.channel, self.expected, self.record = channel, expected, record
    def _capture(self):
        actual = self.channel.control('capture')
        require(actual['status'] == 'captured' and actual['state'] == self.expected['state']
            and actual['native'] == self.expected['native'], 'formal actual scene drift while signing')
        self.record['signing_captures'].append(actual)
        return actual
    def snapshot(self): return self._capture()['state']
    def semantic_scene(self): return semantic(self._capture()['native'])


def database_backup(directory, name):
    """Consistent read-only SQLite snapshot after the slot is stopped."""
    source, target = directory / (name + '.sqlite3'), directory / (name + '-audit.sqlite3')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as src:
        src.execute('PRAGMA query_only=ON')
        with sqlite3.connect(target) as dst:
            src.backup(dst)
            require(dst.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'formal backup invalid')
    return file_sha(target)


class NativeAdapter:
    def __init__(self, state, spec, freeze, *, guard, channel_factory=NativeChannel, attach_wait=None):
        self.state, self.spec, self.freeze, self.guard = state, spec, freeze, guard
        self.channel_factory, self.attach_wait = channel_factory, attach_wait
        self.channels, self.signers, self.opened, self.keys = {}, {}, [], []
        self.hub, self.plans, self.current = None, None, None

    def prepare(self, plans, *, freeze_sha256):
        self.guard()
        require(freeze_sha256 == digest(self.freeze) and read_json(self.state, 'formal20.started.json')['runtime_freeze_sha256']
            == freeze_sha256, 'formal started scope missing')
        self.plans = native_plans(plans)
        require(digest(plans['slot_order']) == self.spec['slot_order_sha256'], 'formal prepared order drift')
        publish_json(self.state, 'native-plans.json', plans)
        publish_json(self.state, 'hub.key', {'key_hex': secrets.token_bytes(32).hex()})
        self.keys.append((self.state, 'hub.key'))
        for slot in plans['slot_order']:
            directory = self.state / slot['slot_id']
            directory.mkdir(mode=0o700)
            publish_json(directory, 'handoff.key', {'key_hex': secrets.token_bytes(32).hex()})
            self.keys.append((directory, 'handoff.key'))
        publish_json(self.state, 'native-prepared.json', {'study_id': STUDY_ID,
            'native_plans_sha256': digest(plans), 'runtime_freeze_sha256': freeze_sha256})

    def start(self):
        # ScriptEditor entry independently verifies formal authority before attach.
        if self.attach_wait is not None: self.attach_wait()
        deadline = time.monotonic() + self.spec['hub_attach_timeout_seconds']
        while not (self.state / 'hub-bootstrap.json').exists():
            self.guard()
            require(time.monotonic() < deadline, 'formal hub attachment unknown')
            time.sleep(0.05)
        bootstrap = read_json(self.state, 'hub-bootstrap.json')
        require(bootstrap['runtime_freeze_sha256'] == digest(self.freeze)
            and bootstrap['source_sha256'] == self.freeze['source_inventory_sha256']
            and bootstrap['native_plans_sha256'] == digest(self.plans), 'formal actual hub bootstrap differs')
        self.hub = self.channel_factory(self.state, bytes.fromhex(read_json(self.state, 'hub.key')['key_hex']),
            digest(self.freeze), hub=True, guard=self.guard)

    def open_slot(self, *, slot_id, fixture_recipe, task_sha256, max_writes, max_reads, freeze_sha256):
        self.guard()
        plan = self.plans['plans'][slot_id]
        require(freeze_sha256 == digest(self.freeze) and fixture_recipe == plan['fixture_recipe']
            and (max_writes, max_reads) == (plan['max_writes'], plan['max_reads'])
            and task_sha256 == hashlib.sha256(plan['task_text'].encode()).hexdigest(), 'formal native slot differs')
        self.current = slot_id  # Keep unknown opening identity for fail-closed cleanup.
        value = self.hub.control('open', slot_id)
        require(value['status'] == 'slot_opened' and value['slot_id'] == slot_id, 'formal native opening failed')
        self.opened.append(slot_id)
        directory = self.state / slot_id
        child = self.channel_factory(directory, bytes.fromhex(read_json(directory, 'handoff.key')['key_hex']),
            digest(self.freeze), plan['task_text'], guard=self.guard)
        self.channels[slot_id] = child
        # Even abstention slots have empty databases, so hidden writes are detectable.
        store = ConsentStore(directory / 'consent.sqlite3', load_public_mcp_tools())
        with store._tx() as db:
            db.execute("CREATE TABLE IF NOT EXISTS c5_model_handoff (observation_sha256 TEXT PRIMARY KEY, state TEXT NOT NULL, request_id TEXT UNIQUE, payload_sha256 TEXT)")
        self.signers[slot_id] = (store, None)

    def capture(self, slot_id): return self.channels[slot_id].control('capture')

    def execute_observation(self, *, slot_id, task_text, response, before):
        child = self.channels[slot_id]
        sent, wire = response['wire_request'], response['wire_response']
        require(sent['slot_id'] == slot_id and sent['task'] == task_text and sent['scene'] == semantic(before['native']),
            'formal raw model/task/scene differs before permission')
        observed = rebind_observation(wire, sent, self.freeze['model_identities'][sent['route']], before['state'])
        require(observed == response['observation'], 'formal unchanged raw observation differs')
        from training.c5_formal20_plan import _schemas
        from training.c5_formal20_prepermission import rejection
        denied = rejection(observed['name'], observed['arguments'], before['native'], _schemas())
        if denied is not None: return denied
        record = {'capture': before, 'post_model_capture': None, 'signing_captures': [],
            'request': sent, 'response': wire, 'handoff_request_id': None}
        proxy = ActualScene(child, before, record)
        store, signer = self.signers[slot_id]
        if signer is None:
            p = self.plans['plans'][slot_id]
            signer = ResearchSigner(store, SceneView(proxy, proxy.semantic_scene), child.secret, digest(self.freeze), task_text,
                max_writes=p['max_writes'], max_reads=p['max_reads'])
            self.signers[slot_id] = (store, signer)
        else:
            signer.scene = SceneView(proxy, proxy.semantic_scene)
        envelope = signer.issue(observed, schemas=_schemas())
        record['handoff_request_id'] = envelope['payload']['request_id']
        # Save the consumed/signed handoff before dispatch; crashes retain it.
        step = sent['step_index']
        publish_json(self.state / slot_id, 'signing-%d.json' % step, record)
        value = child.exchange({'kind': 'execute', 'envelope': envelope})
        require(value.get('status') == 'done', 'formal native execution incomplete')
        return value

    def unresolved(self, slot_id):
        return self.hub is None or self.hub.unresolved or slot_id not in self.channels or self.channels[slot_id].unresolved

    def close_slot(self, slot_id): return self.channels[slot_id].control('close')

    def stop_slot(self, slot_id):
        value = self.channels[slot_id].control('stop')
        require(value.get('status') == 'stopped' and value.get('had_failure') is False, 'formal child stop incomplete')
        directory = self.state / slot_id
        publish_json(directory, 'database-backups.json', {name: database_backup(directory, name) for name in ('consent', 'fixture')})
        self.current = None
        return value

    def finish(self):
        if self.hub is not None:
            require(not self.hub.unresolved and self.current is None, 'formal uncertain hub/fixture requires reconciliation')
            return self.hub.control('stop')
        # Only before a hub start claim can partial preparation be safely cleaned.
        require(not (self.state / 'formal20.hub-started.claim.json').exists(), 'formal unknown hook requires reconciliation')
        publish_json(self.state, 'formal20.hub-admission.claim.json', {'action': 'abort_before_attach',
            'study_id': STUDY_ID, 'runtime_freeze_sha256': digest(self.freeze), 'replay_allowed': False})
        removed = []
        for directory, name in self.keys:
            if os.path.lexists(directory / name):
                removed.append({'directory_slot': directory.name, **remove_private_key(directory, name)})
        publish_json(self.state, 'unattached-key-cleanup.json', {'keys': removed, 'hub_never_claimed': True})
        return {'status': 'hub_not_attached_cleaned', 'had_failure': True}


class ModelAdapter:
    def __init__(self, state, spec, freeze, *, guard, process_factory=subprocess.Popen, pipe_factory=FramedPipe):
        self.state, self.spec, self.freeze, self.guard = state, spec, freeze, guard
        self.process_factory, self.pipe_factory = process_factory, pipe_factory
        self.process, self.pipe, self.stderr_fd = None, None, None
        self.attempts, self.plans = [], None

    def prepare(self, plans, *, freeze_sha256):
        self.guard()
        require(freeze_sha256 == digest(self.freeze), 'formal model freeze differs')
        self.plans = hashed_model_plans(plans)
        publish_json(self.state, 'model-plans-hashed.json', self.plans)

    def start(self):
        self.guard()
        require(SSH_SOCKET.is_socket(), 'existing authenticated formal SSH socket required')
        require(SSH_KNOWN_HOSTS.is_file() and SSH_KNOWN_HOSTS.resolve() == SSH_KNOWN_HOSTS
            and file_sha(SSH_KNOWN_HOSTS) == SSH_KNOWN_HOSTS_SHA, 'formal pinned SSH host identity differs')
        self.stderr_fd = os.open(self.state / 'worker-stderr.txt', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        args = ['ssh', '-T', '-S', str(SSH_SOCKET), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + str(SSH_KNOWN_HOSTS), '-o', 'HostKeyAlgorithms=ssh-ed25519',
            '-p', str(SSH_PORT), 'linux@175.155.64.171',
            'cd ' + str(REMOTE_SOURCE) + ' && ' + str(REMOTE_ENV / 'bin/python') + ' -B -m tools.run_c5_formal20_worker serve']
        self.process = self.process_factory(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr_fd)
        self.pipe = self.pipe_factory(self.process, timeout=self.spec['per_request_timeout_seconds'])
        bootstrap = {'kind': 'formal_bootstrap', 'study_id': STUDY_ID, 'runtime_freeze_sha256': digest(self.freeze),
            'started': read_json(self.state, 'formal20.started.json'), 'plans': self.plans}
        publish_json(self.state, 'worker-bootstrap-request.json', bootstrap)
        value = self.pipe.exchange(bootstrap)
        require(value.get('status') == 'formal_worker_ready' and value.get('model_identities') == self.freeze['model_identities']
            and value.get('runtime_freeze_sha256') == digest(self.freeze), 'formal worker readiness differs')
        publish_json(self.state, 'worker-bootstrap-response.json', value)

    def infer(self, *, slot_id, route, step_index, task_text, scene, binding, freeze_sha256):
        self.guard()
        require(freeze_sha256 == digest(self.freeze), 'formal inference freeze drift')
        sent = request(STUDY_ID, slot_id, route, step_index, task_text, scene, binding, freeze_sha256, 'm-' + secrets.token_urlsafe(24))
        key = digest({'slot': slot_id, 'step': step_index, 'freeze': freeze_sha256})
        self.attempts.append(key)
        publish_json(self.state, key + '-model-request.json', sent)
        wire = self.pipe.exchange(sent)
        publish_json(self.state, key + '-model-response.json', wire)
        observed = rebind_observation(wire, sent, self.freeze['model_identities'][route], binding)
        return {**wire, 'observation': observed, 'wire_request': sent, 'wire_response': wire}

    def stop(self):
        if self.process is None:
            if self.stderr_fd is not None: os.close(self.stderr_fd); self.stderr_fd = None
            return
        try:
            require(not self.pipe.blocked, 'formal unknown remote acknowledgement; no reconnect/export retry')
            for key in self.attempts:
                sent = {'kind': 'formal_export_step', 'study_id': STUDY_ID, 'runtime_freeze_sha256': digest(self.freeze), 'key': key}
                value = self.pipe.exchange(sent)
                require(value.get('status') == 'formal_raw_step_evidence' and value.get('key') == key,
                    'formal remote evidence scope differs')
                publish_json(self.state, key + '-remote-evidence.json', value)
            sent = {'kind': 'formal_stop', 'study_id': STUDY_ID, 'runtime_freeze_sha256': digest(self.freeze)}
            stopped = self.pipe.exchange(sent)
            require(stopped.get('status') == 'formal_worker_stopped' and stopped.get('runtime_freeze_sha256') == digest(self.freeze),
                'formal remote stop proof missing')
            publish_json(self.state, 'worker-stop-response.json', stopped)
        finally:
            self.process.stdin.close()
            try: exit_code = self.process.wait(timeout=180)
            except subprocess.TimeoutExpired: exit_code = None
            self.process.stdout.close()
            if self.stderr_fd is not None: os.close(self.stderr_fd); self.stderr_fd = None
            publish_json(self.state, 'worker-process-exit.json', {'exit_code': exit_code, 'replay_allowed': False})
        require(exit_code == 0, 'formal remote process did not exit cleanly')
