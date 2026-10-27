#! python 3
"""Single ScriptEditor entry; zero models, only the exact admitted new headless probe scope."""
import importlib
import json
from pathlib import Path
import sys
import time
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]


def start(*, final=False):
    sys.dont_write_bytecode = True
    prefix = 'rhino_lora_probe_' + uuid.uuid4().hex
    for name, path in ((prefix, ROOT), (prefix+'.plugin', ROOT),
                       (prefix+'.plugin.rhino_listener', ROOT/'plugin/rhino_listener')):
        module = types.ModuleType(name); module.__path__ = [str(path)]; sys.modules[name] = module
    def load(name): return importlib.import_module(prefix+'.plugin.rhino_listener.'+name)
    if final:
        package, state, _ = load('lora_final_admission').admit(ROOT, 'mac')
        ready = load('lora_development_runtime').prepare_host(ROOT, package)
        plan = package['comparison_plan']
        prepared = {'schemas':ready['schemas'], 'views':package['compiled']['views'],
            'capacity':load('lora_development_runtime').common_capacity(plan),
            'session_options':{'state_contract':plan['state_contract']}}
    else:
        package = json.loads((ROOT/'common-probe-package.json').read_text())
        prepared = load('lora_common_probe').prepare(ROOT, package)
        state = load('lora_common_probe').admit(ROOT, package)
        plan = package['plan']
    channel, native = load('c5_research_channel'), load('c5_research_native')
    runtime = native.digest(package)
    native.require(channel.read_json(state, 'mac-started.claim.json' if final else 'probe.claim.json')['package_sha256'] == runtime, 'controller missing')
    # Existing settled objects may remain in module metadata; never replace an
    # active callback or inspect any existing user document.
    for module in tuple(sys.modules.values()):
        session = vars(module).get('_SESSION') if isinstance(module, types.ModuleType) else None
        if session is not None and hasattr(session, 'host'):
            native.require(session.stopped is True and session.host.current is None, 'another research session active')
    key = channel.read_json(state, 'host-secret.json')
    native.require(key['package_sha256'] == runtime, 'key scope differs')
    secret = bytes.fromhex(key['key_hex'])
    def source(): load('lora_development_admission').source_guard(ROOT, package['source_files'])
    scope = channel.read_json(state, 'mac-started.claim.json') if final else None
    def guard():
        source()
        deadline = package['lease_end_epoch'] - 900
        if final: deadline = min(deadline, scope['wall'] + package['limits']['gpu_residency_seconds'] - 900)
        native.require(time.time() < deadline, 'host lease cutoff')
    import Rhino
    native.require(Rhino.RhinoApp.IsOnMainThread and list(sys.version_info[:2]) == [3, 9]
        and str(Rhino.RhinoApp.Version) == '8.21.25188.17002', 'fixed embedded host required')
    host_module = load('lora_development_host')
    def factory(plan, runtime, secret):
        directory = state/'fixtures'/plan['slot_id']; directory.mkdir(mode=0o700)
        return host_module.RhinoSession(plan, runtime, secret, directory=directory, schemas=prepared['schemas'], guard=guard,
            **prepared['session_options'])
    host = host_module.DevelopmentHost(state=state/'host', runtime=runtime, native_views=prepared['views']['native'],
        schedule=prepared['views']['schedule'], secret=secret, factory=factory, guard=guard, cleanup_guard=source,
        operations=native.CORE, messages_max=prepared['capacity']['host_messages_max'], study=plan['study_id'])
    def attach(callback): Rhino.RhinoApp.Idle += callback
    def detach(callback): Rhino.RhinoApp.Idle -= callback
    session = load('lora_development_session').DevelopmentSession(host, state/'host', runtime,
        attach=attach, detach=detach, work_guard=guard, cleanup_guard=source,
        slot_seconds=plan['limits']['slot_seconds'],
        idle_allowed=lambda: not bool(getattr(Rhino.RhinoApp, 'InCommand', False)))
    sys.modules[prefix]._SESSION = session
    session.start()
    return session


if __name__ == '__main__':
    SESSION = start()
    SESSION.release()
