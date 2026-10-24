"""New development permission handoff over retained signer/SQLite semantics.

No fixture opening, key provisioning, Rhino import, launcher or approval maker.
The actual frozen entry supplies one captured fixture and its signed channel.
Public plans are read from the bound source root, never private train/holdout.
"""
import os
from pathlib import Path
import time

from plugin.rhino_listener.c5_research_channel import private_directory
from plugin.rhino_listener.c5_research_native import digest, READS
from training.c5_reuse_evidence import canonical, require, sha, strict
from training.c5_reuse_field_scope import validate_binding
from training.c5_reuse_field_wire import approved_request, validate_peer_result
from training.c5_reuse_development_plan import public_plan
from training.c5_modelbridge_joint_audit import semantic
from training.c5_inventory import load_public_mcp_tools
from training.c5_research_permission import ResearchSigner, SceneView
from training.consent_candidate import ConsentStore
from training.c5_formal20_prepermission import rejection


class CaptureProxy:
    def __init__(self,capture,expected,journal,check):
        self.capture,self.expected,self.journal,self.check=capture,expected,journal,check

    def _capture(self):
        self.check()
        value=self.capture()
        self.journal.append('native_signing_capture',{'capture':value})
        require(canonical(value)==canonical(self.expected), 'reuse_actual_scene_changed_before_signing')
        self.check()
        return value

    def snapshot(self): return self._capture()['state']
    def semantic_scene(self): return semantic(self._capture()['native'])


class NativeHandoff:
    def __init__(self,journal,schemas,guard,budget,*,clock=time.monotonic,epoch=time.time):
        validate_binding(journal.binding)
        require(journal.role=='controller' and journal.binding['endpoint']=='mac', 'reuse_handoff_controller')
        guard(); budget()
        self.journal,self.binding=journal,journal.binding
        self.plan=public_plan(Path(self.binding['paths']['source_root']))
        require(self.plan['development_plan_sha256']==self.binding['development_plan_sha256'], 'reuse_native_public_plan')
        require(not any(r['kind']=='native_handoff_open' for r in journal.records),'reuse_handoff_reconstruction_forbidden')
        self.schemas=strict(canonical(schemas))
        self.guard,self.budget,self.clock,self.epoch=guard,budget,clock,epoch
        self.spent=set(); self.blocked=False
        self.journal.append('native_handoff_open',{'development_plan_sha256':self.plan['development_plan_sha256']})

    def execute(self,sent,result,before,capture,execute_signed,secret):
        require(self.journal.lock.acquire(blocking=False),'reuse_handoff_active')
        try:
            require(not self.blocked and not self.journal.blocked,'reuse_handoff_retired_no_retry')
            sent,result,before=(strict(canonical(x),limit=2*1024*1024) for x in (sent,result,before))
            approved_request(self.binding,sent,self.plan['task_plans'])
            observed=validate_peer_result(self.binding,sent,result)
            inner=sent['request']; key=(inner['slot_id'],inner['step_index'])
            require(key not in self.spent and inner['step_index']==0,'reuse_development_single_step_no_reissue')
            start=last=self.clock()
            def check():
                nonlocal last
                now=self.clock()
                require(last<=now<start+120,'reuse_complete_native_deadline')
                last=now
                self.guard(); self.budget()
            check()
            self.spent.add(key)
            self.blocked=True
            self.journal.append('native_handoff_intent',{'request':sent,'model_result':result,'before':before})
            require(type(before) is dict and set(before)=={'state','native'}
                    and digest(before['state'])==inner['binding_sha256']
                    and semantic(before['native'])==inner['scene'], 'reuse_actual_generation_scene_binding')
            if observed['status']!='schema_valid_not_authorized':
                value={'status':'model_classified_no_native_permission','model_status':observed['status'],
                       'permission_reserved':False,'native_dispatches':0}
                self.journal.append('native_no_permission',value)
                self.blocked=observed['status']=='operational_failure_no_retry'
                check()
                return value
            denied=rejection(observed['name'],observed['arguments'],before['native'],self.schemas)
            policy=self.plan['slot_policies'][inner['slot_id']]
            if denied is None and policy['max_reads' if observed['name'] in READS else 'max_writes']==0:
                denied={'status':'known_prepermission_rejection_no_dispatch','reason':'development_task_policy',
                        'permission_reserved':False,'native_dispatches':0}
            if denied is not None:
                self.journal.append('native_no_permission',denied)
                check(); self.blocked=False
                return denied
            proxy=CaptureProxy(capture,before,self.journal,check)
            proxy.snapshot()  # Current physical capture, never expected scoring state.
            directory=Path(self.binding['paths']['state_root'])/inner['slot_id']
            fd=private_directory(directory); os.close(fd)
            db_path=directory/'consent.sqlite3'
            fd=os.open(db_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); os.close(fd)
            store=ConsentStore(db_path,load_public_mcp_tools(),clock=self.epoch)
            signer=ResearchSigner(store,SceneView(proxy,proxy.semantic_scene),secret,self.binding['runtime_sha256'],
                inner['task'],max_writes=policy['max_writes'],max_reads=policy['max_reads'],clock=self.epoch)
            # This detached trusted binding leaves the raw model receipt intact.
            bound=strict(canonical(observed),limit=2*1024*1024); bound['scene_binding']=before['state']
            self.journal.append('native_permission_intent',{'bound_observation':bound})
            check()
            signed=signer.issue(bound,schemas=self.schemas)
            self.journal.append('native_signed_handoff',{'envelope':signed})
            check()
            receipt=execute_signed(signed)
            self.journal.append('native_dispatch_observed',{'receipt':receipt})
            require(type(receipt) is dict and receipt.get('status')=='done'
                    and receipt.get('payload')==signed['payload']
                    and receipt.get('before_state')==signed['payload']['expected']
                    and 'result' in receipt and receipt.get('result_sha256')==digest(receipt['result'])
                    and type(receipt.get('after_state')) is dict
                    and receipt['after_state'].get('document_key')==before['state']['document_key'],
                    'reuse_signed_native_result')
            check()
            self.blocked=False
            return receipt
        except BaseException as error:
            self.blocked=self.journal.blocked=True
            try: self.journal.append('native_handoff_retired',{'error_type':type(error).__name__})
            except BaseException: pass
            raise
        finally: self.journal.lock.release()
