"""New accepted finite budget. Constructor is not an execution grant."""
import math
import time
from plugin.rhino_listener.c5_formal20_scope_v2 import STUDY_ID
from plugin.rhino_listener.c5_research_native import require,digest
from plugin.rhino_listener.c5_research_channel import publish_json


class FormalBudgetV2:
    def __init__(self, boundary, *, wall=time.time, mono=time.monotonic):
        required = {'owner_confirmed', 'provider_expiry_epoch', 'generation_cutoff_epoch', 'export_reserve_seconds',
            'formal_max_seconds', 'prior_cumulative_seconds', 'original_cumulative_max_seconds',
            'prior_research_seconds', 'research_cumulative_max_seconds'}
        require(isinstance(boundary, dict) and set(boundary) == required and boundary['owner_confirmed'] is True,
            'complete formal resource boundary required')
        require(all(type(boundary[k]) in (int, float) and math.isfinite(boundary[k]) and boundary[k] >= 0
            for k in required - {'owner_confirmed'}), 'finite formal resource amounts required')
        require(all(type(boundary[k]) is int for k in required-{
            'owner_confirmed','prior_cumulative_seconds','prior_research_seconds'}),
            'formal integer ceilings/deadlines required')
        require(0 < boundary['formal_max_seconds'] <= 18000 and boundary['export_reserve_seconds'] >= 900
            and boundary['provider_expiry_epoch'] - boundary['generation_cutoff_epoch'] >= boundary['export_reserve_seconds']
            and boundary['original_cumulative_max_seconds'] == 57600
            and boundary['research_cumulative_max_seconds'] == 21600, 'formal resource limits differ')
        self.wall, self.mono, self.boundary = wall, mono, dict(boundary)
        self.start_wall, self.start_mono = wall(), mono()
        require(boundary['generation_cutoff_epoch']-self.start_wall >= boundary['formal_max_seconds'],
            'insufficient full formal window before cutoff; no arming or private consumption')
        self.cap = min(boundary['formal_max_seconds'], 57600 - boundary['prior_cumulative_seconds'],
            21600 - boundary['prior_research_seconds'], boundary['generation_cutoff_epoch'] - self.start_wall)
        require(self.cap > 0, 'formal resource exhausted')
        self.check()

    def check(self):
        elapsed = self.mono() - self.start_mono
        require(0 <= elapsed < self.cap and self.wall() < self.boundary['generation_cutoff_epoch'], 'formal budget stop')
        return self.cap - elapsed

    def settle(self, state, status):
        elapsed = self.mono() - self.start_mono
        require(math.isfinite(elapsed) and elapsed >= 0, 'formal settlement duration invalid')
        value = {'study_id': STUDY_ID, 'status': status, 'elapsed_seconds_including_load_and_idle': elapsed,
            'cap_seconds': self.cap, 'start_epoch': self.start_wall, 'stop_epoch': self.wall(),
            'resource_boundary_sha256': digest(self.boundary), 'replay_allowed': False}
        publish_json(state, 'resource-settlement.json', value)
        return value
