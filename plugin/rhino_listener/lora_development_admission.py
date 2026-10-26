"""Small Python 3.9 admission shared with the separately approved host entry.

Checks exact owner record and frozen project bytes; does not claim closure of
the entire already-running Rhino host, loaded CLR assemblies or third-party UI.
"""
import hashlib
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
