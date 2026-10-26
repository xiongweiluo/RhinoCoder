"""Exact new-study admission and bounded work clock, with no grant creation.

Public preparation may construct a package; effects require the owner's
separate exact approval. Historical C5 grants, state and budgets are excluded.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import time

from plugin.rhino_listener.c5_research_native import digest, require
from training.lora_development_plan import review_plan
from training.lora_development_scope import STUDY, _sha, field_views

APPROVAL_BASIS = "repository_owner_explicit_approval_of_this_complete_development_package"


def verify_source(root, files):
    root = Path(root)
    require(root.is_absolute() and root.resolve() == root and type(files) is dict and 0 < len(files) <= 768,
            "bounded exact source bundle required")
    for name, expected in files.items():
        p = Path(name)
        require(type(name) is str and not p.is_absolute() and p.as_posix() == name
                and not any(part in {'.', '..'} for part in p.parts), "relative source path required")
        path = root / p
        require(path.resolve() == path and path.is_file() and path.stat().st_size <= 2 * 1024 * 1024,
                "source file missing, oversized or symlinked")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == _sha(expected), "frozen source bytes changed: " + name)
    return digest(files)


def validate_package(package):
    require(type(package) is dict and set(package) == {'schema_version', 'study_id', 'development_plan',
        'source_files', 'model_identities', 'assets', 'endpoints', 'limits', 'lease_end_epoch', 'resource_policy',
        'host_policy', 'evidence_policy', 'historical_family_overlap', 'execution_ready',
        'loader_policy', 'stop_policy', 'native_scope', 'gpu_hardware'}, "complete development package required")
    require(type(package['schema_version']) is int and package['schema_version'] == 1 and package['study_id'] == STUDY
            and package['execution_ready'] is True, "prepared new-study package required")
    plan = package['development_plan']
    require(package['gpu_hardware'] == {'name': 'NVIDIA GeForce RTX 3090', 'memory_mib': 24576,
        'driver_version': '550.107.02', 'uuid': 'GPU-0e00f0ad-fa5a-eed9-6eee-5877984e02f9'},
        'verified single GPU identity required')
    review = review_plan(plan)
    views = field_views(plan)
    require(package['native_scope'] == {'schedule': views['schedule'], 'native': views['native']},
            'fixed public native scope required')
    from training.lora_development_loader import POLICY
    require(package['loader_policy'] == POLICY and package['stop_policy'] == {
        'target': 'only_new_direct_child_pinned_by_pidfd', 'natural_exit_wait_seconds': 5,
        'sigterm_max': 1, 'sigterm_wait_seconds': 10, 'sigkill_max': 1, 'sigkill_wait_seconds': 10,
        'unknown_exit_blocks_recovery': True}, 'bounded owned child stop policy required')
    assets = package['assets']
    require(type(assets) is dict and set(assets) == {'snapshot_dir', 'adapter_root', 'base_files', 'adapter_files',
            'local_tokenizer_dir', 'tokenizer_files'}, 'fixed asset map required')
    from training.c5_reuse_gpu_loader import SNAPSHOT, ADAPTER, ADAPTER_FILES
    require(assets['snapshot_dir'] == str(SNAPSHOT) and assets['adapter_root'] == str(ADAPTER)
            and assets['adapter_files'] == ADAPTER_FILES and len(assets['base_files']) == 14,
            'historical weight identity must be retained')
    for group in ('base_files', 'adapter_files', 'tokenizer_files'):
        require(type(assets[group]) is dict and assets[group], 'asset inventory required')
        for name, expected in assets[group].items():
            require(type(name) is str and Path(name).name == name and name not in {'.', '..'}, 'single asset filename required')
            _sha(expected)
    require(set(assets['tokenizer_files']) == {'config.json', 'generation_config.json', 'merges.txt',
        'tokenizer.json', 'tokenizer_config.json', 'vocab.json'} and all(
            assets['base_files'][name] == value for name, value in assets['tokenizer_files'].items()),
        'identical local tokenizer files required')
    require(package['limits'] == plan['limits'] and package['resource_policy'] == {
        'lease_paid': True, 'additional_cost_ceiling': 0, 'new_paid_service_or_renewal': False,
        'historical_budget_reuse': False}, "owner-confirmed resource policy differs")
    require(package['host_policy'] == {'only_new_local_documents': True, 'model_writes': 0,
        'existing_project_content_access': False, 'fixture_documents_max': 32, 'auxiliary_documents_max': 0,
        'close_after_use': True, 'legacy_whole_host_byte_closure_claim': False}, "explicit isolated host policy required")
    require(package['evidence_policy'] == {'old_private_materials': False, 'new_public_development_raw_outputs': True,
        'private_owner_controlled_storage': True, 'public_output': 'sanitized_statistics_hashes_and_audit_only'},
        "exact proposed evidence scope required")
    require(type(package['lease_end_epoch']) is int and package['lease_end_epoch'] > 0,
            "actual lease deadline required")
    require(set(package['model_identities']) == {'base', 'current_lora'}, "exact model routes required")
    for identity in package['model_identities'].values(): _sha(identity)
    require(package['model_identities'] == {
        'base': digest({'base': assets['base_files'], 'loader_policy': POLICY}),
        'current_lora': digest({'base': assets['base_files'], 'adapter': assets['adapter_files'], 'loader_policy': POLICY})},
        'model identities must derive from fixed weight and loader bytes')
    require(set(package['endpoints']) == {'mac', 'gpu'}, "two fixed endpoints required")
    for endpoint in package['endpoints'].values():
        require(type(endpoint) is dict and set(endpoint) == {'source_root', 'state_root', 'python', 'environment_sha256'},
                "exact endpoint fields required")
        for key in ('source_root', 'state_root', 'python'):
            p = Path(endpoint[key])
            require(p.is_absolute() and str(p) == endpoint[key] and '..' not in p.parts, "fixed absolute endpoint path required")
        require('lora-development' in Path(endpoint['state_root']).name, "new isolated development state required")
        _sha(endpoint['environment_sha256'])
    require(package['endpoints']['mac']['state_root'] != package['endpoints']['gpu']['state_root'], "separate endpoint roots")
    require(type(package['historical_family_overlap']) is dict and set(package['historical_family_overlap']) == {
        'status', 'owner_summary_sha256'} and package['historical_family_overlap']['status'] in {
            'unknown_disclosed_public_development_only', 'owner_reviewed_family_independence'}, "independence status must be explicit")
    overlap = package['historical_family_overlap']
    if overlap['status'] == 'owner_reviewed_family_independence': _sha(overlap['owner_summary_sha256'])
    else: require(overlap['owner_summary_sha256'] is None, "unknown independence cannot carry invented evidence")
    return review


def verify_approval(package, approval, *, endpoint, source_root, state_root, now=None):
    validate_package(package)
    expected = {'study_id': STUDY, 'actor': 'repository_owner', 'approved': True,
        'package_sha256': digest(package), 'approval_basis': APPROVAL_BASIS,
        'scope': 'one_bounded_public_development_no_training_no_final_test'}
    require(approval == expected and type(approval.get('approved')) is bool, "new exact owner execution approval required")
    paths = package['endpoints'][endpoint]
    require(str(source_root) == paths['source_root'] and str(state_root) == paths['state_root'], "approved endpoint root differs")
    now = time.time() if now is None else now
    require(type(now) in (int, float) and math.isfinite(now)
            and now + package['limits']['gpu_residency_seconds'] <= package['lease_end_epoch'],
            "full initial work and cleanup window unavailable")
    verify_source(source_root, package['source_files'])
    return digest(package)


class WorkBudget:
    """One first-start clock; work admission preserves the cleanup reserve.

    Durable first-start/loading and exposure records are owned by the entry.
    This arithmetic guard does not interrupt a blocked GPU call: its separate
    qualified-child supervisor enforces the same deadline out of process.
    """
    def __init__(self, limits, lease_end_epoch, *, first_wall, first_mono, wall=time.time, mono=time.monotonic):
        require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                    for v in (first_wall, first_mono, lease_end_epoch)), 'valid initial clocks required')
        self.limits, self.lease = dict(limits), lease_end_epoch
        self.first_wall, self.first_mono, self.wall, self.mono = first_wall, first_mono, wall, mono
        self.last_wall, self.last_mono = first_wall, first_mono

    def remaining(self):
        wall, mono = self.wall(), self.mono()
        require(all(type(v) in (int, float) and math.isfinite(v) for v in (wall, mono))
                and wall >= self.last_wall and mono >= self.last_mono, "clock reversal or invalid time")
        self.last_wall, self.last_mono = wall, mono
        elapsed = max(wall - self.first_wall, mono - self.first_mono)
        return min(self.limits['gpu_residency_seconds'] - elapsed, self.lease - wall)

    def work(self, *, remaining_slots=0, loading=False):
        require(type(remaining_slots) is int and 0 <= remaining_slots <= 32 and type(loading) is bool,
                "bounded work request required")
        need = (self.limits['cleanup_export_seconds'] + remaining_slots * self.limits['slot_seconds']
                + (self.limits['load_seconds'] if loading else 0))
        require(self.remaining() >= need, "remaining window cannot cover approved work and cleanup")

    def cleanup(self):
        require(self.remaining() > 0, "resource ceiling reached; no new unbounded work")
