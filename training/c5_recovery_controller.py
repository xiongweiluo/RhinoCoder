"""Opt-in future controller: preload confirmation, bounded recovery, shared budget.

There are deliberately no GPU/Rhino/SSH defaults or installed field commands.
Future complete source/runtime approval must supply the frozen trusted actors.
Importing/constructing/replaying this module grants no execution authority.
"""
import math
import time
from training.c5_reuse_evidence import exact,is_sha,require,sha
from training.c5_recovery_policy import POLICY,validate_scope,require_grant,retry_decision
from training.c5_recovery_confirmation import validate_receipt

def replay(scope,rows):
    validate_scope(scope)
    state={'attempts':0,'active':False,'formal_consumed':False,'first_load_epoch':None,
           'last_epoch':None,'status':'WAITING_OWNER','receipt':None,'ready':False,'begun':False,
           'scope':dict(scope)}
    for row in rows:
        scope=state['scope'];kind,p=row['kind'],row['payload']
        if kind in ('runtime_revision_accepted','resource_runtime_revision_accepted'):
            exact(p,('scope','grant','previous_head_sha256')+
                  (('resource_amendment',) if kind=='resource_runtime_revision_accepted' else ()))
            revised=validate_scope(p['scope'])
            require(not state['active'] and not state['formal_consumed']
                    and state['status'] not in ('PAUSED_RECONCILIATION','AWAITING_INDEPENDENT_AUDIT')
                    and state['attempts']<POLICY['public_attempts_max'],'recovery_revision_requires_known_pause')
            require(all(revised[k]==scope[k] for k in ('campaign_id','phase','policy_sha256',
                    'history_sha256','public_plan_sha256','contract_sha256')),
                    'recovery_revision_cannot_change_contract_or_reset_budget')
            if kind=='resource_runtime_revision_accepted':
                amendment={'old_seconds_max':scope['development_seconds_max'],
                    'new_seconds_max':revised['development_seconds_max'],
                    'first_load_epoch':state['first_load_epoch'],'attempts':state['attempts'],
                    'budget_reset':False,'old_budget_recredited':False}
                require(p['resource_amendment']==amendment and scope['phase']=='public_engineering'
                    and revised['development_seconds_max']>scope['development_seconds_max'],
                    'recovery_explicit_resource_amendment_required')
            else:require(revised['development_seconds_max']==scope['development_seconds_max'],
                         'recovery_revision_cannot_change_contract_or_reset_budget')
            require(revised['generation_cutoff_epoch']>=scope['generation_cutoff_epoch']
                    and revised!=scope,'recovery_revision_not_new_material')
            grant=dict(p['grant'])
            require(grant.pop('previous_campaign_head_sha256',None)==p['previous_head_sha256']
                    and row.get('previous_sha256',p['previous_head_sha256'])==p['previous_head_sha256'],
                    'recovery_revision_requires_prior_raw_head')
            require_grant(revised,grant)
            state.update(scope=dict(revised),receipt=None,status='WAITING_OWNER')
        elif kind=='owner_preload_confirmed':
            require(state['receipt'] is None and not state['active'],'recovery_confirmation_order')
            validate_receipt(scope,p['snapshot'],p['receipt'])
            state['receipt']=p;state['status']='PREPARED'
        elif kind=='owner_resume_requested':
            exact(p,('attempts',))
            require(state['status']=='PAUSED_OWNER' and not state['active'] and not state['formal_consumed']
                    and p['attempts']==state['attempts'] and state['attempts']<POLICY['public_attempts_max'],
                    'recovery_owner_resume_order')
            state['status']='RETRYABLE_ENGINEERING'
        elif kind=='attempt_load_intent':
            exact(p,('attempt','epoch'))
            require(state['receipt'] is not None and not state['active'] and not state['formal_consumed']
                    and state['status'] in ('PREPARED','RETRYABLE_ENGINEERING','RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE')
                    and type(p['attempt']) is int and p['attempt']==state['attempts']+1
                    and p['attempt']<=POLICY['public_attempts_max'],'recovery_attempt_order')
            require(type(p['epoch']) in (int,float) and math.isfinite(p['epoch']) and p['epoch']>0
                    and (state['last_epoch'] is None or p['epoch']>=state['last_epoch']),
                    'recovery_clock_regression')
            if state['first_load_epoch'] is None:
                require(p['epoch']+scope['development_seconds_max']<=scope['generation_cutoff_epoch'],
                        'recovery_complete_window_unavailable')
                state['first_load_epoch']=p['epoch']
            require(p['epoch']<min(state['first_load_epoch']+scope['development_seconds_max']-60,
                                  scope['generation_cutoff_epoch']-60),'recovery_shared_budget_exhausted')
            state.update(attempts=p['attempt'],active=True,ready=False,begun=False,
                         status='LOADING',last_epoch=p['epoch'])
        elif kind=='budget_observation':
            exact(p,('epoch',))
            require(state['first_load_epoch'] is not None and type(p['epoch']) in (int,float)
                    and math.isfinite(p['epoch']) and p['epoch']>=state['last_epoch']
                    and p['epoch']<min(state['first_load_epoch']+scope['development_seconds_max']-60,
                                      scope['generation_cutoff_epoch']-60),'recovery_shared_budget_exhausted')
            state['last_epoch']=p['epoch']
        elif kind=='worker_ready':
            exact(p,('attempt','raw_anchor_sha256'))
            require(state['active'] and not state['ready'] and p['attempt']==state['attempts']
                    and is_sha(p['raw_anchor_sha256']),'recovery_ready_order')
            state.update(ready=True,status='READY')
        elif kind in ('generation_begin_intent','private_exposure_intent'):
            exact(p,('attempt','raw_anchor_sha256'))
            require(state['active'] and p['attempt']==state['attempts']
                    and is_sha(p['raw_anchor_sha256']),'recovery_consumption_order')
            if kind=='generation_begin_intent':
                require(state['ready'] and not state['begun'],'recovery_generation_order')
                state['begun']=True
            else:
                require(scope['phase']=='formal' and not state['formal_consumed'],
                        'recovery_private_exposure_once')
            if scope['phase']=='formal':state['formal_consumed']=True
            state['status']='RUNNING'
        elif kind=='attempt_failed':
            exact(p,('attempt','error','proof','decision'))
            require(state['active'] and p['attempt']==state['attempts'],'recovery_failure_order')
            decision=retry_decision(scope,state['attempts'],state['formal_consumed'],p['error'],p['proof'])
            require(decision==p['decision'],'recovery_failure_decision_changed')
            state.update(active=False,status=decision)
        elif kind=='cleanup_reconciled':
            exact(p,('error','proof','decision'))
            require(not state['active'] and state['status']=='PAUSED_RECONCILIATION',
                    'recovery_reconciliation_order')
            decision=retry_decision(scope,state['attempts'],state['formal_consumed'],p['error'],p['proof'])
            require(p['decision']==decision and decision!='PAUSED_RECONCILIATION',
                    'recovery_reconciliation_incomplete')
            state['status']=decision
        elif kind=='attempt_completed':
            exact(p,('attempt','raw_anchor_sha256'))
            require(state['active'] and state['begun'] and p['attempt']==state['attempts']
                    and is_sha(p['raw_anchor_sha256']),'recovery_completion_order')
            state.update(active=False,status='AWAITING_INDEPENDENT_AUDIT')
        else:raise ValueError('recovery_unknown_event')
    return state

