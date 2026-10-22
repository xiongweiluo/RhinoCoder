"""Formal-only exact host checkpoints and complete native timing.

No field effects on import. Arm accepts no tasks before zero-consumption
readiness. Private plans are initialized once only after the owner claim.
"""
import json
import time

from .c5_formal_reuse_hub_base import FormalHub
from .c5_formal_reuse_scope import STUDY_ID, native_plans
from .c5_hostassurance_lifecycle_hub_d import LifecycleBridgeD, finish_service
from .c5_formal20_observation_capacity import validate_settle_sample_count
from .c5_lifecycle_deadlines import PhaseClock
from .c5_research_channel import publish_json, read_json
from .c5_research_native import digest, require, active_content_digest


class FormalLifecycleBridge(LifecycleBridgeD):
    def settle(self):
        require(self.pending is not None, 'known formal pending receipt required')
        validate_settle_sample_count(len(self.pending['samples']))
        require(len(self.pending['samples']) < 8, 'formal settle sampling exhausted; no retry')
        return super().settle()


class FormalHostHub(FormalHub):
    def __init__(self, *args, assurance, **kwargs):
        self.assurance = assurance
        self.current_request, self.request_attested, self.cleanup_mode = None, False, False
        kwargs['bridge_factory'] = lambda *a, **k: FormalLifecycleBridge(*a,
            lifecycle=self.spec['lifecycle_protocol'], cleanup_source=self.cleanup_guard,
            assurance=self.assurance, **k)
        kwargs['seed_guard'] = self.dispatch_guard
        # The original hub still owns HMAC, order, seeding and exact Dispose.
        super().__init__(*args, **kwargs)
        self.source = self.dispatch_guard

    def dispatch_guard(self):
        return self.assurance.checkpoint('formal-dispatch-%04d' % self.assurance.checkpoints)

    def cleanup_guard(self):
        return self.assurance.cleanup_checkpoint('formal-cleanup-%04d' % self.assurance.checkpoints)

    def guard(self):
        source=self.source
        if self.cleanup_mode: self.source=self.cleanup_guard
        try:
            super().guard()
            if self.current_request is not None and not self.request_attested:
                publish_json(self.state,'hub-host-check-%04d.json'%self.seq,{
                    'request_sha256':digest(self.current_request),'host_record_sha256':self.assurance.head,
                    'host_sequence':self.assurance.sequence-1,'runtime_freeze_sha256':digest(self.freeze)})
                self.request_attested=True
        finally: self.source=source

    def handle(self, envelope):
        self.current_request,self.request_attested=envelope,False
        self.cleanup_mode=envelope.get('payload',{}).get('action')=='stop' if isinstance(envelope,dict) else False
        try:
            value=super().handle(envelope)
            if value.get('status')=='hub_stopped':
                receipt=self.assurance.finish()
                publish_json(self.state,'host-continuity-terminal-receipt.json',receipt)
                print('C5_FORMAL_REUSE_HOST_EXTERNAL_RECEIPT '+json.dumps(receipt,sort_keys=True))
            return value
        finally: self.current_request,self.request_attested,self.cleanup_mode=None,False,False

    def tick(self, sender=None, event=None):
        if self.stopped: return
        import Rhino
        if getattr(Rhino.RhinoApp,'InCommand',False): return
        seq=self.seq
        if not (self.state/('hub-request-%04d.json'%seq)).exists(): return
        phase=PhaseClock(120,clock=time.monotonic)
        super().tick(sender,event)
        if self.seq != seq and not finish_service(self.state,'hub-',seq,phase,digest(self.freeze)):
            self.blocked=True


