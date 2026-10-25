"""New development wall reservation, including loading/idle/stop/export."""
import math
import time
from training.c5_reuse_evidence import require

STOP_RESERVE_SECONDS=60

class ReuseBudget:
    def __init__(self,resources,*,wall=time.time,mono=time.monotonic):
        self.resources=dict(resources); self.wall,self.mono=wall,mono
        self.start_wall,self.start_mono=wall(),mono(); self.last=self.start_mono
        if resources.get('resource_policy') in ('incremental_reuse_unknown_history_v1','incremental_disclosed_followup_unknown_history_v2'):
            require(resources['prior_cumulative_upper_bound_seconds'] is None
                and resources['original_cumulative_compliance_claimed'] is False
                and resources['development_seconds_max']==18000 and resources['remaining_gpu_seconds']==82800
                and self.start_wall+18000<=resources['generation_cutoff_epoch'],
                'reuse_full_phase_reservation_unavailable')
            self.reservation=18000
        else:self.reservation=min(resources['development_seconds_max'],resources['remaining_gpu_seconds'],
                     resources['original_cumulative_seconds_max']-resources['prior_cumulative_upper_bound_seconds'],
                     resources['generation_cutoff_epoch']-self.start_wall)
        self.cap=self.reservation-STOP_RESERVE_SECONDS
        require(type(self.cap) in (int,float) and math.isfinite(self.cap) and self.cap>0,'reuse_budget_unavailable')
        self.check()

    def check(self):
        now=self.mono(); utc=self.wall()
        require(type(now) in (int,float) and math.isfinite(now) and self.last<=now<self.start_mono+self.cap
                and self.start_wall<=utc<self.resources['generation_cutoff_epoch']-STOP_RESERVE_SECONDS,'reuse_complete_wall_budget')
        self.last=now
        return min(self.start_mono+self.cap-now,self.resources['generation_cutoff_epoch']-STOP_RESERVE_SECONDS-utc)

    def observation(self):
        elapsed=self.mono()-self.start_mono
        require(math.isfinite(elapsed) and elapsed>=0,'reuse_budget_observation')
        return {'elapsed_wall_seconds':elapsed,'start_epoch':self.start_wall,'operational_cap_seconds':self.cap,
                'reserved_wall_seconds':self.reservation,'stop_reserve_seconds':STOP_RESERVE_SECONDS,
                'within_reserved_wall_seconds':elapsed<=self.reservation,
                'prior_cumulative_upper_bound_seconds':self.resources['prior_cumulative_upper_bound_seconds'],
                'physical_gpu_release_independently_verified':None}
