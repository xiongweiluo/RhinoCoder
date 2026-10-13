"""One campaign wall reservation, retained across entry/process/attempt restarts."""
import math
import time
from training.c5_reuse_evidence import require

class FieldBudget:
    def __init__(self,campaign,*,wall=time.time,mono=time.monotonic,persist=True):
        self.campaign,self.wall,self.mono=campaign,wall,mono
        self.persist=persist
        self.start_wall,self.start_mono=wall(),mono();self.last_mono=self.start_mono
        state=campaign.observation();require(state['first_load_epoch'] is not None,'recovery_load_intent_required')
        self.first=state['first_load_epoch'];self.cap=campaign.scope['development_seconds_max']-60
        self.last_durable=state['last_epoch'];self.check()
    def check(self):
        now,utc=self.mono(),self.wall()
        require(all(type(v) in (int,float) and math.isfinite(v) for v in (now,utc))
            and now>=self.last_mono and utc>=self.start_wall+(now-self.start_mono)-2
            and utc>=self.last_durable,'recovery_field_clock_regression')
        state=self.campaign.observation()
        require(state['first_load_epoch']==self.first,'recovery_budget_origin_changed')
        remaining=min(self.first+self.cap,self.campaign.scope['generation_cutoff_epoch']-60)-utc
        require(remaining>0,'recovery_shared_budget_exhausted');self.last_mono=now
        # At most 300 observations in 5h, plus bounded transition events. The
        # UTC and monotonic checks still run at EVERY RPC/native checkpoint.
        if self.persist and utc-self.last_durable>=60:
            self.campaign.budget();self.last_durable=utc
        return remaining
    def require_attempt_window(self,minimum):
        require(type(minimum) is int and minimum>60 and self.check()>=minimum,
                'recovery_complete_remaining_attempt_window_unavailable')
    def observation(self):
        elapsed=self.wall()-self.first
        return {'elapsed_wall_seconds':elapsed,'start_epoch':self.first,'operational_cap_seconds':self.cap,
            'reserved_wall_seconds':self.campaign.scope['development_seconds_max'],'stop_reserve_seconds':60,
            'within_reserved_wall_seconds':0<=elapsed<=self.campaign.scope['development_seconds_max'],
            'prior_cumulative_upper_bound_seconds':None,'physical_gpu_release_independently_verified':None}
