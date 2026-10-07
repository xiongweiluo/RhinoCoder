"""New isolated development hub; no default registration or model imports.

Python3.9/RhinoCommon lifecycle owner opens at most one fresh fixture at a
time. A stopped child is required before another slot. All slot admission
claims live at the fixed approved state root, not replaceable output folders.
"""
from __future__ import annotations

import hashlib
import hmac
import time

from .c5_research_channel import publish_json,read_json,remove_private_key
from .c5_research_gate import ResearchGate,signature
from .c5_research_native import NativeDoc,require,digest,active_content_digest
from .candidate_atomic_gate import RhinoAtomicGate,rhino_scene_digest
from .c5_research_session import IdleBridge


class DevelopmentHub:
    """Only the new frozen ScriptEditor entry may create/attach this owner.

    Neither this class nor a signer constructor fabricates owner approval.
    The entry checks the exact human record, source freeze and prepared scope.
    Unknown/partial opening retains the actual fixture reference for audit.
    """
    def __init__(self,state,spec,freeze,schemas,source,active,*,clock=time.time,bridge_factory=IdleBridge):
        self.state,self.spec,self.freeze,self.schemas,self.source = state,spec,freeze,schemas,source
        self.active,self.active_serial = active,int(active.RuntimeSerialNumber)
        # A's watermark-bearing digest was over-sensitive: read-only Rhino
        # ScriptEditor commands advance global object/undo counters. Keep
        # those counters for mutable fixture atomicity, but use the same
        # content-only protection already used by NativeDoc for the active UI.
        self.initial_active = active_content_digest(active)
        self.clock,self.seq = clock,1
        self.bridge_factory = bridge_factory
        self.secret = bytes.fromhex(read_json(state,'hub.key')['key_hex'])
        self.child,self.fixture = None,None
        self.opened,self.control_ids = [],set()
        self.blocked,self.stopped,self.attached = False,False,False
        self._callback = self.tick

    def guard(self):
        import Rhino
        self.source()
        require(Rhino.RhinoApp.IsOnMainThread and Rhino.RhinoDoc.ActiveDoc is not None
                and int(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber)==self.active_serial
                and active_content_digest(self.active)==self.initial_active,'actual active document changed')

    def attach(self):
        import Rhino
        self.guard()
        require(not self.attached,'hub already attached')
        publish_json(self.state,'hub-bootstrap.json',{'probe_id':self.spec['probe_id'],
                     'runtime_freeze_sha256':digest(self.freeze),'source_sha256':self.freeze['source_inventory_sha256'],
                     'active_serial':self.active_serial,'active_sha256':self.initial_active})
        Rhino.RhinoApp.Idle += self._callback
        self.attached=True

    def handle(self,envelope):
        self.guard()
        require(isinstance(envelope,dict) and set(envelope)=={'payload','signature'},'exact signed hub control required')
        p=envelope['payload']
        require(isinstance(p,dict) and set(p)=={'version','request_id','action','slot_id','owner_freeze_sha256','expires_at'}
                and type(p['version']) is int and p['version']==1 and p['action'] in {'open','stop'}
                and p['owner_freeze_sha256']==digest(self.freeze)
                and isinstance(p['request_id'],str) and 16 <= len(p['request_id']) <= 128
                and p['request_id'] not in self.control_ids
                and type(p['expires_at']) is int and 0 < p['expires_at']-self.clock() <= 120
                and isinstance(envelope['signature'],str)
                and hmac.compare_digest(envelope['signature'],signature(self.secret,p)), 'hub control scope/TTL/signature rejected')
        self.control_ids.add(p['request_id'])
        if p['action']=='stop':
            # A partially opened NEW fixture can coexist with a previously
            # stopped child. Only the bridge bound to the CURRENT retained
            # fixture may attest closure. Never report hub cleanup while a
            # created-but-unbridged document could still be alive.
            current_closed=(self.fixture is None or
                (self.child is not None and self.child.gate.backend.doc is self.fixture
                 and self.child.stopped and self.child.gate.backend.closed))
            require(p['slot_id'] is None and current_closed,
                    'cannot stop hub with live/unbridged/uncertain current fixture')
            import Rhino
            # Known never-opened ephemeral keys only. No evidence/claims or R
            # files are deleted; actual opened children removed their own key.
            removed=[]
            for slot in self.spec['slot_order']:
                if slot not in self.opened:
                    proof=remove_private_key(self.state/slot,'handoff.key')
                    require(proof['actual_absence_checked'],'unused scoped key absence unverified')
                    removed.append(slot)
            hub_key=remove_private_key(self.state,'hub.key')
            Rhino.RhinoApp.Idle -= self._callback
            self.attached,self.stopped=False,True
            self.guard()
            value={'status':'hub_stopped','opened_slots':list(self.opened),'unused_keys_removed':removed,
                   'hub_key_absence':hub_key,'hook_removed_in_same_callback':True,
                   'active_serial':self.active_serial,'active_sha256':self.initial_active,
                   'source_sha256':self.freeze['source_inventory_sha256'],'had_failure':self.blocked}
            publish_json(self.state,'hub-stop.json',value)
            return value
        require(not self.blocked and self.clock() < self.freeze['resource_boundary']['hard_stop_epoch']-900,
                'blocked/past-budget hub cannot open')
        require(self.child is None or self.child.stopped,'previous child not verifiably stopped')
        require(len(self.opened) < len(self.spec['slot_order']) and p['slot_id']==self.spec['slot_order'][len(self.opened)],
                'fixed counterbalanced slot order differs')
        slot=p['slot_id']; directory=self.state/slot
        publish_json(self.state,slot+'.engine-started.claim.json',{'probe_id':self.spec['probe_id'],
                     'slot_id':slot,'runtime_freeze_sha256':digest(self.freeze),'replay_allowed':False})
        import Rhino
        fixture=Rhino.RhinoDoc.CreateHeadless(None)
        require(fixture is not None,'headless opening unknown; do not retry')
        self.fixture=fixture  # Retain identity before any further operation.
        self.opened.append(slot)
        publish_json(directory,'engine-created.json',{'fixture_serial':int(fixture.RuntimeSerialNumber),
                     'active_serial':self.active_serial,'runtime_freeze_sha256':digest(self.freeze),
                     'rhino_version':str(Rhino.RhinoApp.Version),'python_major_minor':[3,9],'rhino_major':8})
        fixture.ModelUnitSystem=Rhino.UnitSystem.Millimeters
        fixture.ModelAbsoluteTolerance=0.000001
        backend=NativeDoc(fixture,self.active,self.schemas)
        atomic=RhinoAtomicGate(directory/'fixture.sqlite3',str(fixture.RuntimeSerialNumber),
                 lambda:rhino_scene_digest(fixture),create_ledger=True)
        plan=self.spec['task_plans'][slot]
        require(len(plan['steps'])==1,'development hub permits single-step slot only')
        task=plan['steps'][0]
        secret=bytes.fromhex(read_json(directory,'handoff.key')['key_hex'])
        policy=self.spec['slot_policies'][slot]
        gate=ResearchGate(backend,atomic,secret,digest(self.freeze),task_sha256=hashlib.sha256(task.encode()).hexdigest(),
                          max_writes=policy['max_writes'],max_reads=policy['max_reads'])
        self.child=self.bridge_factory(gate,directory,key_name='handoff.key',
                 source_sha256=self.freeze['source_inventory_sha256'],guard_source=self.source)
        self.child.attach()
        return {'status':'slot_opened','slot_id':slot,'fixture_serial':int(fixture.RuntimeSerialNumber)}

    def tick(self,sender=None,event=None):
        if self.stopped:return
        import Rhino
        if getattr(Rhino.RhinoApp,'InCommand',False):return
        name='hub-request-%04d.json'%self.seq
        if not (self.state/name).exists():return
        try:
            require(self.seq <= 16,'hub message count exhausted')
            result=self.handle(read_json(self.state,name))
        except BaseException as exc:
            self.blocked=True
            result={'status':'hub_failed_no_retry','error_type':type(exc).__name__,'error':str(exc),
                    'manual_reconciliation_required':True}
        publish_json(self.state,'hub-response-%04d.json'%self.seq,result)
        self.seq+=1
