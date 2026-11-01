#!/usr/bin/env python3
"""One admitted zero-model native probe; --check has no live effects."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    sys.path.append('/opt/anaconda3/lib/python3.13/site-packages')
    from training.lora_common_probe_runner import prepare, controller
    from plugin.rhino_listener.lora_common_probe import admit, request_shutdown, wait_for_host_reply
    from plugin.rhino_listener.lora_development_admission import source_guard
    from plugin.rhino_listener.c5_research_channel import read_json, publish_json, remove_private_key
    from plugin.rhino_listener.c5_research_native import digest, require
    from plugin.rhino_listener.lora_development_runtime import failure_record
    package = json.loads((ROOT/'common-probe-package.json').read_text())
    prepare(ROOT, package)
    if args.check:
        print(json.dumps({'status': 'passed', 'package_sha256': digest(package), 'model_loads': 0,
            'rhino_calls': 0, 'grant_or_state_created': False, 'actual_entry_preparation_used': True})); return
    require(str(Path(sys.executable).resolve()) == package['python'], 'fixed CPU interpreter required')
    state = admit(ROOT, package)
    require(shutil.disk_usage(state).free >= 4*1024**3, 'probe evidence and backup reserve unavailable')
    started = time.monotonic(); runtime = digest(package)
    publish_json(state, 'probe.claim.json', {'package_sha256': runtime, 'wall': time.time()})
    for name in ('host', 'controller', 'journal', 'permission', 'fixtures'): (state/name).mkdir(mode=0o700)
    host_state = state/'host'; deadline = None; rows = []; failures = []; final = key = None
    def source(): source_guard(ROOT, package['source_files'])
    def guard():
        source()
        require(shutil.disk_usage(state).free >= 2*1024**3, 'cleanup storage reserve reached')
        require(time.time() < package['lease_end_epoch'] - 900, 'lease cleanup cutoff')
        require(deadline is None or time.monotonic() < deadline, 'slot deadline')
    def await_json(name, until, *, stop_on_timeout=False):
        return wait_for_host_reply(host_state,name,until,runtime,stop_on_timeout=stop_on_timeout)
    def host(envelope):
        nonlocal deadline
        p = envelope['payload']; action = p['request']['action']
        if action == 'open': deadline = time.monotonic() + package['plan']['limits']['slot_seconds']
        until = time.monotonic()+30 if action in {'close', 'stop'} else deadline
        publish_json(host_state, 'request-%04d.json'%p['sequence'], envelope)
        result = await_json('response-%04d.json'%p['sequence'], until, stop_on_timeout=action not in {'close','stop'})
        if action == 'stop': deadline = None
        return result
    secret = secrets.token_bytes(32)
    try:
        publish_json(state, 'host-secret.json', {'package_sha256': runtime, 'key_hex': secret.hex()})
        print('Waiting for the separately approved common probe Rhino entry', flush=True)
        ready = await_json('host-ready.json', time.monotonic()+package['plan']['limits']['host_ready_seconds'], stop_on_timeout=True)
        require(ready['runtime_sha256'] == runtime and ready['entry_return_release_observed'] is True,
                'host readiness differs')
        runner = controller(ROOT, package, state, secret, host, guard, source)
        rows = runner.results; runner.run()
    except BaseException as exc:
        failures.append(failure_record(exc, 'probe'))
    finally:
        try:
            request_shutdown(host_state, runtime)
            final = await_json('host-settlement.json', time.monotonic()+30)
            require(final['runtime_sha256'] == runtime and final['status'] == 'host_stopped'
                    and final['exact_delegate_remove_returned'] is True, 'host cleanup unknown')
            key = remove_private_key(state, 'host-secret.json')
        except BaseException as exc: failures.append(failure_record(exc, 'cleanup'))
        publish_json(state, 'probe-result.json', {'package_sha256': runtime, 'rows': rows, 'failures': failures,
            'host': final, 'key_removal': key, 'elapsed_seconds': time.monotonic()-started,
            'model_loads': 0, 'model_quality_evidence': False, 'phase_one_complete': False})
    require(not failures and len(rows) == package['capacity']['slots'] and all(r['outcome'] == 'success' for r in rows),
            'probe incomplete or failed; retain evidence, no automatic retry')


if __name__ == '__main__': main()
