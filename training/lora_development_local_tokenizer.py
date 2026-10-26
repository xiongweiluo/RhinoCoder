"""CPU-only pinned tokenizer for independent Mac raw-output reparse.

Actual backend imports are blocked; no weights, GPU, downloads or private data.
The prepared loaded Python/package origins are bound separately from Rhino.
"""
import hashlib
import os
from pathlib import Path
import sys

from plugin.rhino_listener.c5_research_native import digest, require

SITE = '/opt/anaconda3/lib/python3.13/site-packages'
BLOCKED = {'torch', 'tensorflow', 'jax', 'peft', 'bitsandbytes'}


def load_tokenizer(assets):
    require(all(sys.modules.get(name) is None for name in BLOCKED), 'model backend already imported in CPU audit')
    for name in BLOCKED: sys.modules[name] = None
    os.environ.update({'USE_TORCH': '0', 'USE_TF': '0', 'USE_FLAX': '0', 'HF_HUB_OFFLINE': '1',
        'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'TOKENIZERS_PARALLELISM': 'false'})
    if SITE not in sys.path: sys.path.append(SITE)
    root = Path(assets['local_tokenizer_dir'])
    for name, expected in assets['tokenizer_files'].items():
        require((root / name).is_file() and hashlib.sha256((root / name).read_bytes()).hexdigest() == expected,
                'fixed local tokenizer asset differs')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(root, local_files_only=True, trust_remote_code=False)
    if tokenizer.pad_token_id is None: tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = 'right'
    return tokenizer


def observed_environment():
    files = {}
    for module in tuple(sys.modules.values()):
        origin = getattr(module, '__file__', None)
        if not origin or 'site-packages' not in Path(origin).parts: continue
        path = Path(origin)
        if path.suffix == '.pyc':
            import importlib.util
            path = Path(importlib.util.source_from_cache(str(path)))
        require(path.is_absolute() and path.resolve() == path and str(path).startswith(SITE + '/'), 'foreign CPU dependency')
        files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    executable = Path(sys.executable).resolve()
    return {'python': sys.version, 'python_path': str(executable),
        'python_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(), 'loaded_package_files': files,
        'model_backends_imported': False, 'external_dynamic_libraries_byte_closed': False}


def verify_environment(expected):
    observed = observed_environment()
    require(all(observed[k] == expected[k] for k in expected if k != 'loaded_package_files'), 'CPU interpreter differs')
    require(all(expected['loaded_package_files'].get(k) == v for k, v in observed['loaded_package_files'].items()),
            'unregistered loaded CPU dependency')
    for name, sha in expected['loaded_package_files'].items():
        require(hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, 'CPU dependency changed')
    require(all(sys.modules.get(name) is None for name in BLOCKED), 'model backend imported in CPU audit')
    return digest(expected)