class Campaign:
    def __init__(self,scope,log,*,wall=time.time):
        validate_scope(scope)
        self.initial_scope,self.log,self.wall=log.binding,log,wall
        require(self.observation()['scope']==scope,'recovery_campaign_log_binding')
    @property
    def scope(self):return self.observation()['scope']
    def observation(self):
        with self.log.locked():return replay(self.initial_scope,self.log.rows())
    def _event(self,kind,payload):
        with self.log.locked():
            # Semantic replay BEFORE durable append/effect; invalid events write nothing.
            replay(self.initial_scope,self.log.rows()+[{'kind':kind,'payload':payload,
                    'previous_sha256':self.log.rows()[-1]['record_sha256'] if self.log.rows() else '0'*64}])
            return self.log.append_locked(kind,payload)
    def accept_revision(self,scope,grant):
        with self.log.locked():
            rows=self.log.rows();head=rows[-1]['record_sha256'] if rows else '0'*64
            payload={'scope':scope,'grant':grant,'previous_head_sha256':head}
            replay(self.initial_scope,rows+[{'kind':'runtime_revision_accepted','payload':payload,
                                           'previous_sha256':head}])
            return self.log.append_locked('runtime_revision_accepted',payload)
    def accept_resource_revision(self,scope,grant):
        with self.log.locked():
            rows=self.log.rows();state=replay(self.initial_scope,rows);head=rows[-1]['record_sha256'] if rows else '0'*64
            payload={'scope':scope,'grant':grant,'previous_head_sha256':head,
                'resource_amendment':{'old_seconds_max':state['scope']['development_seconds_max'],
                    'new_seconds_max':scope['development_seconds_max'],'first_load_epoch':state['first_load_epoch'],
                    'attempts':state['attempts'],'budget_reset':False,'old_budget_recredited':False}}
            replay(self.initial_scope,rows+[{'kind':'resource_runtime_revision_accepted','payload':payload,'previous_sha256':head}])
            return self.log.append_locked('resource_runtime_revision_accepted',payload)
    def confirm(self,snap,receipt):
        return self._event('owner_preload_confirmed',{'snapshot':snap,'receipt':receipt})
    def resume_after_owner_pause(self):
        self.budget()
        return self._event('owner_resume_requested',{'attempts':self.observation()['attempts']})
    def start(self):
        state=self.observation()
        self._event('attempt_load_intent',{'attempt':state['attempts']+1,'epoch':self.wall()})
        return self.observation()['attempts']
    def budget(self):
        state=self.observation();now=self.wall()
        require(type(now) in (int,float) and math.isfinite(now),'recovery_budget_clock')
        if state['first_load_epoch'] is None:return self.scope['development_seconds_max']-60
        require(now>=state['last_epoch'],'recovery_clock_regression')
        remaining=min(state['first_load_epoch']+self.scope['development_seconds_max']-60,
                      self.scope['generation_cutoff_epoch']-60)-now
        require(remaining>0,'recovery_shared_budget_exhausted')
        self._event('budget_observation',{'epoch':now})
        return remaining
    def ready(self,anchor):
        return self._event('worker_ready',{'attempt':self.observation()['attempts'],'raw_anchor_sha256':anchor})
    def begin(self,anchor):
        return self._event('generation_begin_intent',{'attempt':self.observation()['attempts'],'raw_anchor_sha256':anchor})
    def expose_private(self,anchor):
        # Trusted owner-side data accessor must call before access, never afterwards.
        return self._event('private_exposure_intent',{'attempt':self.observation()['attempts'],'raw_anchor_sha256':anchor})
    def failed(self,error,proof):
        state=self.observation();decision=retry_decision(self.scope,state['attempts'],state['formal_consumed'],error,proof)
        self._event('attempt_failed',{'attempt':state['attempts'],'error':error,'proof':proof,'decision':decision})
        return decision
    def reconcile(self,error,proof):
        state=self.observation();decision=retry_decision(self.scope,state['attempts'],state['formal_consumed'],error,proof)
        self._event('cleanup_reconciled',{'error':error,'proof':proof,'decision':decision})
        return decision
    def completed(self,anchor):
        return self._event('attempt_completed',{'attempt':self.observation()['attempts'],'raw_anchor_sha256':anchor})

