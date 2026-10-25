"""Finite formal phase budget; prior development clocks are retained separately.

No historical amount is filled with zero. Waiting for pre-load owner input is
not an attempt. Reattachment must supply the original start and cannot renew it.
"""
import math
import time
from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_research_channel import publish_json

from plugin.rhino_listener.c5_formal_reuse_resource_policy import validate_boundary

class FormalBudgetV2:
    def __init__(self,boundary,*,wall=time.time,mono=time.monotonic,start=None):
        validate_boundary(boundary);self.boundary=dict(boundary);self.wall,self.mono=wall,mono
        now,monotonic=wall(),mono()
        require(all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in (now,monotonic)),
            'formal_reuse_budget_clock')
        if start is None:
            require(now+64800<=boundary['generation_cutoff_epoch'],'formal_reuse_full_window_unavailable')
            self.start_wall,self.start_mono=now,monotonic
        else:
            require(type(start) is dict and set(start)=={'wall','mono'}
                and all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in start.values())
                and start['wall']<=now and start['mono']<=monotonic,'formal_reuse_original_start_required')
            self.start_wall,self.start_mono=start['wall'],start['mono']
            require(self.start_wall+64800<=boundary['generation_cutoff_epoch'],'formal_reuse_original_window_invalid')
        self.cap=64800;self.last_wall,self.last_mono=now,monotonic;self.check()
    def check(self):
        now,monotonic=self.wall(),self.mono()
        require(all(type(v) in (int,float) and math.isfinite(v) for v in (now,monotonic))
            and now>=self.last_wall and monotonic>=self.last_mono,'formal_reuse_clock_regression')
        self.last_wall,self.last_mono=now,monotonic
        remaining=min(64740-(monotonic-self.start_mono),
            self.start_wall+64740-now,self.boundary['generation_cutoff_epoch']-60-now,
            self.boundary['research_cumulative_max_seconds']-self.boundary['development_elapsed_to_release_seconds']-(monotonic-self.start_mono)-60)
        require(remaining>0,'formal_reuse_budget_stop');return remaining
    def settle(self,state,status):
        elapsed=self.mono()-self.start_mono
        require(math.isfinite(elapsed) and elapsed>=0,'formal_reuse_settlement_clock')
        from plugin.rhino_listener.c5_formal_reuse_scope import STUDY_ID
        value={'study_id':STUDY_ID,'status':status,'elapsed_seconds_including_load_and_idle':elapsed,
            'cap_seconds':64800,'start_epoch':self.start_wall,'stop_epoch':self.wall(),
            'resource_boundary_sha256':digest(self.boundary),'replay_allowed':False}
        publish_json(state,'resource-settlement.json',value);return value
