"""Formal resource accounting and worker plans, without GPU imports."""
from __future__ import annotations

import math
import time

from plugin.rhino_listener.c5_formal20_scope import SLOT, SHA, STUDY_ID
from plugin.rhino_listener.c5_research_native import require, digest
from plugin.rhino_listener.c5_research_channel import publish_json
from training.c5_model_transport import OneShotModelSession, validate_request


def hashed_model_plans(plans):
    import hashlib
    require(isinstance(plans, dict) and len(plans) == 40, 'formal forty model plans required')
    result = {}
    for slot, plan in plans.items():
        require(SLOT.fullmatch(slot) and isinstance(plan, dict) and set(plan) == {'route', 'steps'}
            and plan['route'] in {'base', 'lora'} and slot.endswith('-' + plan['route'])
            and isinstance(plan['steps'], list) and 1 <= len(plan['steps']) <= 3
            and all(isinstance(s, str) and 0 < len(s.encode()) <= 4096 for s in plan['steps'])
            and len(set(plan['steps'])) == 1, 'narrow formal model plan differs')
        result[slot] = {'route': plan['route'], 'task_sha256': hashlib.sha256(plan['steps'][0].encode()).hexdigest(),
            'max_steps': len(plan['steps'])}
    return validate_hashed_plans(result)


def validate_hashed_plans(plans):
    require(isinstance(plans, dict) and len(plans) == 40, 'formal forty hashed plans required')
    for slot, p in plans.items():
        require(isinstance(slot, str) and SLOT.fullmatch(slot) and isinstance(p, dict)
            and set(p) == {'route', 'task_sha256', 'max_steps'} and p['route'] in {'base', 'lora'}
            and slot.endswith('-' + p['route']) and type(p['max_steps']) is int and 1 <= p['max_steps'] <= 3
            and isinstance(p['task_sha256'], str) and SHA.fullmatch(p['task_sha256']), 'formal hashed model policy differs')
    require(set(plans) == {'F%02d-%s' % (n, r) for n in range(1, 21) for r in ('base', 'lora')},
        'formal model slot population differs')
    for n in range(1, 21):
        a, b = plans['F%02d-base' % n], plans['F%02d-lora' % n]
        require(a['task_sha256'] == b['task_sha256'] and a['max_steps'] == b['max_steps'], 'formal paired task policy differs')
    return plans


class FormalModelSession:
    """Reuse the proven one-shot wire, with formal task hashes and step bounds.

    Private text is accepted per requested slot after the Mac consumption
    claim. The bootstrap contains hashes only, never answers/fixture plans.
    """
    def __init__(self, freeze_sha, hashed_plans, *args, **kwargs):
        self.hashed = validate_hashed_plans(hashed_plans)
        self.session = OneShotModelSession(STUDY_ID, freeze_sha, {}, *args, **kwargs)

    @property
    def blocked(self): return self.session.blocked

    def infer(self, sent):
        import hashlib
        validate_request(sent)
        p = self.hashed.get(sent['slot_id'])
        require(p is not None and p['route'] == sent['route'] and sent['step_index'] < p['max_steps']
            and hashlib.sha256(sent['task'].encode()).hexdigest() == p['task_sha256'], 'formal requested task outside sealed plan')
        self.session.plans[sent['slot_id']] = {'route': p['route'], 'steps': [sent['task']] * p['max_steps']}
        return self.session.infer(sent)


class FormalBudget:
    def __init__(self, boundary, *, wall=time.time, mono=time.monotonic):
        required = {'owner_confirmed', 'provider_expiry_epoch', 'generation_cutoff_epoch', 'export_reserve_seconds',
            'formal_max_seconds', 'prior_cumulative_seconds', 'original_cumulative_max_seconds',
            'prior_research_seconds', 'research_cumulative_max_seconds'}
        require(isinstance(boundary, dict) and set(boundary) == required and boundary['owner_confirmed'] is True,
            'complete formal resource boundary required')
        require(all(type(boundary[k]) in (int, float) and math.isfinite(boundary[k]) and boundary[k] >= 0
            for k in required - {'owner_confirmed'}), 'finite formal resource amounts required')
        require(0 < boundary['formal_max_seconds'] <= 10800 and boundary['export_reserve_seconds'] >= 900
            and boundary['provider_expiry_epoch'] - boundary['generation_cutoff_epoch'] >= boundary['export_reserve_seconds']
            and boundary['original_cumulative_max_seconds'] == 57600
            and boundary['research_cumulative_max_seconds'] == 14400, 'formal resource limits differ')
        self.wall, self.mono, self.boundary = wall, mono, dict(boundary)
        self.start_wall, self.start_mono = wall(), mono()
        self.cap = min(boundary['formal_max_seconds'], 57600 - boundary['prior_cumulative_seconds'],
            14400 - boundary['prior_research_seconds'], boundary['generation_cutoff_epoch'] - self.start_wall)
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
