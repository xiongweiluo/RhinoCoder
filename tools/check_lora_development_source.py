#!/usr/bin/env python3
"""Check an isolated public source bundle on CPU; never create an execution grant.

Copies only inventoried public files to a temporary directory. No repository
fallback, model/Rhino imports, private data or runtime entries. Existing CPU
JSON-schema dependencies are allowed explicitly; no packages are installed.
This proves the exercised Python import closure, not model or host readiness.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

# Executed in a fresh -I -S -B interpreter, with only the copied bundle and
# standard library and explicit CPU dependencies available. No entry is called.
PROBE = r'''
import hashlib, importlib, json, os, pathlib, sys, sysconfig
root = pathlib.Path(sys.argv[1]).resolve()
stdlib = pathlib.Path(sysconfig.get_path('stdlib')).resolve()
site = pathlib.Path(sys.argv[2] or sysconfig.get_path('purelib')).resolve()
cpu = {'jsonschema', 'jsonschema_specifications', 'referencing', 'rpds',
       'attrs', 'attr', 'typing_extensions'}
project = {'training', 'plugin', 'agent', 'data_pipeline', 'tools'}
sys.path[:] = [str(root)] + [p for p in sys.path if p and
    'site-packages' not in pathlib.Path(p).parts and
    (pathlib.Path(p).resolve().is_relative_to(stdlib) or p.endswith('.zip'))]
sys.path.append(str(site))
blocked = {'torch', 'transformers', 'peft', 'bitsandbytes', 'tensorflow',
           'jax', 'Rhino', 'rhinoscriptsyntax', 'scriptcontext', 'clr', 'System'}
class Block:
    def find_spec(self, fullname, path=None, target=None):
        top = fullname.split('.')[0]
        if top in blocked:
            raise RuntimeError('backend import forbidden: ' + fullname)
        if top not in cpu | project | sys.stdlib_module_names:
            raise ModuleNotFoundError('non-allowlisted dependency: ' + fullname, name=fullname)
sys.meta_path.insert(0, Block())
def audit(event, args):
    if event == 'open':
        name, mode, flags = args
        if isinstance(name, int): raise RuntimeError('file descriptor open forbidden')
        path = pathlib.Path(name).resolve()
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise RuntimeError('write forbidden')
        if not (path.is_relative_to(root) or path.is_relative_to(site) or
                (path.is_relative_to(stdlib) and 'site-packages' not in path.parts)):
            raise RuntimeError('read outside public bundle/stdlib forbidden')
    if event.startswith(('socket.', 'subprocess.', 'os.exec', 'os.spawn')) or event in {
        'os.system', 'os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'ctypes.dlopen'}:
        raise RuntimeError('effect forbidden: ' + event)
sys.addaudithook(audit)
from training import lora_development_loader as loader
if hasattr(loader, 'cpu_dependencies'):
    generation, load_config, load_pinned_tokenizer = loader.cpu_dependencies()
else:  # Historical source, without retrofitting the old loader.
    from training.c5_execution import generation, load_config, load_pinned_tokenizer
load_config(root / 'eval/c5/c5-engineering-config.json')  # Public config only.
targets = (
    'training.lora_development_gpu_entry', 'training.lora_development_peer',
    'training.lora_development_controller', 'training.lora_development_export',
    'training.lora_development_preflight',
    'training.lora_development_local_tokenizer',
    'plugin.rhino_listener.lora_development_admission',
    'plugin.rhino_listener.lora_development_campaign',
    'plugin.rhino_listener.lora_development_native',
    'plugin.rhino_listener.lora_development_session',
    'tools.run_lora_development_mac', 'tools.run_lora_development_gpu',
    'tools.run_lora_development_rhino', 'tools.run_lora_development_rhino_wrapper')
if (root / 'training/lora_common_chain.py').exists():
    targets += ('training.lora_common_chain', 'training.lora_common_probe_runner',
                'training.lora_comparison_statistics', 'training.lora_comparison_storage',
                'plugin.rhino_listener.lora_common_probe')
    if (root / 'plugin/rhino_listener/controlled_snapshot_probe.py').exists():
        targets += ('plugin.rhino_listener.controlled_snapshot_probe',)
if (root / 'tools/run_lora_common_probe.py').exists():
    targets += ('tools.run_lora_common_probe', 'tools.run_lora_common_probe_rhino')
for name in targets: importlib.import_module(name)
if (root / 'common-probe-package.json').exists():
    from training.lora_common_probe_runner import prepare
    prepare(root, json.loads((root / 'common-probe-package.json').read_text()))
origins, cpu_origins = {}, {}
for module in tuple(sys.modules.values()):
    origin = vars(module).get('__file__') if module is not None else None
    if not origin or origin.startswith('<'): continue
    path = pathlib.Path(origin).resolve()
    if path.is_relative_to(root):
        origins[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif path.is_relative_to(site):
        cpu_origins[path.relative_to(site).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif not path.is_relative_to(stdlib):
        raise RuntimeError('unexpected module origin')
assert not blocked.intersection(sys.modules)
print(json.dumps({'status': 'passed', 'origins': origins, 'cpu_origins': cpu_origins, 'targets': targets,
                  'backend_imports': 0, 'runtime_entries_called': 0}))
'''


def probe_source(root, files, *, site=None):
    from training.lora_development_authority import verify_source
    root = Path(root).resolve()
    source_sha = verify_source(root, files)
    with tempfile.TemporaryDirectory(prefix='lora-public-import-') as temporary:
        bundle = Path(temporary).resolve()
        for name, expected in files.items():
            raw = (root / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('source changed during copy: ' + name)
            target = bundle / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-X',
                                'pycache_prefix=' + str(bundle / 'never-created-bytecode-cache'),
                                '-c', PROBE, str(bundle), str(site or '')],
                                cwd=bundle, capture_output=True, text=True, timeout=30)
    if result.returncode:
        return {'status': 'rejected', 'source_inventory_sha256': source_sha,
                'returncode': result.returncode, 'error_tail': result.stderr.splitlines()[-4:]}
    observed = json.loads(result.stdout)
    if not observed['origins'] or any(files.get(name) != sha for name, sha in observed['origins'].items()):
        raise ValueError('loaded source was not in the exact inventory')
    return {**observed, 'source_inventory_sha256': source_sha, 'source_files': len(files),
            'python_version': sys.version.split()[0], 'python_executable': str(Path(sys.executable).resolve()),
            'cpu_site_override': str(site) if site is not None else None, 'execution_authorized': False,
            'private_data_read': False, 'model_or_host_readiness_proven': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--manifest', type=Path, help='Public frozen package; defaults to current source inventory')
    parser.add_argument('--site', type=Path, help='Existing explicit CPU dependency directory for the target Python')
    args = parser.parse_args()
    if args.site:
        if not args.site.is_absolute() or args.site.resolve() != args.site or not args.site.is_dir():
            parser.error('existing canonical absolute CPU site required')
        sys.path.append(str(args.site))  # -S: no .pth/site hooks; never installs packages.
    sys.path.insert(0, str(ROOT))
    from tools.build_lora_development_package import source_manifest
    files = json.loads(args.manifest.read_text())['source_files'] if args.manifest else source_manifest(args.root)
    report = probe_source(args.root, files, site=args.site)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if report['status'] == 'passed' else 1)
