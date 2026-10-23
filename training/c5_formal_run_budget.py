"""Prospective GPU-residency accounting; original wall timeline stays intact."""
import math
import time
from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.c5_research_channel import publish_json
from plugin.rhino_listener.c5_run_package_policy import validate_policy, remaining_window


class ResidencyBudget:
    def __init__(self, package, basis, *, wall=time.time, mono=time.monotonic, legacy_boundary_sha256=None):
        self.package, self.basis = package, dict(basis)
        self.legacy_boundary_sha256=legacy_boundary_sha256
        self.policy = validate_policy(package['policy'])
        require(set(basis) == {'charged_before_seconds', 'load_intent_epoch', 'legacy_first_load_epoch'}
                and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in basis.values()),
                'run_package_budget_basis')
        self.wall, self.mono = wall, mono
        self.start_wall = basis['load_intent_epoch']
        now, monotonic = wall(), mono()
        require(self.start_wall <= now, 'run_package_load_clock')
        self.start_mono = monotonic - (now - self.start_wall)
        self.last_wall, self.last_mono = now, monotonic
        self.check()

    def check(self):
        now, monotonic = self.wall(), self.mono()
        require(math.isfinite(now) and math.isfinite(monotonic)
                and now >= self.last_wall and monotonic >= self.last_mono, 'run_package_clock_regression')
        self.last_wall, self.last_mono = now, monotonic
        elapsed = max(now - self.start_wall, monotonic - self.start_mono)
        remaining = min(self.policy['gpu_residency_seconds_max'] - self.basis['charged_before_seconds'] - elapsed,
                        self.policy['research_reservation_seconds_max']-66773.24127721786-self.basis['charged_before_seconds']-elapsed,
                        self.package['lease_expiry_epoch'] - now) - self.policy['export_reserve_seconds']
        require(remaining > 0, 'run_package_residency_or_lease_stop')
        return remaining

    def settle(self, state, status):
        now, monotonic = self.wall(), self.mono()
        require(now >= self.last_wall and monotonic >= self.last_mono, 'run_package_settlement_clock')
        stop=now;elapsed=max(now-self.start_wall,monotonic-self.start_mono);basis='worker_before_exit'
        if (state/'export-supervisor-original.json').exists():
            from plugin.rhino_listener.c5_research_channel import read_json
            exported=read_json(state,'export-supervisor-original.json');final=exported['final']
            require(final['child_exit_reaped'] is True and type(final['child_wait_status']) is int
                and type(final['epoch']) in (int,float) and math.isfinite(final['epoch'])
                and self.start_wall<=final['epoch']<=now,'run_package_actual_residency_exit_required')
            stop=final['epoch'];elapsed=stop-self.start_wall;basis='original_qualified_gpu_exit'
            worker=exported.get('worker_resource')
            if worker is not None:elapsed=max(elapsed,worker['elapsed_seconds_including_load_and_idle'])
        value = {'study_id': self.policy['study_id'], 'status': status, 'accounting': 'gpu_residency_v1',
                 'start_epoch': self.start_wall, 'stop_epoch': stop,'observation_epoch':now,
                 'settlement_basis':basis,
                 'elapsed_seconds_including_load_and_idle': elapsed,
                 'charged_before_seconds': self.basis['charged_before_seconds'],
                 'legacy_first_load_epoch': self.basis['legacy_first_load_epoch'],
                 'cap_seconds': self.policy['gpu_residency_seconds_max'],
                 'run_package_sha256': digest(self.package), 'resource_boundary_sha256':self.legacy_boundary_sha256, 'replay_allowed': False}
        publish_json(state, 'resource-settlement.json', value)
        return value


def budget_for(freeze, permit):
    if 'run_package' in freeze:
        return ResidencyBudget(freeze['run_package'], permit['budget_basis'],legacy_boundary_sha256=digest(freeze['resource_boundary']))
    from training.c5_formal_reuse_budget import FormalBudgetV2
    now, mono = time.time(), time.monotonic()
    return FormalBudgetV2(freeze['resource_boundary'], start={
        'wall': permit['first_load_epoch'], 'mono': mono-(now-permit['first_load_epoch'])})


def require_recovery_window(package, observation, *, now=None, remaining_work_seconds=None):
    now = time.time() if now is None else now
    policy = package['policy']
    work = policy['remaining_chain_upper_seconds'] if remaining_work_seconds is None else remaining_work_seconds
    value = remaining_window(policy, charged_seconds=observation['charged_gpu_seconds'],
                             remaining_work_seconds=work, now=now, expiry=package['lease_expiry_epoch'])
    require(value['can_load'], 'run_package_remaining_work_window_unavailable')
    return value
