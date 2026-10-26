"""Lazy fixed-weight development loader; no execution on import.

Only a newly qualified child, after exact owner admission, calls load().
Retains historical inference settings without invoking historical entries.
"""
import contextlib
import hashlib
import os
from pathlib import Path
import sys
import subprocess

from plugin.rhino_listener.c5_research_native import digest, require
from tools.audit_lora_development_environment import inventory, sha, SITE

POLICY = {'seed': 20260928, 'tf32': True, 'quantization': 'nf4_double_quant_bfloat16',
    'prepare_base': 'prepare_model_for_kbit_training_no_checkpoint_hooks',
    'base_route': 'same_PEFT_model_disable_adapter', 'lora_trainable': False,
    'local_files_only': True, 'trust_remote_code': False, 'device': 0,
    'parse_repair': False, 'training': False}


def preflight(package):
    row = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version,uuid',
        '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    hardware = package['gpu_hardware']
    require([part.strip() for part in row.split(',')] == [hardware['name'], str(hardware['memory_mib']),
        hardware['driver_version'], hardware['uuid']], 'GPU hardware identity differs')
    report, files = inventory()
    require(digest(report) == package['endpoints']['gpu']['environment_sha256'], 'GPU environment bytes differ')
    assets = package['assets']
    for prefix, names in [(assets['snapshot_dir'], assets['base_files']),
                          (assets['adapter_root'], assets['adapter_files'])]:
        for name, expected in names.items():
            path = Path(prefix) / name
            require(path.resolve() == path and sha(path) == expected, 'fixed model bytes differ')
            files[str(path)] = expected
    # Byte verification once, then stable dev/inode/mtime/ctime/size continuity
    # between checkpoints; no claim of whole-machine runtime byte closure.
    def identity(path):
        s = Path(path).stat()
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    identities = {name: identity(name) for name in files}
    def check():
        require(all(identity(name) == value for name, value in identities.items()), 'verified asset metadata drift')
        for module in tuple(sys.modules.values()):
            origin = getattr(module, '__file__', None)
            if not origin or 'site-packages' not in Path(origin).parts: continue
            path = Path(origin)
            if path.suffix == '.pyc':
                import importlib.util
                path = Path(importlib.util.source_from_cache(str(path)))
            require(str(path) in files and path.resolve() == path, 'unregistered loaded package')
    return check


def load(root, package, guard):
    require(package['loader_policy'] == POLICY, 'fixed common inference policy required')
    check = preflight(package)
    os.environ.update({'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false'})
    if str(SITE) not in sys.path: sys.path.append(str(SITE))
    guard()
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        from peft import PeftModel, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
        from training.c5_execution import generation, load_config, load_pinned_tokenizer
        check(); guard()
        require(torch.cuda.is_available() and torch.cuda.is_bf16_supported()
                and torch.cuda.mem_get_info()[0] >= 16 * 1024**3, 'approved GPU capacity unavailable')
        snapshot, adapter = Path(package['assets']['snapshot_dir']), Path(package['assets']['adapter_root'])
        tokenizer = load_pinned_tokenizer(snapshot, config=load_config(root / 'eval/c5/c5-engineering-config.json'))
        torch.manual_seed(20260928); torch.cuda.manual_seed_all(20260928)
        torch.backends.cuda.matmul.allow_tf32 = True
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True,
                                  bnb_4bit_compute_dtype=torch.bfloat16)
        base = AutoModelForCausalLM.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False,
            quantization_config=quant, dtype=torch.bfloat16, device_map={'': 0})
        base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=False)
        base.config.use_cache = False
        guard(); check()
        model = PeftModel.from_pretrained(base, adapter, local_files_only=True, is_trainable=False)
        model.eval()
        torch.cuda.reset_peak_memory_stats()
        guard(); check()
    def current(): check(); guard()
    def generate(prompt, stage):
        current()
        with contextlib.redirect_stdout(sys.stderr): value = generation(model, tokenizer, prompt, stage)
        # The peer durably stores this raw return before its post-generation
        # guard. A deadline/source error must not discard an available output.
        return value
    def route(name):
        require(name in {'base', 'current_lora'}, 'fixed route required')
        return model.disable_adapter() if name == 'base' else contextlib.nullcontext()
    return tokenizer, generate, route, current