class FormalArm:
    """One already-attached delegate, no private reads before owner started."""
    def __init__(self, state, spec, freeze, schemas, source, active, assurance):
        self.state,self.spec,self.freeze,self.schemas,self.source=state,spec,freeze,schemas,source
        self.active,self.assurance,self.hub=active,assurance,None
        self.blocked=self.stopped=False
        self.active_serial=int(active.RuntimeSerialNumber)
        self.active_sha=active_content_digest(active)
        self._callback=None

    def tick(self, sender=None, event=None):
        if self.blocked or self.stopped: return
        import Rhino
        if getattr(Rhino.RhinoApp,'InCommand',False): return
        if self.hub is None and (self.state/'preload-abort.request.json').exists():
            require(not (self.state/'formal20.hub-initialization.claim.json').exists(),'formal_reuse_uninitialized_abort_only')
            from .c5_research_gate import signature
            from .c5_research_channel import remove_private_key
            import hmac
            request=read_json(self.state,'preload-abort.request.json');payload=request['payload']
            secret=bytes.fromhex(read_json(self.state,'hub.key')['key_hex'])
            require(set(payload)=={'action','runtime_freeze_sha256'}
                and payload=={'action':'abort_uninitialized_native','runtime_freeze_sha256':digest(self.freeze)}
                and hmac.compare_digest(request['signature'],signature(secret,payload)),
                'formal_reuse_abort_signature')
            self.assurance.checkpoint('formal-preload-before-abort')
            self.assurance.cleanup_checkpoint('formal-preload-abort')
            removed=[]
            for n in range(1,21):
                for route in ('base','lora'):
                    slot='F%02d-%s'%(n,route)
                    removed.append({'slot_id':slot,**remove_private_key(self.state/slot,'handoff.key')})
            hub=remove_private_key(self.state,'hub.key')
            Rhino.RhinoApp.Idle-=self._callback
            terminal=self.assurance.finish();self.stopped=True
            publish_json(self.state,'host-continuity-terminal-receipt.json',terminal)
            publish_json(self.state,'preload-abort.response.json',{'status':'preload_aborted',
                'request_sha256':digest(request),'runtime_freeze_sha256':digest(self.freeze),
                'unused_keys_removed':removed,'hub_key_absence':hub,
                'hook_removed_in_same_callback':True,'host_terminal':terminal,'private_rows_read_by_native_arm':0})
            print('C5_FORMAL_REUSE_HOST_EXTERNAL_RECEIPT '+json.dumps(terminal,sort_keys=True))
            return
        if self.hub is None:
            if not (self.state/'native-prepared.json').exists(): return
            try:
                require(read_json(self.state,'formal20.started.json')=={
                    'study_id':STUDY_ID,'spec_sha256':digest(self.spec),
                    'runtime_freeze_sha256':digest(self.freeze),
                    'public_commitment_sha256':self.spec['public_commitment_sha256'],'replay_allowed':False},
                    'permanent owner consumption claim required before private plans')
                publish_json(self.state,'formal20.hub-initialization.claim.json',{
                    'study_id':STUDY_ID,'runtime_freeze_sha256':digest(self.freeze),'replay_allowed':False})
                plans=native_plans(read_json(self.state,'native-plans.json'))
                prepared=read_json(self.state,'native-prepared.json')
                require(prepared=={'study_id':STUDY_ID,'native_plans_sha256':digest(plans),
                    'runtime_freeze_sha256':digest(self.freeze)}, 'one-time private plan binding differs')
                self.hub=FormalHostHub(self.state,self.spec,self.freeze,plans,self.schemas,self.source,
                    self.active,assurance=self.assurance)
                require(self.hub.active_serial==self.active_serial and self.hub.initial_active==self.active_sha,
                    'formal active document changed before private initialization')
                self.hub.guard()
                # Preserve the SAME installed delegate, never attach again.
                self.hub._callback=self._callback; self.hub.attached=True
                publish_json(self.state,'hub-bootstrap.json',{'study_id':STUDY_ID,
                    'runtime_freeze_sha256':digest(self.freeze),'source_sha256':self.freeze['source_inventory_sha256'],
                    'native_plans_sha256':digest(plans),'active_serial':self.active_serial,'active_sha256':self.active_sha})
            except BaseException as exc:
                self.blocked=True
                publish_json(self.state,'formal20.hub-initialization.failed.json',{
                    'study_id':STUDY_ID,'error_type':type(exc).__name__,'replay_allowed':False})
                raise
        self.hub.tick(sender,event)
        self.blocked,self.stopped=self.hub.blocked,self.hub.stopped
