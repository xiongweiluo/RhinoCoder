"""Small Python 3.9 admission shared with the separately approved host entry.

Checks exact owner record and frozen project bytes; does not claim closure of
the entire already-running Rhino host, loaded CLR assemblies or third-party UI.
"""
import hashlib
import os
from pathlib import Path
import time

from .c5_research_channel import read_json
from .c5_research_native import digest, require
from .lora_development_channel import STUDY


def retired_predecessors(package):
    """Exact settled R1/R2 lineage; does not read files or grant another run."""
    prior = package.get('continuation')
    if package.get('schema_version') != 3:
        return [prior] if prior is not None else []
    require(type(prior) is dict and set(prior) == {'predecessors', 'charged_prior_seconds',
        'cumulative_seconds_limit', 'prior_load_attempts', 'cumulative_load_attempts_limit'},
        'complete two-batch continuation required')
    fixed = {'charged_prior_seconds': 229, 'cumulative_seconds_limit': 7200,
             'prior_load_attempts': 3, 'cumulative_load_attempts_limit': 4}
    require(all(type(prior[k]) is int and prior[k] == v for k, v in fixed.items()),
            'all three consumed attempts and 229 seconds must be preserved')
    limits = package['limits']
    require(all(type(limits[k]) is int and limits[k] == v for k, v in {
        'gpu_residency_seconds': 6971, 'max_load_attempts': 1, 'max_infrastructure_recoveries': 0,
        'load_seconds': 600, 'slot_seconds': 150, 'cleanup_export_seconds': 900}.items()),
        'one proposed additional attempt, no recovery and unchanged slot limits required')
    expected = (
        ('c1cfb2f13d0c56fb58e65481cc413189016ed8589428a6af869e27f76febf249',
         '706cf374c8179e7c4adf2a462438ba37132cee250a4ba07b136b99cd6221df12', '', 2),
        ('aa280fb64ba123e4d7f999f5b5cd7db4302c2c3bb1337f2c459da938d408df9e',
         '3e58e8d9df79c7d150a8f21522ba6e50869a5737ee20ce3840e8f3451d480f93', '-r2', 1))
    rows = prior['predecessors']
    require(type(rows) is list and len(rows) == 2, 'both retired batches required')
    for row, (runtime, review_sha, suffix, attempts) in zip(rows, expected):
        require(type(row) is dict and set(row) == {'prior_package_sha256', 'prior_review',
            'prior_review_sha256', 'prior_endpoints'}, 'exact predecessor fields required')
        review = row['prior_review']
        require(row['prior_package_sha256'] == runtime and row['prior_review_sha256'] == review_sha
                and digest(review) == review_sha, 'immutable prior review differs')
        require(review['package_sha256'] == runtime and review['load_attempts_consumed'] == attempts
                and review['slot_claims_verified'] == review['model_generation_stages'] == review['fixture_documents_created'] == 0
                and review['replay_allowed'] is False and review['host_secret_absence_verified'] is True
                and len(review['stop_evidence']) == attempts and all(
                    stop['exit_observed'] and stop['gpu_absence_verified'] for stop in review['stop_evidence']),
                'settled no-exposure predecessor required')
        endpoints = row['prior_endpoints']
        require(type(endpoints) is dict and set(endpoints) == {'mac', 'gpu'}, 'both prior endpoints required')
        for name, prefix in [('mac', '/Users/xiongweiluo/RhinoCoder/data'), ('gpu', '/data')]:
            base = prefix + '/lora-development-20261026' + suffix
            require(endpoints[name]['source_root'] == base + '/source'
                    and endpoints[name]['state_root'] == base + '/state-lora-development',
                    'retired endpoint cannot be substituted')
            require(package['endpoints'][name]['source_root'] == prefix + '/lora-development-20261026-r3/source'
                    and package['endpoints'][name]['state_root'] == prefix + '/lora-development-20261026-r3/state-lora-development',
                    'new exact R3 endpoints required; never reuse prior state')
    return rows


def source_guard(root, files):
    root = Path(root)
    require(root.is_absolute() and root.resolve() == root and type(files) is dict and 0 < len(files) <= 768,
            'fixed bounded source root required')
    for name, expected in files.items():
        p = Path(name)
        require(type(name) is str and not p.is_absolute() and p.as_posix() == name
                and not any(part in {'.', '..'} for part in p.parts), 'relative source name required')
        path = root / p
        require(path.resolve() == path and path.is_file() and path.stat().st_size <= 2 * 1024 * 1024,
                'source alias, absence or oversize')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'frozen source bytes differ')


def admit(root, package, endpoint):
    paths = package['endpoints'][endpoint]
    state = Path(paths['state_root'])
    require(str(root) == paths['source_root'] and package['study_id'] == STUDY
            and package['execution_ready'] is True, 'fixed prepared endpoint required')
    expected = {'study_id': STUDY, 'actor': 'repository_owner', 'approved': True,
        'package_sha256': digest(package),
        'approval_basis': 'repository_owner_explicit_approval_of_this_complete_development_package',
        'scope': 'one_bounded_public_development_no_training_no_final_test'}
    require(digest(read_json(state, 'owner-approval.json')) == digest(expected), 'exact new owner execution approval required')
    if package.get('schema_version') == 3: retired_predecessors(package)
    source_guard(root, package['source_files'])
    require(time.time() < package['lease_end_epoch'], 'lease ended')
    return state


def sessions_available(modules, package):
    """Allow only precisely retired predecessors; never detach or alter old work."""
    rows = retired_predecessors(package)
    by_runtime = {row['prior_package_sha256']: row for row in rows}
    for name, module in tuple(modules.items()):
        if not name.startswith(('rhino_research_', 'rhino_c5_', 'rhino_lora_')): continue
        session = getattr(module, '_SESSION', None)
        if session is None: continue
        prior = by_runtime.get(getattr(session, 'runtime', None))
        require(prior is not None, 'another research session remains; no replacement')
        endpoint = prior['prior_endpoints']['mac']
        state = Path(endpoint['state_root'])
        require(name.startswith('rhino_lora_') and list(getattr(module, '__path__', [])) == [endpoint['source_root']]
                and getattr(session, 'runtime', None) == prior['prior_package_sha256']
                and getattr(session, 'state', None) == state / 'host'
                and getattr(session, 'stopped', None) is True
                and getattr(getattr(session, 'host', None), 'current', 'unknown') is None,
                'unrelated or unsettled session cannot be replaced')
        settled = read_json(state / 'host', 'host-settlement.json')
        require(settled['runtime_sha256'] == prior['prior_package_sha256'] and settled['status'] == 'host_stopped'
                and settled['exact_delegate_remove_returned'] is True
                and not os.path.lexists(state / 'host-secret.json'), 'prior host retirement unverified')
