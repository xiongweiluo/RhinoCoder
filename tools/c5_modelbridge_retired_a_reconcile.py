#! python 3
"""One-shot safety closure for retired A after its first hub open was denied.

This is NOT a probe replay or a successful frozen hub stop. It requires a
separate exact owner approval and proves no headless fixture was ever opened.
"""
from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

import Rhino


STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/modelbridge-development-state-20261003-A')
ID = 'C5DEV-MODELBRIDGE-20261003-A'
FREEZE_SHA = '1cb2adb2161ba2f14b2c80b703cc38e3573621a5a86014cf5c15b72883f6cb73'
SELF = Path(__file__).resolve()


def main():
    matches = [(name, module, module._SESSION) for name, module in tuple(sys.modules.items())
               if name.startswith('rhino_c5_') and getattr(module, '_SESSION', None) is not None]
    if len(matches) != 1:
        raise RuntimeError('unique retired modelbridge hub not found')
    name, package, session = matches[0]
    channel = importlib.import_module(name + '.c5_research_channel')
    native = importlib.import_module(name + '.c5_research_native')
    approval = channel.read_json(STATE, 'postfailure-reconciliation-approval.json')
    if approval != {'probe_id': ID, 'actor': 'repository_owner', 'approved': True,
                    'runtime_freeze_sha256': FREEZE_SHA,
                    'cleanup_script_sha256': hashlib.sha256(SELF.read_bytes()).hexdigest(),
                    'scope': 'retired A only; detach blocked idle hook and remove never-used ephemeral keys; no replay'}:
        raise RuntimeError('separate exact reconciliation approval missing')
    result = channel.read_json(STATE, 'result.json')
    first = channel.read_json(STATE, 'hub-response-0001.json')
    second = channel.read_json(STATE, 'hub-response-0002.json')
    if (result.get('status') != 'modelbridge_fail_retired_no_replay'
            or result.get('holdout_calls') != 0
            or any(value.get('status') != 'hub_failed_no_retry' for value in (first, second))
            or session.state != STATE or native.digest(session.freeze) != FREEZE_SHA
            or not session.blocked or not session.attached or session.stopped
            or session.child is not None or session.fixture is not None or session.opened):
        raise RuntimeError('retired no-fixture failure scope differs')
    active = Rhino.RhinoDoc.ActiveDoc
    if (not Rhino.RhinoApp.IsOnMainThread or active is None
            or int(active.RuntimeSerialNumber) != session.active_serial
            or native._all_objects(active)):
        raise RuntimeError('actual active document identity/empty scene differs')
    if any((STATE / (slot + '.engine-started.claim.json')).exists()
           or (STATE / slot / 'engine-created.json').exists()
           for slot in session.spec['slot_order']):
        raise RuntimeError('a fixture may have been opened; no automatic reconciliation')
    channel.publish_json(STATE, ID + '.manual-reconciliation.claim.json', {
        'probe_id': ID, 'runtime_freeze_sha256': FREEZE_SHA,
        'cleanup_script_sha256': approval['cleanup_script_sha256'],
        'no_fixture_or_model_generation_asserted': True, 'replay_allowed': False,
    })
    Rhino.RhinoApp.Idle -= session._callback
    session.attached = False
    removed = {}
    for slot in session.spec['slot_order']:
        removed[slot] = channel.remove_private_key(STATE / slot, 'handoff.key')
    removed['hub'] = channel.remove_private_key(STATE, 'hub.key')
    if not all(proof['actual_absence_checked'] and proof['key_removed'] for proof in removed.values()):
        raise RuntimeError('ephemeral key deletion not independently verified')
    session.stopped = True
    package._SESSION = None
    channel.publish_json(STATE, 'manual-reconciliation.json', {
        'status': 'retired_a_manual_safety_closure_not_frozen_success',
        'probe_id': ID, 'runtime_freeze_sha256': FREEZE_SHA,
        'cleanup_script_sha256': approval['cleanup_script_sha256'],
        'active_serial': session.active_serial, 'fixture_never_opened': True,
        'opened_slots': [], 'idle_hook_detached': True,
        'ephemeral_key_absence': removed, 'probe_replay_allowed': False,
        'formal_quality_claim': False, 'holdout_calls': 0,
    })
    print('C5_MODELBRIDGE_RETIRED_A_MANUAL_SAFETY_CLOSED_NO_REPLAY')


if __name__ == '__main__':
    main()
