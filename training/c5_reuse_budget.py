"""New development wall reservation, including loading/idle/stop/export."""
import math
import time
from training.c5_reuse_evidence import require


class ReuseBudget:
    def __init__(self,resources,*,wall=time.time,mono=time.monotonic):
        self.resources=dict(resources); self.wall,self.mono=wall,mono
        self.start_wall,self.start_mono=wall(),mono(); self.last=self.start_mono
        self.cap=min(resources['development_seconds_max'],resources['remaining_gpu_seconds'],
                     resources['original_cumulative_seconds_max']-resources['prior_cumulative_upper_bound_seconds'],
                     resources['generation_cutoff_epoch']-self.start_wall)
        require(type(self.cap) in (int,float) and math.isfinite(self.cap) and self.cap>0,'reuse_budget_unavailable')
        self.check()

    def check(self):
        now=self.mono(); utc=self.wall()
        require(type(now) in (int,float) and math.isfinite(now) and self.last<=now<self.start_mono+self.cap
                and self.start_wall<=utc<self.resources['generation_cutoff_epoch'],'reuse_complete_wall_budget')
        self.last=now
        return min(self.start_mono+self.cap-now,self.resources['generation_cutoff_epoch']-utc)

    def observation(self):
        elapsed=self.mono()-self.start_mono
        require(math.isfinite(elapsed) and elapsed>=0,'reuse_budget_observation')
        return {'elapsed_wall_seconds':elapsed,'start_epoch':self.start_wall,'cap_seconds':self.cap,
                'prior_cumulative_upper_bound_seconds':self.resources['prior_cumulative_upper_bound_seconds'],
                'physical_gpu_release_independently_verified':None}
