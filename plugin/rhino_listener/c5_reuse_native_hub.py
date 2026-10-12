"""New approved development binding over the retained native lifecycle.

Views below are constructor adapters, never claimed to be frozen documents.
Every signature and raw artifact carries the actual new runtime hash.
No Rhino import, subscription, fixture, grant or key on module import.
"""
import time
from pathlib import Path
from .c5_reuse_field_scope import validate_binding, require, sha, STUDY
from .c5_reuse_public_plan import public_plan
from .c5_hostassurance_development_hub import HostAwareDevelopmentHub
from .c5_hostassurance_lifecycle_hub_d import LifecycleBridgeD, finish_service
from .c5_lifecycle_deadlines import PhaseClock


class ReuseBridge(LifecycleBridgeD):
    def settle(self):
        require(self.pending is not None and len(self.pending['samples'])<8,'reuse_settlement_capacity')
        return super().settle()


class ReuseNativeHub(HostAwareDevelopmentHub):
    def __init__(self,binding,runtime,registry,schemas,active,byte_guard,assurance):
        validate_binding(binding)
        require(binding['endpoint']=='mac' and registry.binding==binding
                and sha(runtime)==binding['runtime_sha256'],'reuse_native_hub_binding')
        plan=public_plan(Path(binding['paths']['source_root']))
        require(plan['development_plan_sha256']==binding['development_plan_sha256'],'reuse_native_hub_plan')
        self.binding,self.registry=binding,registry
        view={'probe_id':STUDY,'slot_order':plan['order'],'task_plans':plan['task_plans'],
              'slot_policies':plan['slot_policies']}
        native_view={'source_inventory_sha256':sha(runtime['source_files']),
                     'resource_boundary':{'hard_stop_epoch':runtime['resources']['generation_cutoff_epoch']+900}}
        super().__init__(state=Path(binding['paths']['state_root']),spec=view,freeze=native_view,
                         schemas=schemas,active=active,byte_guard=byte_guard,
                         runtime_sha=binding['runtime_sha256'],max_messages=41)
        self.assurance=assurance
        self.bridge_factory=lambda *a,**k:ReuseBridge(*a,**k,max_messages=128,
            lifecycle={'native_ack_seconds':120,'settle_seconds':60},
            cleanup_source=self.cleanup_guard,assurance=self.assurance)
        self.monotonic=time.monotonic

    def tick(self,sender=None,event=None):
        if self.stopped:return
        import Rhino
        if getattr(Rhino.RhinoApp,'InCommand',False):return
        seq=self.seq
        if not (self.state/('hub-request-%04d.json'%seq)).exists():return
        phase=PhaseClock(120,clock=self.monotonic)
        super().tick(sender,event)
        if self.seq!=seq and not finish_service(self.state,'hub-',seq,phase,self.runtime_sha):
            self.blocked=True
