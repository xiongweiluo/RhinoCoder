#! python 3
"""Formal ScriptEditor entry: verify new freeze/owner/start before private plans.

Run only in the approved formal session, while the owner driver waits for the
hub. Import/preflight does not attach Idle or construct a fixture.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def start():
    import Rhino
    for name, module in tuple(sys.modules.items()):
        if (name.startswith(('rhino_research_', 'rhino_c5_')) or 'candidate_' in name) and getattr(module, '_SESSION', None) is not None:
            raise RuntimeError('another live research session')
    namespace = 'rhino_c5_' + uuid.uuid4().hex
    loader = importlib.util.spec_from_file_location(namespace, ROOT / 'plugin/rhino_listener/__init__.py',
        submodule_search_locations=[str(ROOT / 'plugin/rhino_listener')])
    package = importlib.util.module_from_spec(loader)
    sys.modules[namespace] = package; loader.loader.exec_module(package)
    native = importlib.import_module(namespace + '.c5_research_native')
    channel = importlib.import_module(namespace + '.c5_research_channel')
    provenance = importlib.import_module(namespace + '.c5_research_provenance')
    protocol = importlib.import_module(namespace + '.c5_formal20_scope')
    hub_module = importlib.import_module(namespace + '.c5_formal20_hub')
    environment = importlib.import_module(namespace + '.c5_formal20_environment')
    def public(path):
        native.require(path.resolve() == path and 0 < path.stat().st_size <= 1024 * 1024, 'formal public file invalid')
        def pairs(items):
            result = {}
            for k, v in items:
                native.require(k not in result, 'duplicate formal public JSON key'); result[k] = v
            return result
        return json.loads(path.read_text(), object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite formal JSON')))
    spec, freeze = public(ROOT / protocol.SPEC_FILE), public(ROOT / protocol.FREEZE_FILE)
    approval = channel.read_json(protocol.MAC_STATE, 'owner-approval.json')
    freeze_sha = protocol.authority(spec, freeze, approval)
    native.require(str(ROOT) == freeze.get('mac_source_root') and hashlib.sha256((ROOT / protocol.SPEC_FILE).read_bytes()).hexdigest()
        == freeze['spec_file_sha256'], 'formal Rhino source/spec differs')
    source = provenance.SourceGuard(ROOT, freeze['source_files'], freeze['source_inventory_sha256'], project_prefixes=(namespace,))
    def guard():
        source()
        environment.verify_project_origins(ROOT, freeze['source_files'])
        native.require(sys.version_info[:2] == (3, 9) and str(Rhino.RhinoApp.Version) == freeze['rhino_version'],
            'formal embedded runtime differs')
        for path, sha in freeze['rhino_environment_files'].items():
            p = Path(path)
            native.require(p.is_absolute() and p.resolve() == p and p.is_file()
                and hashlib.sha256(p.read_bytes()).hexdigest() == sha, 'formal Rhino runtime binary/source drift')
        actual = environment.loaded_external_files(ROOT)
        native.require(all(freeze['rhino_environment_files'].get(n) == sha for n, sha in actual.items()),
            'formal unfrozen loaded embedded Python/CLR origin')
        native.require(all(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == sha
            for n, sha in freeze['fixed_public_files'].items()), 'formal Rhino public config drift')
        return freeze['source_inventory_sha256']
    guard()
    started = channel.read_json(protocol.MAC_STATE, 'formal20.started.json')
    native.require(started == {'study_id': protocol.STUDY_ID, 'spec_sha256': native.digest(spec),
        'runtime_freeze_sha256': freeze_sha, 'public_commitment_sha256': spec['public_commitment_sha256'], 'replay_allowed': False},
        'formal permanent started missing')
    prepared = channel.read_json(protocol.MAC_STATE, 'native-prepared.json')
    native.require(prepared['runtime_freeze_sha256'] == freeze_sha, 'formal prepared scope differs')
    # No task/setup body is opened until all gates above pass.
    plans = protocol.native_plans(channel.read_json(protocol.MAC_STATE, 'native-plans.json'))
    native.require(native.digest(plans) == prepared['native_plans_sha256'], 'formal narrow plans changed')
    active = Rhino.RhinoDoc.ActiveDoc
    native.require(Rhino.RhinoApp.IsOnMainThread and active is not None and not native._all_objects(active),
        'usable blank active document required')
    # Attach and pre-attach cleanup compete for the SAME O_EXCL admission.
    # A timeout cannot race a late ScriptEditor start into an unkeyed hook.
    channel.publish_json(protocol.MAC_STATE, 'formal20.hub-admission.claim.json', {'action': 'attach',
        'study_id': protocol.STUDY_ID, 'runtime_freeze_sha256': freeze_sha, 'replay_allowed': False})
    channel.publish_json(protocol.MAC_STATE, 'formal20.hub-started.claim.json', {'study_id': protocol.STUDY_ID,
        'runtime_freeze_sha256': freeze_sha, 'replay_allowed': False})
    schemas = public(ROOT / 'eval/c5/rhino-runtime-schema-v1.json')['core_parameters']
    hub = hub_module.FormalHub(protocol.MAC_STATE, spec, freeze, plans, schemas, guard, active)
    package._SESSION = hub
    tick = hub._callback
    def callback(sender, event):
        tick(sender, event)
        if hub.stopped: package._SESSION = None
    hub._callback = callback; hub.attach()
    print('C5_FORMAL20_APPROVED_HUB_ATTACHED')


if __name__ == '__main__': start()
