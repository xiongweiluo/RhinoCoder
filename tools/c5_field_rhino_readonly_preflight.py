#! python 3
"""Actual embedded import/runtime inventory; no fixture, hook, model or task.

Run only this entry in ScriptEditor. A report is not an execution grant.
Loaded host assemblies that cannot be byte-frozen are reported as blockers,
not silently excused or used to claim import closure.
"""
import hashlib
import importlib
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/field-rhino-readonly-20261006-v3.json')


def diagnostic_origins(root, modules, assemblies, executable):
    """Collect partial file evidence and *all* blockers; never a closure proof.

    Unlike the admission guard, diagnostics continue after a bad origin. No
    unknown/dynamic origin is resolved by name, trusted by allowlist or skipped
    from the blocker list. Dynamic code needs a separately reviewed design.
    """
    root = Path(root).resolve()
    origins, blockers = set(), []
    for name, module in modules:
        origin = getattr(module, '__file__', None)
        if not origin or str(origin).startswith('<'):
            continue
        path = Path(str(origin))
        if not path.is_absolute():
            blockers.append({'kind':'nonabsolute_python_origin', 'module':name, 'origin':str(origin)})
            continue
        try:
            if path.suffix == '.pyc':
                path = Path(importlib.util.source_from_cache(str(path)))
            path = path.resolve(strict=True)
            if not path.is_relative_to(root):
                origins.add(path)
        except (OSError, ValueError):
            blockers.append({'kind':'unresolved_python_file', 'module':name})
    for row in assemblies:
        if row['dynamic'] or not row['location']:
            blockers.append({'kind':'nonfile_clr_assembly', 'assembly':row['name'], 'dynamic':row['dynamic']})
        else:
            path = Path(row['location'])
            if not path.is_absolute():
                blockers.append({'kind':'nonabsolute_clr_location', 'assembly':row['name']})
            else:
                origins.add(path)
    path = Path(executable)
    if path.is_absolute():
        origins.add(path)
    else:
        blockers.append({'kind':'nonabsolute_python_executable'})
    files = {}
    for path in sorted(origins):
        try:
            path = path.resolve(strict=True)
            if not path.is_file():
                raise ValueError('not regular')
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            files[str(path)] = h.hexdigest()
        except (OSError, ValueError):
            blockers.append({'kind':'unreadable_external_origin', 'origin':str(path)})
    return {'file_backed_partial_inventory':files, 'unverifiable_origins':blockers,
        'partial_inventory_is_closure_proof':False}


def run():
    import Rhino
    namespace = 'rhino_c5_preflight_' + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(namespace, ROOT / 'plugin/rhino_listener/__init__.py',
        submodule_search_locations=[str(ROOT / 'plugin/rhino_listener')])
    package = importlib.util.module_from_spec(spec); sys.modules[namespace] = package; spec.loader.exec_module(package)
    native = importlib.import_module(namespace + '.c5_research_native')
    importlib.import_module(namespace + '.c5_formal20_hub')
    environment = importlib.import_module(namespace + '.c5_formal20_environment')
    source = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ('agent','training','tools','plugin','data_pipeline','eval')
        for p in sorted((ROOT / folder).rglob('*.py'))}
    active = Rhino.RhinoDoc.ActiveDoc
    native.require(Rhino.RhinoApp.IsOnMainThread and active is not None, 'usable active Rhino required')
    before = native.active_content_digest(active)
    live = [n for n, m in tuple(sys.modules.items()) if n.startswith(('rhino_c5_', 'rhino_research_'))
        and getattr(m, '_SESSION', None) is not None]
    files, blockers = {}, []
    try:
        environment.verify_project_origins(ROOT, source)
        files = environment.loaded_external_files(ROOT)
    except BaseException as exc:
        blockers.append({'category': 'actual_embedded_closure_not_freezable', 'error_type': type(exc).__name__,
            'reason': str(exc) if isinstance(exc, native.NativeError) else 'external_origin_inspection_failed'})
    relative_origins = [{'module':name,'origin':str(getattr(m,'__file__')),
        'spec_origin':str(getattr(getattr(m,'__spec__',None),'origin',None))}
        for name,m in tuple(sys.modules.items()) if getattr(m,'__file__',None)
        and not str(getattr(m,'__file__')).startswith('<') and not Path(str(getattr(m,'__file__'))).is_absolute()]
    import System
    assemblies = [{'name':str(a.FullName),'dynamic':bool(a.IsDynamic),
        'location':None if a.IsDynamic else str(a.Location)} for a in System.AppDomain.CurrentDomain.GetAssemblies()]
    diagnostics = diagnostic_origins(ROOT, tuple(sys.modules.items()), assemblies, sys.executable)
    after = native.active_content_digest(active)
    report = {'status':'actual_rhino_readonly_preflight_not_execution_authority', 'source_root':str(ROOT),
        'source_files':source,'source_inventory_sha256':native.digest(source),
        'rhino_version':str(Rhino.RhinoApp.Version),'python':sys.version,
        'python_major_minor':list(sys.version_info[:2]),'loaded_environment_files':files,
        'environment_inventory_sha256':native.digest(files), 'blockers':blockers,
        'relative_module_origins':relative_origins,'loaded_clr_assemblies':assemblies,
        'origin_diagnostics':diagnostics,
        'actual_embedded_closure_verified':bool(files) and not blockers,
        'active_serial':int(active.RuntimeSerialNumber),'active_object_count':len(native._all_objects(active)),
        'active_before_sha256':before,'active_after_sha256':after,'active_unchanged':before==after,
        'live_research_namespaces':live,'fixtures_created':0,'idle_hooks_attached':0,
        'model_calls':0,'private_task_rows_read':0,'execution_ready':False}
    native.require(before==after, 'readonly active content changed')
    fd=os.open(OUTPUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(report,stream,ensure_ascii=False,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    print('C5_FIELD_READONLY_REPORT_WRITTEN closure=' + str(report['actual_embedded_closure_verified']))


if __name__ == '__main__': run()
