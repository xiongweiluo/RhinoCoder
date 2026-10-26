#!/usr/bin/env python3
"""Exact-approved new public development controller, never a final-test entry.

Run only after the owner approves the complete package. Starts one bounded
GPU supervisor over the owner-established SSH control connection and waits
for the separately started frozen Rhino wrapper. Never merges a PR.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import selectors
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-control', type=Path, required=True)
    args = parser.parse_args()
    package = json.loads((ROOT / 'lora-development-package.json').read_text())
    from training.lora_development_local_tokenizer import load_tokenizer, verify_environment
    tokenizer = load_tokenizer(package['assets'])  # CPU only, model backends blocked.
    from training.lora_development_authority import verify_approval, verify_source, WorkBudget
    from training.lora_development_controller import DevelopmentController
    from training.lora_development_scope import DevelopmentJournal
    from training.lora_development_process import JsonPipe
    from plugin.rhino_listener.c5_research_channel import read_json, publish_json, remove_private_key
    from plugin.rhino_listener.c5_research_native import digest, require
    from training.c5_formal20_plan import _schemas
    state = Path(package['endpoints']['mac']['state_root'])
    runtime = verify_approval(package, read_json(state, 'owner-approval.json'), endpoint='mac', source_root=ROOT, state_root=state)
    require(shutil.disk_usage(state).free >= 2 * 1024**3, 'Mac evidence reserve unavailable')
    require(Path(sys.executable).resolve() == Path(package['endpoints']['mac']['python']), 'fixed CPU Python required')
    environment = json.loads((ROOT / 'lora-development-mac-environment.json').read_text())
    require(digest(environment) == package['endpoints']['mac']['environment_sha256'], 'CPU environment binding differs')
    verify_environment(environment)
    start = {'wall': time.time(), 'monotonic': time.monotonic(), 'package_sha256': runtime}
    publish_json(state, 'mac-started.claim.json', start)
    budget = WorkBudget(package['limits'], package['lease_end_epoch'], first_wall=start['wall'], first_mono=start['monotonic'])
    for name in ['host', 'controller', 'journal', 'fixtures']:
        (state / name).mkdir(mode=0o700)
    secret = secrets.token_bytes(32)
    publish_json(state, 'host-secret.json', {'package_sha256': runtime, 'key_hex': secret.hex()})
    host_state = state / 'host'
    worker = pipe = journal = None
    rows, error, gpu, host_final, key_removed, exported = [], None, None, None, None, None
    slot_deadline = None
    def source(): verify_source(ROOT, package['source_files'])
    def guard():
        source(); verify_environment(environment); budget.work()
        require(slot_deadline is None or time.monotonic() < slot_deadline, 'controller slot deadline')
    def await_json(directory, name, deadline):
        while time.monotonic() < deadline:
            if os.path.lexists(directory / name): return read_json(directory, name)
            if directory == host_state and name != 'host-settlement.json' and os.path.lexists(directory / 'host-settlement.json'):
                raise RuntimeError('host already stopped')
            time.sleep(.05)
        raise TimeoutError('bounded host response wait')
    def host(envelope):
        nonlocal slot_deadline
        p = envelope['payload']; action, seq = p['request']['action'], p['sequence']
        if action == 'open':
            remaining = 32 - int(p['slot_id'].rsplit('-', 1)[1])
            budget.work(remaining_slots=remaining)
            slot_deadline = time.monotonic() + 150
        deadline = (time.monotonic() + 30 if action in {'close', 'stop'} else slot_deadline)
        publish_json(host_state, 'request-%04d.json' % seq, envelope)
        response = await_json(host_state, 'response-%04d.json' % seq, deadline)
        if action == 'stop': slot_deadline = None
        return response
    def model(request):
        guard()
        pipe.send({'action': 'infer', 'request': request}, slot_deadline)
        returned = pipe.receive(slot_deadline)
        guard()
        return returned
    try:
        print('Waiting for the approved Rhino wrapper: ' + str(ROOT / 'tools/run_lora_development_rhino_wrapper.py'), flush=True)
        ready = await_json(host_state, 'host-ready.json', time.monotonic() + 180)
        require(ready['status'] == 'ready' and ready['runtime_sha256'] == runtime
                and ready['entry_return_release_observed'] is True, 'host readiness differs')
        budget.work(remaining_slots=32, loading=True)
        remote = package['endpoints']['gpu']
        command = [remote['python'], '-I', '-S', '-B', '-X', 'pycache_prefix=' + remote['state_root'] + '/never-created-supervisor-cache',
                   remote['source_root'] + '/tools/run_lora_development_gpu.py', '--serve']
        ssh = ['ssh', '-T', '-S', str(args.ssh_control), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=20', '-o', 'ServerAliveCountMax=3',
               '-p', '22158', 'linux@175.155.64.171', shlex.join(command)]
        stderr = open(state / 'ssh.stderr', 'xb'); os.chmod(state / 'ssh.stderr', 0o600)
        try:
            worker = subprocess.Popen(ssh, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
            pipe = JsonPipe(worker.stdout.fileno(), worker.stdin.fileno())
            ready = pipe.receive(time.monotonic() + 1250)
            publish_json(state, 'gpu-startup-response.json', ready)
            if ready.get('status') in {'gpu_stopped', 'gpu_cleanup_unknown'}:
                require(ready.get('package_sha256') == runtime, 'startup settlement binding differs')
                gpu = ready
            require(ready == {'status': 'ready', 'package_sha256': runtime, 'model_identities': package['model_identities']},
                    'GPU startup did not establish fixed models')
            journal = DevelopmentJournal(state / 'journal', package['development_plan'], runtime)
            controller = DevelopmentController(journal=journal, state=state / 'controller', runtime=runtime, secret=secret,
                schemas=_schemas(), tokenizer=tokenizer, identities=package['model_identities'], host=host, model=model,
                guard=guard, cleanup_guard=source)
            rows = controller.results
            controller.run()
        finally: stderr.close()
    except BaseException as exc: error = type(exc).__name__
    finally:
        if pipe is not None:
            try:
                if gpu is None:
                    deadline = time.monotonic() + 180
                    pipe.send({'action': 'stop', 'package_sha256': runtime}, deadline)
                    while True:
                        value = pipe.receive(deadline)
                        if value.get('status') in {'gpu_stopped', 'gpu_cleanup_unknown'}:
                            require(value.get('package_sha256') == runtime, 'GPU settlement binding differs')
                            gpu = value; break
                        # Retain a late model response without admitting another dispatch.
                        publish_json(state, 'late-model-response.json', value)
            except BaseException as exc: error = error or type(exc).__name__
            finally:
                worker.stdin.close()
                try: worker.wait(timeout=40)
                except subprocess.TimeoutExpired: error = error or 'SSHExitUnknown'
                worker.stdout.close()
        try:
            publish_json(host_state, 'shutdown.request.json', {'runtime_sha256': runtime, 'action': 'shutdown'})
            host_final = await_json(host_state, 'host-settlement.json', time.monotonic() + 30)
        except BaseException as exc: error = error or type(exc).__name__
        if host_final and host_final.get('status') == 'host_stopped':
            key_removed = remove_private_key(state, 'host-secret.json')
        if gpu and gpu.get('status') == 'gpu_stopped':
            # Copy only this package's stopped GPU evidence; preserve the raw
            # archive privately and verify its member digests without extracting.
            try:
                from training.lora_development_export import verify_archive
                path = state / 'gpu-evidence.tar'
                export_command = ssh[:-1] + [shlex.join(command[:-1] + ['--export'])]
                with open(path, 'xb') as output, open(state / 'export.stderr', 'xb') as err:
                    os.chmod(path, 0o600); os.chmod(state / 'export.stderr', 0o600)
                    exporter = subprocess.Popen(export_command, stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL)
                    deadline, size = time.monotonic() + 180, 0
                    try:
                        with selectors.DefaultSelector() as selector:
                            selector.register(exporter.stdout, selectors.EVENT_READ)
                            while True:
                                remaining = deadline - time.monotonic()
                                require(remaining > 0 and selector.select(remaining), 'private export timeout')
                                block = os.read(exporter.stdout.fileno(), 65536)
                                if not block: break
                                size += len(block)
                                require(size <= 514 * 1024 * 1024, 'private export bound exceeded')
                                output.write(block)
                        require(exporter.wait(timeout=10) == 0, 'GPU export process failed')
                    finally:
                        exporter.stdout.close()
                        if exporter.poll() is None:
                            exporter.terminate()  # Only this new CPU SSH export subprocess, never the control master.
                            exporter.wait(timeout=10)
                exported = verify_archive(path, package)
                publish_json(state, 'gpu-export-verified.json', exported)
            except BaseException as exc: error = error or type(exc).__name__
        claimed_slots = None
        if journal is not None:
            try:
                claimed_slots = sum(os.path.lexists(journal.root / (journal.slot_key(c['slot_id']) + '.claim.json'))
                                    for c in journal.views['schedule'])
            except BaseException as exc: error = error or type(exc).__name__
        result = {'package_sha256': runtime, 'rows': rows, 'claimed_slots': claimed_slots,
            'completed_slot_results': len(rows), 'journal_reconciliation_required': True,
            'error_type': error, 'gpu': gpu, 'host': host_final,
            'key_removal': key_removed, 'gpu_export': exported, 'elapsed_seconds': time.monotonic() - start['monotonic'],
            'research_complete': False, 'phase_one_complete': False, 'historical_results_changed': False}
        publish_json(state, 'development-result.json', result)
        print(json.dumps({'status': 'stopped_pending_evidence_review', 'claimed_slots': claimed_slots,
                          'completed_slot_results': len(rows),
                          'error_type': error, 'phase_one_complete': False}), flush=True)


if __name__ == '__main__': main()