class EngineeringFault(RuntimeError):
    def __init__(self,category,message):
        require(category in ('startup','transport','native_operational','capture','quality','integrity'),
                'recovery_error_category')
        super().__init__(message);self.recovery_category=category

class AttemptFailure(RuntimeError):
    def __init__(self,original,decision,secondary):
        super().__init__(str(original));self.original=original;self.decision=decision;self.secondary=secondary

class RecoveryController:
    """Fixed actors come only from the future independently frozen field entry.

    preflight is read-only; owner_confirm precedes start/load; verify_ready and
    verify_cleanup recompute retained raw anchors. No producer counter is PASS.
    The same campaign/log/grant survives bounded engineering attempts.
    """
    def __init__(self,campaign,grant,*,guard,preflight,owner_confirm,load_worker,
                 verify_ready,run_public,stop_worker,cleanup_native,finalize_capture,verify_cleanup):
        self.campaign,self.grant=campaign,grant
        self.guard,self.preflight,self.owner_confirm=guard,preflight,owner_confirm
        self.load_worker,self.verify_ready,self.run_public=load_worker,verify_ready,run_public
        self.stop_worker,self.cleanup_native=stop_worker,cleanup_native
        self.finalize_capture,self.verify_cleanup=finalize_capture,verify_cleanup
    def run_once(self):
        c=self.campaign
        require_grant(c.scope,self.grant);self.guard()
        require(c.scope['phase']=='public_engineering','formal_owner_private_entry_required')
        pre=self.preflight();self.guard()
        state=c.observation()
        if state['receipt'] is None:
            receipt=self.owner_confirm(pre)
            if receipt is None:return {'status':'WAITING_OWNER','model_loaded':False,'attempt_consumed':False}
            c.confirm(pre,receipt)
        else:
            # Permit covers finite retries only with the exact SAME snapshot.
            validate_receipt(c.scope,pre,state['receipt']['receipt'])
        self.guard();attempt=c.start();worker=None;cleanup_spent=set();observed={}
        try:
            c.budget();worker=self.load_worker(attempt)
            self.guard();c.budget()
            ready_anchor=self.verify_ready(worker,pre)
            c.ready(ready_anchor);self.guard();c.budget()
            c.begin(ready_anchor)  # Durable before generation callback.
            anchor=self.run_public(worker,attempt)
            self.guard();c.budget()
            # Successful execution still needs known cleanup and independent final audit.
            cleanup_spent.add('stop');observed['stop']=self.stop_worker(worker)
            cleanup_spent.add('native');observed['native']=self.cleanup_native()
            cleanup_spent.add('capture');observed['capture']=self.finalize_capture()
            proof=self.verify_cleanup(worker,observed['stop'],observed['native'],observed['capture'])
            if proof.get('capture_complete') is not True:
                raise EngineeringFault('capture','recovery_success_diagnostics_incomplete')
            if not all(proof.get(k) is True for k in
                       ('qualified_target_absent','known_native_cleanup_complete','private_exposure_absent')):
                raise EngineeringFault('native_operational','recovery_success_cleanup_unknown')
            c.completed(anchor)
            return {'status':'AWAITING_INDEPENDENT_AUDIT','attempt':attempt,'whole_field_pass':False}
        except BaseException as original:
            secondary=[]
            # Each known actor exactly once even when an earlier cleanup raises.
            # If success-path cleanup already ran, don't resend it on a later failure.
            for name,action in (('stop',lambda:self.stop_worker(worker)),
                                ('native',self.cleanup_native),('capture',self.finalize_capture)):
                if name in cleanup_spent:continue
                cleanup_spent.add(name)
                try:observed[name]=action()
                except BaseException as error:secondary.append({'action':name,'error_type':type(error).__name__})
            try:proof=self.verify_cleanup(worker,observed.get('stop'),observed.get('native'),observed.get('capture'))
            except BaseException as error:
                secondary.append({'action':'independent_cleanup_verification','error_type':type(error).__name__})
                proof={'raw_anchor_sha256':sha(secondary),'capture_complete':False,
                       'qualified_target_absent':False,'known_native_cleanup_complete':False,'private_exposure_absent':False}
            category=('cancelled' if isinstance(original,(KeyboardInterrupt,SystemExit)) else
                      getattr(original,'recovery_category','startup' if worker is None else 'integrity'))
            try:decision=c.failed(category,proof)
            except BaseException as error:
                secondary.append({'action':'recovery_failure_record','error_type':type(error).__name__})
                decision='PAUSED_RECONCILIATION'
            raise AttemptFailure(original,decision,secondary) from original
    def run(self):
        # Already-persisted failures/counts/budget are included; never a fresh counter.
        while True:
            try:return self.run_once()
            except AttemptFailure as failure:
                if failure.decision not in ('RETRYABLE_ENGINEERING','RETRYABLE_ENGINEERING_DIAGNOSTICS_INCOMPLETE'):raise
