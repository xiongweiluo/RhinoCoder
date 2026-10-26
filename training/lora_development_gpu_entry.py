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


def gpu_absent(pid):
    result = subprocess.run(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
        text=True, capture_output=True, timeout=10, check=True)
    rows = [row.strip() for row in result.stdout.splitlines() if row.strip()]
    require(all(row.isdigit() for row in rows), 'GPU process observation unknown')
    return str(pid) not in rows


def supervise(root, package, state):
    require(shutil.disk_usage(state).free >= 2 * 1024**3, 'GPU evidence reserve unavailable')
    start = {'wall': time.time(), 'monotonic': time.monotonic(), 'package_sha256': digest(package)}
    publish_json(state, 'gpu-started.claim.json', start)
    budget = WorkBudget(package['limits'], package['lease_end_epoch'],
                        first_wall=start['wall'], first_mono=start['monotonic'])
    outer = JsonPipe(sys.stdin.fileno(), sys.stdout.fileno())
    exposed, child, stopped, error = False, None, None, None
    attempts = []
    try:
        for number in range(package['limits']['max_load_attempts']):
            budget.work(remaining_slots=32, loading=True)
            verify_source(root, package['source_files'])
            attempt = state / ('load-%d' % number)
            attempt.mkdir(mode=0o700)
            publish_json(attempt, 'attempt.claim.json', {'number': number, 'first_start': start,
                         'package_sha256': digest(package), 'tasks_exposed': False})
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
                    deadline = time.monotonic() + 600
                    child.pipe.send({'action': 'release_load', 'package_sha256': digest(package),
                                     'parent_pid': os.getpid()}, deadline)
                    ready = child.pipe.receive(deadline)
                    require(ready == {'status': 'ready', 'package_sha256': digest(package),
                        'model_identities': package['model_identities']}, 'model readiness differs')
                except BaseException as exc:
                    stopped = child.close(); child = None
                    stopped['gpu_absence_verified'] = gpu_absent(stopped['pid'])
                    journal('loading-stop-verified', stopped)
                    attempts.append({'number': number, 'ready': False, 'error_type': type(exc).__name__})
                    require(stopped['exit_observed'] and stopped['gpu_absence_verified'], 'loading cleanup unknown')
                    if number + 1 < package['limits']['max_load_attempts']: continue
                    raise
                attempts.append({'number': number, 'ready': True})
                outer.send(ready, time.monotonic() + 10)
                while True:
                    budget.work()
                    message = outer.receive(time.monotonic() + min(150, budget.remaining() - 900))
                    if message == {'action': 'stop', 'package_sha256': digest(package)}: break
                    require(set(message) == {'action', 'request'} and message['action'] == 'infer', 'fixed GPU action required')
                    exposed = True  # Intent persisted before sending any task to the worker.
                    if not (state / 'tasks-exposed.claim.json').exists():
                        publish_json(state, 'tasks-exposed.claim.json', {'request_sha256': digest(message['request'])})
                    verify_source(root, package['source_files'])
                    deadline = time.monotonic() + min(150, budget.remaining() - 900)
                    child.pipe.send(message, deadline)
                    response = child.pipe.receive(deadline)
                    outer.send(response, deadline)
                stopped = child.close(); child = None
                stopped['gpu_absence_verified'] = gpu_absent(stopped['pid'])
                journal('completion-stop-verified', stopped)
                break
    except BaseException as exc:
        error = type(exc).__name__
    finally:
        if child is not None:
            try:
                stopped = child.close()
                stopped['gpu_absence_verified'] = gpu_absent(stopped['pid'])
            except BaseException as exc: error = error or type(exc).__name__
        settlement = {'status': 'gpu_stopped' if stopped and stopped['exit_observed'] and stopped.get('gpu_absence_verified')
                      else 'gpu_cleanup_unknown', 'package_sha256': digest(package), 'attempts': attempts,
            'tasks_exposed': exposed, 'stop': stopped, 'error_type': error,
            'elapsed_seconds_including_load_and_idle': time.monotonic() - start['monotonic'],
            'additional_cost': 0, 'paid_lease_amount': None, 'replay_allowed': False}
        publish_json(state, 'gpu-settlement.json', settlement)
        try: outer.send(settlement, time.monotonic() + 5)
        except (BrokenPipeError, TimeoutError): pass
    return settlement


def worker(root, package, state, number):
    require(number in {0, 1}, 'bounded loading attempt')
    attempt = state / ('load-%d' % number)
    claimed = read_json(attempt, 'attempt.claim.json')
    require(claimed['number'] == number and claimed['package_sha256'] == digest(package), 'parent attempt differs')
    budget = WorkBudget(package['limits'], package['lease_end_epoch'],
        first_wall=claimed['first_start']['wall'], first_mono=claimed['first_start']['monotonic'])
    pipe = JsonPipe(sys.stdin.fileno(), sys.stdout.fileno())
    message = pipe.receive(time.monotonic() + 10)
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
    peer = DevelopmentPeer(state=peer_state, runtime=digest(package), views=field_views(package['development_plan'])['model'],
        identities=package['model_identities'], tokenizer=tokenizer, generate=generate, route_context=route, guard=check)
    pipe.send({'status': 'ready', 'package_sha256': digest(package), 'model_identities': package['model_identities']},
              time.monotonic() + 10)
    while True:
        try: message = pipe.receive(time.monotonic() + min(150, budget.remaining() - 900))
        except EOFError: return
        require(set(message) == {'action', 'request'} and message['action'] == 'infer', 'fixed worker request required')
        response = peer.infer(message['request'])
        pipe.send(response, time.monotonic() + 10)
