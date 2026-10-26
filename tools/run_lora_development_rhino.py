#! python 3
"""Frozen new-study ScriptEditor entry; separate exact owner approval required.

No ActiveDoc inspection. Isolated project namespace, no global plugin/training
alias, no model or historical state. Merely committing this file grants nothing.
"""
import importlib
import json
from pathlib import Path
import sys
import time
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]


def start():
    package = json.loads((ROOT / 'lora-development-package.json').read_text())
    sys.dont_write_bytecode = True
    prefix = 'rhino_lora_' + uuid.uuid4().hex
    for name, path in [(prefix, ROOT), (prefix + '.plugin', ROOT / 'plugin'),
                       (prefix + '.plugin.rhino_listener', ROOT / 'plugin/rhino_listener')]:
        module = types.ModuleType(name); module.__path__ = [str(path)]; sys.modules[name] = module
    def load(name): return importlib.import_module(prefix + '.plugin.rhino_listener.' + name)
    prepared = load('lora_development_runtime').prepare_host(ROOT, package)
    admission = load('lora_development_admission')
    state = admission.admit(ROOT, package, 'mac')
    admission.sessions_available(sys.modules, package)
    channel, native = load('c5_research_channel'), load('c5_research_native')
    scope = channel.read_json(state, 'mac-started.claim.json')
    runtime = native.digest(package)
    native.require(scope['package_sha256'] == runtime, 'prepared controller scope differs')
    host_state = state / 'host'
    key = channel.read_json(state, 'host-secret.json')
    native.require(key['package_sha256'] == runtime, 'new host key scope differs')
    secret = bytes.fromhex(key['key_hex'])
    def source(): admission.source_guard(ROOT, package['source_files'])
    def cleanup(): source()  # Disposal is permitted after work cutoff; no new model/native work.
    def guard():
        source()
        reserve = package['limits']['cleanup_export_seconds']
        ceiling = package['limits']['gpu_residency_seconds']
        deadline = package['lease_end_epoch'] - reserve
        if ceiling is not None: deadline = min(deadline, scope['wall'] + ceiling - reserve)
        native.require(time.time() < deadline, 'host work deadline')
    guard()
    import Rhino
    native.require(Rhino.RhinoApp.IsOnMainThread and list(sys.version_info[:2]) == [3, 9]
        and str(Rhino.RhinoApp.Version) == '8.21.25188.17002', 'fixed embedded Rhino runtime required')
    schemas = prepared['schemas']
    host_module = load('lora_development_host')
    def factory(plan, runtime, secret):
        directory = state / 'fixtures' / plan['slot_id']; directory.mkdir(mode=0o700)
        return host_module.RhinoSession(plan, runtime, secret, directory=directory, schemas=schemas, guard=guard)
    host = host_module.DevelopmentHost(state=host_state, runtime=runtime,
        native_views={c['slot_id']: package['native_scope']['native'][c['slot_id']] for c in prepared['schedule']},
        schedule=prepared['schedule'],
        secret=secret, factory=factory, guard=guard, cleanup_guard=cleanup)
    def attach(callback): Rhino.RhinoApp.Idle += callback
    def detach(callback): Rhino.RhinoApp.Idle -= callback
    session = load('lora_development_session').DevelopmentSession(host, host_state, runtime,
        attach=attach, detach=detach, work_guard=guard, cleanup_guard=cleanup, slot_seconds=prepared['config']['slot_seconds'],
        idle_allowed=lambda: not bool(getattr(Rhino.RhinoApp, 'InCommand', False)))
    sys.modules[prefix]._SESSION = session
    session.start()
    return session


if __name__ == '__main__': SESSION = start()
