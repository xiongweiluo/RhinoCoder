"""New-study GPU supervisor/worker functions, inert until exact owner admission.

Independent new state; no historical grants, corpus, run logs or recovery.
The caller supplies the frozen package and already verified owner approval.
"""
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import digest, require
from training.lora_development_authority import WorkBudget, verify_source
from training.lora_development_process import JsonPipe, OwnedChild
from training.lora_development_scope import field_views
from plugin.rhino_listener.lora_development_runtime import configuration, active_schedule, failure_record


def gpu_absent(pid):
    result = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
        text=True, capture_output=True, timeout=10, check=True)
    rows = [row.strip() for row in result.stdout.splitlines() if row.strip()]
    require(all(row.isdigit() for row in rows), 'GPU process observation unknown')
    return str(pid) not in rows


def supervise(root, package, state):
    config = configuration(package)
    campaign = None
    if package.get('schema_version') in {4, 5}:
        from plugin.rhino_listener.lora_development_campaign import Campaign
        campaign = Campaign(package, 'gpu')
    require(shutil.disk_usage(state).free >= 2 * 1024**3, 'GPU evidence reserve unavailable')
    start = {'wall': time.time(), 'monotonic': time.monotonic(), 'package_sha256': digest(package)}
    publish_json(state, 'gpu-started.claim.json', start)
    budget = WorkBudget(package['limits'], package['lease_end_epoch'],
                        first_wall=start['wall'], first_mono=start['monotonic'])
    outer = JsonPipe(sys.stdin.fileno(), sys.stdout.fileno())
    exposed, child, stopped, error = False, None, None, None
    attempts, failures = [], []
    phase = 'loading'
    global_load = None
    try:
        for number in range(package['limits']['max_load_attempts']):
            budget.work(remaining_slots=len(active_schedule(package)), loading=True)
            verify_source(root, package['source_files'])
            if campaign is not None: global_load = campaign.claim_load()
            attempt = state / ('load-%d' % number)
            attempt.mkdir(mode=0o700)
            publish_json(attempt, 'attempt.claim.json', {'number': number, 'first_start': start,
                         'package_sha256': digest(package), 'tasks_exposed': False,
                         'global_load_number': global_load})
            def journal(name, value): publish_json(attempt, name + '.json', value)
            cache = attempt / 'never-created-bytecode-cache'
            require(not cache.exists(), 'new bytecode prefix required')
            command = [package['endpoints']['gpu']['python'], '-I', '-S', '-B', '-X', 'pycache_prefix=' + str(cache),
                       str(root / 'tools/run_lora_development_gpu.py'), '--worker', str(number)]
            env = {k: v for k, v in os.environ.items() if k in {'PATH', 'HOME', 'LANG', 'LC_ALL'}}
            with open(attempt / 'worker.stderr', 'xb') as stderr:
                os.chmod(attempt / 'worker.stderr', 0o600)
                stopped = None
                child = OwnedChild(command, cwd=str(root), env=env, stderr=stderr, journal=journal)
                try:
                    deadline = time.monotonic() + config['load_seconds']
                    child.pipe.send({'action': 'release_load', 'package_sha256': digest(package),
                                     'parent_pid': os.getpid()}, deadline)
                    ready = child.pipe.receive(deadline)
                    require(ready == {'status': 'ready', 'package_sha256': digest(package),
                        'model_identities': package['model_identities']}, 'model readiness differs')
                except BaseException as exc:
                    attempts.append({'number': number, 'ready': False, 'error_type': type(exc).__name__,
                                     'failure': failure_record(exc, 'loading')})
                    phase = 'loading_cleanup'
                    stopped = child.close(); child = None
                    stopped['gpu_absence_verified'] = gpu_absent(stopped['pid'])
                    journal('loading-stop-verified', stopped)
                    require(stopped['exit_observed'] and stopped['gpu_absence_verified'], 'loading cleanup unknown')
                    if number + 1 < package['limits']['max_load_attempts']: continue
                    raise
                attempts.append({'number': number, 'ready': True})
                phase = 'model_transport'
                outer.send(ready, time.monotonic() + config['protocol_reply_seconds'])
                while True:
                    budget.work()
                    message = outer.receive(time.monotonic() + min(config['slot_seconds'], budget.remaining() - config['cleanup_export_seconds']))
                    if message == {'action': 'stop', 'package_sha256': digest(package)}: break
                    require(set(message) == {'action', 'request'} and message['action'] == 'infer', 'fixed GPU action required')
                    exposed = True  # Intent persisted before sending any task to the worker.
                    if campaign is not None: campaign.exposed()
                    if not (state / 'tasks-exposed.claim.json').exists():
                        publish_json(state, 'tasks-exposed.claim.json', {'request_sha256': digest(message['request'])})
                    verify_source(root, package['source_files'])
                    deadline = time.monotonic() + min(config['slot_seconds'], budget.remaining() - config['cleanup_export_seconds'])
                    child.pipe.send(message, deadline)
                    response = child.pipe.receive(deadline)
                    outer.send(response, deadline)
                stopped = child.close(); child = None
                stopped['gpu_absence_verified'] = gpu_absent(stopped['pid'])
                journal('completion-stop-verified', stopped)
                break
    except BaseException as exc:
        error = type(exc).__name__; failures.append(failure_record(exc, phase))
    finally:
        if child is not None:
            try:
                stopped = child.close()
                stopped['gpu_absence_verified'] = gpu_absent(stopped['pid'])
            except BaseException as exc:
                error = error or type(exc).__name__; failures.append(failure_record(exc, 'owned_child_cleanup'))
        settlement = {'status': 'gpu_stopped' if stopped and stopped['exit_observed'] and stopped.get('gpu_absence_verified')
                      else 'gpu_cleanup_unknown', 'package_sha256': digest(package), 'attempts': attempts,
            'tasks_exposed': exposed, 'stop': stopped, 'error_type': error, 'failures': failures,
            'elapsed_seconds_including_load_and_idle': time.monotonic() - start['monotonic'],
            'additional_cost': None if campaign is not None else 0, 'paid_lease_amount': None, 'replay_allowed': False}
        if campaign is not None:
            settlement.update(global_load_number=global_load, paid_resource_actions=0,
                              cost_status='actual_invoice_unknown_no_purchase_or_renewal_performed')
        publish_json(state, 'gpu-settlement.json', settlement)
        if campaign is not None and global_load is not None: campaign.settle_load(global_load, settlement)
        try: outer.send(settlement, time.monotonic() + 5)
        except (BrokenPipeError, TimeoutError): pass
    return settlement


