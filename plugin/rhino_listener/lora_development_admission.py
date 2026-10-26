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
    source_guard(root, package['source_files'])
    require(time.time() < package['lease_end_epoch'], 'lease ended')
    return state


def sessions_available(modules, package):
    """Allow only the precisely retired new-study predecessor; never detach old work."""
    prior = package.get('continuation')
    for name, module in tuple(modules.items()):
        if not name.startswith(('rhino_research_', 'rhino_c5_', 'rhino_lora_')): continue
        session = getattr(module, '_SESSION', None)
        if session is None: continue
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
