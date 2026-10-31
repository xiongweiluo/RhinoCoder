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
    parser.add_argument('--ssh-control', type=Path)
    parser.add_argument('--check', action='store_true', help='Run the actual CPU preparation without authority or execution')
    args = parser.parse_args()
    package = json.loads((ROOT / 'lora-development-package.json').read_text())
    from training.lora_development_local_tokenizer import SITE
    if SITE not in sys.path: sys.path.append(SITE)  # Explicit CPU dependencies; no site hooks.
    from training.lora_development_preflight import prepare, report
    if args.check:
        print(json.dumps(report(ROOT, package, 'mac'), sort_keys=True)); return
    if args.ssh_control is None: parser.error('--ssh-control is required for an approved live run')
    prepared = prepare(ROOT, package, 'mac')
    run(ROOT, package, prepared, args.ssh_control)


def run(root, package, prepared, ssh_control):
    """One transport and cleanup implementation, with explicit study admission."""
    final = package.get('kind') == 'lora-common-final-comparison-v1'
    config = prepared['config']
    tokenizer, verify_environment = prepared['tokenizer'], prepared['check_environment']
    DevelopmentController, DevelopmentJournal, JsonPipe = prepared['controller'], prepared['journal'], prepared['pipe']
    from training.lora_development_authority import verify_approval, verify_source, WorkBudget
    from plugin.rhino_listener.c5_research_channel import read_json, publish_json, remove_private_key
    from plugin.rhino_listener.c5_research_native import digest, require
    from plugin.rhino_listener.lora_development_runtime import failure_record, recovery_context
    state = Path(package['endpoints']['mac']['state_root'])
    if final:
        from plugin.rhino_listener.lora_final_admission import admit
        admitted, _, _ = admit(root, 'mac')
        require(admitted == package, 'final runtime changed')
        require(time.time() + config['gpu_residency_seconds'] < package['lease_end_epoch'], 'complete final window unavailable')
        runtime = digest(package)
    else:
        runtime = verify_approval(package, read_json(state, 'owner-approval.json'), endpoint='mac', source_root=root, state_root=state)
    require(shutil.disk_usage(state).free >= (config['minimum_free_bytes'] if final else 2 * 1024**3), 'Mac evidence reserve unavailable')
    require(Path(sys.executable).resolve() == Path(package['endpoints']['mac']['python']), 'fixed CPU Python required')
    campaign = None
    if package.get('schema_version') in {4, 5}:
        from plugin.rhino_listener.lora_development_campaign import Campaign
        campaign = Campaign(package, 'mac')
        campaign.begin_run()
    start = {'wall': time.time(), 'monotonic': time.monotonic(), 'package_sha256': runtime}
    budget = WorkBudget(package['limits'], package['lease_end_epoch'], first_wall=start['wall'], first_mono=start['monotonic'], maximum_slots=len(prepared['schedule']))
    host_state = state / 'host'
    worker = pipe = journal = None
    gpu_launch_attempted = host_capability_published = False
    rows, error, gpu, host_final, key_removed, exported = [], None, None, None, None, None
    failures, phase = [], 'local_setup'
    def record_failure(exc, stage):
        nonlocal error
        error = error or type(exc).__name__; failures.append(failure_record(exc, stage))
    slot_deadline = None
    def source(): verify_source(root, package['source_files'])
    def guard():
        source(); verify_environment(); budget.work()
        if final:
            from training.lora_comparison_storage import check_evidence_budget
            check_evidence_budget(state, config)
        require(slot_deadline is None or time.monotonic() < slot_deadline, 'controller slot deadline')
    def await_json(directory, name, deadline):
        if final:
            from plugin.rhino_listener.lora_common_probe import wait_for_host_reply
            return wait_for_host_reply(directory, name, deadline, runtime, stop_on_timeout=name != 'host-settlement.json')
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
            remaining = len([c for c in prepared['schedule'] if c['slot_id'] >= p['slot_id']])
            budget.work(remaining_slots=remaining)
            # Final 420 seconds includes both bounded close/stop calls.
            slot_deadline = time.monotonic() + config['slot_seconds'] - (2 * config['host_cleanup_seconds'] if final else 0)
        deadline = (time.monotonic() + config['host_cleanup_seconds'] if action in {'close', 'stop'} else slot_deadline)
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
        publish_json(state, 'mac-started.claim.json', start)
        for name in ['host', 'controller', 'journal', 'fixtures']:
            (state / name).mkdir(mode=0o700)
        secret = secrets.token_bytes(32)
        # Set intent first: a partial publication is conservatively unresolved.
        host_capability_published = True
        publish_json(state, 'host-secret.json', {'package_sha256': runtime, 'key_hex': secret.hex()})
        phase = 'host_readiness'
        print('Waiting for the approved Rhino wrapper: ' + str(root / (package['entrypoints']['rhino'] if final else 'tools/run_lora_development_rhino_wrapper.py')), flush=True)
        ready = await_json(host_state, 'host-ready.json', time.monotonic() + config['host_ready_seconds'])
        require(ready['status'] == 'ready' and ready['runtime_sha256'] == runtime
                and ready['entry_return_release_observed'] is True, 'host readiness differs')
        budget.work(remaining_slots=len(prepared['schedule']), loading=True)
        remote = package['endpoints']['gpu']
        command = [remote['python'], '-I', '-S', '-B', '-X', 'pycache_prefix=' + remote['state_root'] + '/never-created-supervisor-cache',
                   remote['source_root'] + '/' + (package['entrypoints']['gpu'] if final else 'tools/run_lora_development_gpu.py'), '--serve']
        ssh = ['ssh', '-T', '-S', str(ssh_control), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=20', '-o', 'ServerAliveCountMax=3',
               '-p', '22158', 'linux@175.155.64.171', shlex.join(command)]
        stderr = open(state / 'ssh.stderr', 'xb'); os.chmod(state / 'ssh.stderr', 0o600)
        try:
            phase = 'gpu_startup'
            gpu_launch_attempted = True  # Unknown SSH launch outcome is not "never launched".
            worker = subprocess.Popen(ssh, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)
            pipe = JsonPipe(worker.stdout.fileno(), worker.stdin.fileno())
            ready = pipe.receive(time.monotonic() + config['gpu_ready_seconds'])
            publish_json(state, 'gpu-startup-response.json', ready)
            if ready.get('status') in {'gpu_stopped', 'gpu_cleanup_unknown'}:
                require(ready.get('package_sha256') == runtime, 'startup settlement binding differs')
                gpu = ready
            require(ready == {'status': 'ready', 'package_sha256': runtime, 'model_identities': package['model_identities']},
                    'GPU startup did not establish fixed models')
            phase = 'controller'
            journal = DevelopmentJournal(state / 'journal', package['comparison_plan'] if final else package['development_plan'], runtime, campaign=campaign,
                                         recovery=recovery_context(package), compiled=package['compiled'] if final else None)
            contract = prepared['contract_class'](package['comparison_plan'], package['compiled'], prepared['cases'], state / 'permission') if final else None
            controller = DevelopmentController(journal=journal, state=state / 'controller', runtime=runtime, secret=secret,
                schemas=prepared['schemas'], tokenizer=tokenizer, identities=package['model_identities'], host=host, model=model,
                guard=guard, cleanup_guard=source, contract=contract)
            rows = controller.results
            controller.run()
        finally:
            try: stderr.close()
            except BaseException as exc: record_failure(exc, 'ssh_stderr_close')
    except BaseException as exc:
        record_failure(exc, phase)
    finally:
        if pipe is not None:
            try:
                if gpu is None:
                    deadline = time.monotonic() + config['gpu_stop_seconds']
                    pipe.send({'action': 'stop', 'package_sha256': runtime}, deadline)
                    while True:
                        value = pipe.receive(deadline)
                        if value.get('status') in {'gpu_stopped', 'gpu_cleanup_unknown'}:
                            require(value.get('package_sha256') == runtime, 'GPU settlement binding differs')
                            gpu = value; break
                        # Retain a late model response without admitting another dispatch.
                        publish_json(state, 'late-model-response.json', value)
            except BaseException as exc:
                record_failure(exc, 'gpu_stop_transport')
            finally:
                try: worker.stdin.close()
                except BaseException as exc: record_failure(exc, 'ssh_stdin_close')
                try: worker.wait(timeout=config['transport_exit_seconds'])
                except BaseException as exc: record_failure(exc, 'ssh_exit')
                try: worker.stdout.close()
                except BaseException as exc: record_failure(exc, 'ssh_stdout_close')
        if host_capability_published:
            try:
                if final:
                    from plugin.rhino_listener.lora_common_probe import request_shutdown
                    request_shutdown(host_state, runtime)
                else:
                    publish_json(host_state, 'shutdown.request.json', {'runtime_sha256': runtime, 'action': 'shutdown'})
                host_final = await_json(host_state, 'host-settlement.json', time.monotonic() + config['host_cleanup_seconds'])
            except BaseException as exc: record_failure(exc, 'host_shutdown')
        else:
            # No secret could have reached the host: distinguish no startup
            # from an unobserved shutdown, without claiming a callback removal.
            host_final = {'status': 'not_started', 'capability_published': False}
            key_removed = {'key_removed': False, 'actual_absence_checked': not os.path.lexists(state / 'host-secret.json')}
        if host_final and host_final.get('status') == 'host_stopped':
            try: key_removed = remove_private_key(state, 'host-secret.json')
            except BaseException as exc: record_failure(exc, 'key_removal')
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
                    deadline, size = time.monotonic() + config['export_seconds'], 0
                    try:
                        with selectors.DefaultSelector() as selector:
                            selector.register(exporter.stdout, selectors.EVENT_READ)
                            while True:
                                remaining = deadline - time.monotonic()
                                require(remaining > 0 and selector.select(remaining), 'private export timeout')
                                block = os.read(exporter.stdout.fileno(), 65536)
                                if not block: break
                                size += len(block)
                                require(size <= config['export_bytes_max'], 'private export bound exceeded')
                                output.write(block)
                        require(exporter.wait(timeout=10) == 0, 'GPU export process failed')
                    finally:
                        exporter.stdout.close()
                        if exporter.poll() is None:
                            exporter.terminate()  # Only this new CPU SSH export subprocess, never the control master.
                            exporter.wait(timeout=10)
                exported = verify_archive(path, package)
                publish_json(state, 'gpu-export-verified.json', exported)
            except BaseException as exc: record_failure(exc, 'gpu_export')
        claimed_slots = None
        if journal is not None:
            try:
                claimed_slots = sum(os.path.lexists(journal.root / (journal.slot_key(c['slot_id']) + '.claim.json'))
                                    for c in journal.views['schedule'])
            except BaseException as exc: record_failure(exc, 'journal_population')
        result = {'package_sha256': runtime, 'rows': rows, 'claimed_slots': claimed_slots,
            'completed_slot_results': len(rows), 'journal_reconciliation_required': True,
            'error_type': error, 'failures': failures, 'gpu': gpu, 'host': host_final,
            'historical_rows': list(journal.history.values()) if journal is not None else [],
            'gpu_launch_attempted': gpu_launch_attempted,
            'key_removal': key_removed, 'gpu_export': exported, 'elapsed_seconds': time.monotonic() - start['monotonic'],
            'research_complete': False, 'phase_one_complete': False, 'historical_results_changed': False}
        if final:
            result.pop('phase_one_complete')
            result.update(final_comparison_complete=False, independent_evidence_review_pending=True,
                          actual_additional_cost=None, automatic_paid_resource_actions=0)
            try:
                from training.lora_comparison_storage import check_evidence_budget
                result['cleanup_storage'] = check_evidence_budget(state, config, cleanup=True)
            except BaseException as exc: record_failure(exc, 'cleanup_storage')
            result['error_type'] = error
        publish_json(state, 'final-result.json' if final else 'development-result.json', result)
        if campaign is not None: campaign.settle_run(result)
        print(json.dumps({'status': 'stopped_pending_evidence_review', 'claimed_slots': claimed_slots,
                          'completed_slot_results': len(rows),
                          'error_type': error, 'phase_one_complete': False}), flush=True)


if __name__ == '__main__': main()
