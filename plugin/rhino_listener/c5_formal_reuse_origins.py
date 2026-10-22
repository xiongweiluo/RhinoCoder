"""Exact typed PyTorch virtual origins from the accepted read-only review."""
import importlib.util
from pathlib import Path

def origin_path(module, modules, require):
    """Bind the two real PyTorch virtual namespaces to their defining source.

    These are exact typed singleton objects, not arbitrary relative origins.
    The defining Python and every loaded native module remain byte-checked.
    """
    name = vars(module).get('__name__')
    rules = {'torch.ops': ('torch._ops', '_Ops', '_ops.py', 'ops'), 'torch.classes': ('torch._classes', '_Classes', '_classes.py', 'classes')}
    if name in rules:
        owner_name, cls, sentinel, attribute = rules[name]
        owner = modules.get(owner_name)
        torch = modules.get('torch')
        require(owner is not None and torch is not None and (modules.get(name) is module) and (type(module) is vars(owner).get(cls)) and (vars(torch).get(attribute) is module) and (getattr(module, '__file__', None) == sentinel), 'review_virtual_namespace_identity')
        origin = getattr(owner, '__file__', None)
    else:
        origin = getattr(module, '__file__', None)
    if not origin or str(origin).startswith('<'):
        return None
    p = Path(origin)
    if p.suffix == '.pyc':
        p = Path(importlib.util.source_from_cache(str(p)))
    require(p.is_absolute(), 'review_unresolved_loaded_origin')
    return p.resolve()
