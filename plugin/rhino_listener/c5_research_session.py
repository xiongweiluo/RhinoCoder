"""Opt-in C5 Idle bridge over an ALREADY owner-approved disposable fixture.

Python 3.9 stdlib. Does not create fixtures, keys, ledgers, grants or models,
register a Listener route, read task corpora, or provide a standalone entry.
The frozen trusted lifecycle runner must claim admission and verify actual
owner approval and loaded-source closure before constructing this object.
"""
from __future__ import annotations

import hmac
import os
import time
from pathlib import Path

from .c5_research_channel import private_directory, publish_json, read_json, remove_private_key
from .c5_research_gate import REQUEST, SHA, signature
from .c5_research_native import active_content_digest, digest, require

CONTROL_KEYS = {'version','request_id','task_sha256','owner_freeze_sha256','action','expires_at'}


class IdleBridge:
    def __init__(self, gate, directory, *, key_name, source_sha256, guard_source, clock=time.time, monotonic=time.monotonic,
                 max_messages=64):
        import Rhino
        require(Rhino.RhinoApp.IsOnMainThread, 'Idle bridge must start on Rhino UI thread')
        require(isinstance(source_sha256,str) and SHA.fullmatch(source_sha256)
                and guard_source() == source_sha256, 'actual loaded source closure differs')
        root = private_directory(directory)
        os.close(root)
        key = read_json(directory,key_name)
        require(isinstance(key,dict) and set(key)=={'key_hex'} and isinstance(key['key_hex'],str)
                and len(key['key_hex'])==64, 'exact private signing key required')
        require(hmac.compare_digest(bytes.fromhex(key['key_hex']),gate.secret), 'controller/signer key differs')
        gate.backend.guard()
        self.gate, self.directory, self.key_name = gate, Path(directory), key_name
        self.source_sha, self.guard_source = source_sha256, guard_source
        self.clock, self.monotonic = clock, monotonic
        require(type(max_messages) is int and max_messages in {64, 128}, 'bounded Idle message policy required')
        self.max_messages = max_messages
        self.seq, self.pending, self.blocked, self.stopped, self.attached = 1, None, False, False, False
        self.close_attempted, self.control_ids = False, set()
        self._callback = self.tick

    def _active(self):
        import Rhino
        backend = self.gate.backend
        require(Rhino.RhinoApp.IsOnMainThread and Rhino.RhinoDoc.ActiveDoc is not None
                and int(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber)==backend.active_serial, 'active UI identity differs')
        sha = active_content_digest(Rhino.RhinoDoc.ActiveDoc)
        require(sha == backend.initial_active_sha, 'active content drift')
        return sha

    def _source(self):
        require(self.guard_source() == self.source_sha, 'runtime/import source drift')

    def attach(self):
        import Rhino
        self._source()
        self._active()
        require(not self.attached and not self.stopped, 'bridge already attached/stopped')
        # Bind the exact already-created fixture, not an arbitrary path/result.
        capture = self._capture()
        publish_json(self.directory,'bootstrap.json',{'version':1,'source_sha256':self.source_sha,
                     'owner_freeze_sha256':self.gate.owner_freeze,'task_sha256':self.gate.task_sha,
                     'fixture_serial':self.gate.backend.serial,'active_sha256':self._active(),
                     'active_serial':self.gate.backend.active_serial,
                     'state':capture['state'],'native':capture['native']})
        Rhino.RhinoApp.Idle += self._callback
        self.attached = True

    def _control(self, envelope):
        require(isinstance(envelope,dict) and set(envelope)=={'payload','signature'}, 'signed control required')
        p = envelope['payload']
        require(isinstance(p,dict) and set(p)==CONTROL_KEYS and type(p['version']) is int and p['version']==1,
                'control version/keys differ')
        require(isinstance(envelope['signature'],str) and SHA.fullmatch(envelope['signature'])
                and hmac.compare_digest(signature(self.gate.secret,p),envelope['signature']), 'control signature rejected')
        require(isinstance(p['request_id'],str) and REQUEST.fullmatch(p['request_id'])
                and p['request_id'] not in self.control_ids, 'duplicate/invalid control identity')
        require(p['owner_freeze_sha256']==self.gate.owner_freeze and p['task_sha256']==self.gate.task_sha,
                'control owner/task differs')
        require(type(p['expires_at']) is int and self.clock()<p['expires_at']<=self.clock()+300, 'control TTL differs')
        require(p['action'] in {'capture','close','stop'}, 'unknown control')
        self.control_ids.add(p['request_id'])
        return p

    def _capture(self):
        self.gate.backend.guard()
        before = self.gate.atomic.snapshot()
        native = self.gate.backend.readback()
        require(self.gate.atomic.snapshot()==before, 'unstable capture; no retry')
        return {'state':before,'native':native,'active_sha256':self._active()}

    def handle(self, request):
        """One callback action; deferred settling never calls dispatch again."""
        self._source()
        self._active()
        require(self.attached and not self.stopped and isinstance(request,dict) and set(request)=={'kind','envelope'}, 'invalid request/stopped/unattached bridge')
        if request['kind']=='execute':
            require(not self.blocked and not self.close_attempted and self.pending is None, 'uncertain/closing bridge rejects execution')
            result = self.gate.execute(request['envelope'])
            # Preserve raw immediate receipt before any settling verifier.
            publish_json(self.directory,'execute-%04d.json'%self.seq,result)
            self.pending = {'receipt':result,'response_name':'response-%04d.json'%self.seq,
                            'deadline':self.monotonic()+15,'last':None,'stable':0,'samples':[]}
            return None
        require(request['kind']=='control' and self.pending is None, 'unknown request or execution still settling')
        control = self._control(request['envelope'])
        if control['action']=='capture':
            require(not self.blocked and not self.close_attempted, 'blocked/closed capture')
            return {'status':'captured',**self._capture()}
        if control['action']=='close':
            require(not self.close_attempted, 'close already attempted; manual cleanup if uncertain')
            self.close_attempted = True
            before = self._active()
            capture = self.gate.backend.close()
            removed = remove_private_key(self.directory,self.key_name)
            after = self._active()
            require(before==after and capture['fixture_registry_absent'] is True
                    and removed['actual_absence_checked'], 'close/key absence unverified')
            return {'status':'closed','close_capture':capture,'key_absence':removed,
                    'active_sha256':after,'source_sha256':self.source_sha}
        require(self.close_attempted and self.gate.backend.closed and self.attached, 'stop before known close/attached bridge')
        try: os.stat(self.directory/self.key_name,follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise ValueError('key or symlink still present at stop')
        import Rhino
        Rhino.RhinoApp.Idle -= self._callback
        self.attached, self.stopped = False, True
        return {'status':'stopped','active_sha256':self._active(),'source_sha256':self.source_sha,
                'had_failure':self.blocked,'hook_removed_in_same_callback':True}

    def settle(self):
        require(self.pending is not None and self.monotonic()<self.pending['deadline'], 'postwrite settling deadline exceeded')
        self._source()
        capture = self._capture()
        current = digest(capture)
        self.pending['samples'].append(capture)
        self.pending['stable'] = self.pending['stable']+1 if current==self.pending['last'] else 1
        self.pending['last'] = current
        if self.pending['stable'] < 3: return None
        raw = self.pending['receipt']
        final = {**raw,'after':capture['native'],'after_state':capture['state'],
                 'immediate_after':raw['after'],'immediate_after_state':raw['after_state'],
                 'settling_samples':self.pending['samples'],'stable_idle_samples':3}
        publish_json(self.directory,self.pending['response_name'],final)
        self.pending = None
        return final

    def tick(self, sender=None, event=None):
        """Bounded Idle service. Errors retained; no model/execute/close retry."""
        if self.stopped: return
        import Rhino
        if getattr(Rhino.RhinoApp,'InCommand',False): return
        name = 'request-%04d.json'%self.seq
        try:
            if self.pending is not None:
                if self.settle() is not None: self.seq += 1
                return
            if not (self.directory/name).exists(): return
            require(self.seq<=self.max_messages, 'bounded fixture message count exceeded')
            result = self.handle(read_json(self.directory,name))
            if result is not None:
                publish_json(self.directory,'response-%04d.json'%self.seq,result)
                self.seq += 1
        except BaseException as exc:
            self.blocked = True
            pending = self.pending
            self.pending = None
            # A raw execute receipt and reservation survive settling failure.
            # Only a separately signed close/stop may follow; no quality retry.
            response = pending['response_name'] if pending else 'response-%04d.json'%self.seq
            try:
                publish_json(self.directory,response,{'status':'failed_no_retry','error_type':type(exc).__name__,
                             'error':str(exc),'seq':self.seq,'manual_review_required':True})
            finally:
                self.seq += 1