def worker(root, package, state, number):
    config = configuration(package)
    require(number in {0, 1}, 'bounded loading attempt')
    attempt = state / ('load-%d' % number)
    claimed = read_json(attempt, 'attempt.claim.json')
    require(claimed['number'] == number and claimed['package_sha256'] == digest(package), 'parent attempt differs')
    if package.get('schema_version') in {4, 5}:
        from plugin.rhino_listener.lora_development_campaign import Campaign
        campaign = Campaign(package, 'gpu'); campaign.revision()
        require(number == 0 and read_json(campaign.root, 'load-%d.claim.json' % claimed['global_load_number']) == {
            'global_load_number': claimed['global_load_number'], 'revision_id': package['revision_id'],
            'package_sha256': digest(package)}, 'worker requires permanent global loading intent')
    budget = WorkBudget(package['limits'], package['lease_end_epoch'],
        first_wall=claimed['first_start']['wall'], first_mono=claimed['first_start']['monotonic'])
    pipe = JsonPipe(sys.stdin.fileno(), sys.stdout.fileno())
    message = pipe.receive(time.monotonic() + config['protocol_reply_seconds'])
    require(message == {'action': 'release_load', 'package_sha256': digest(package), 'parent_pid': os.getppid()},
            'only the new direct supervisor may release loading')
    owner = read_json(attempt, 'child-created.json')
    require(owner['pid'] == os.getpid() and owner['parent_pid'] == os.getppid(),
            'this exact new Popen child must have been qualified before release')
    publish_json(attempt, 'worker-admitted.claim.json', {'pid': os.getpid(), 'package_sha256': digest(package)})
    # Kernel parent-death signal complements the supervisor's pidfd deadline.
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(1, 15, 0, 0, 0) == 0 and os.getppid() == message['parent_pid'], 'parent lifeline unavailable')
    def guard(): verify_source(root, package['source_files']); budget.work()
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
    os.environ.update({'XDG_CACHE_HOME': str(attempt / 'cache'), 'TRITON_CACHE_DIR': str(attempt / 'triton-cache'),
                       'TORCHINDUCTOR_CACHE_DIR': str(attempt / 'torch-cache')})
    from training.lora_development_loader import load
    tokenizer, generate, route, check = load(root, package, guard)
    from training.lora_development_peer import DevelopmentPeer
    peer_state = attempt / 'peer'; peer_state.mkdir(mode=0o700)
    views = field_views(package['development_plan'])['model']
    allowed = {c['slot_id'] for c in active_schedule(package)}
    peer = DevelopmentPeer(state=peer_state, runtime=digest(package), views={k: v for k, v in views.items() if k in allowed},
        identities=package['model_identities'], tokenizer=tokenizer, generate=generate, route_context=route, guard=check)
    pipe.send({'status': 'ready', 'package_sha256': digest(package), 'model_identities': package['model_identities']},
              time.monotonic() + config['protocol_reply_seconds'])
    while True:
        try: message = pipe.receive(time.monotonic() + min(config['slot_seconds'], budget.remaining() - config['cleanup_export_seconds']))
        except EOFError: return
        require(set(message) == {'action', 'request'} and message['action'] == 'infer', 'fixed worker request required')
        response = peer.infer(message['request'])
        pipe.send(response, time.monotonic() + config['protocol_reply_seconds'])
