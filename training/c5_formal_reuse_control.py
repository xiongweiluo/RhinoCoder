"""Cleanup authority does not depend on model assets, Torch or loader preflight.

The exact original grant, pinned control code, qualification and shared stop
ledger remain required even after a lease or generation budget expires.
"""
import json
import sys
from pathlib import Path
from plugin.rhino_listener.c5_formal_reuse_scope import (
    SPEC_FILE, FREEZE_FILE, REMOTE_SOURCE, REMOTE_STATE, MAC_SOURCE,MAC_STATE,authority, file_sha)
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import digest, require

CONTROL_FILES = (
    'tools/c5_formal_reuse_control.py', 'training/c5_formal_reuse_control.py',
    'training/c5_formal_reuse_supervisor.py', 'training/c5_reuse_process_identity.py',
    'training/c5_reuse_stop.py', 'training/c5_recovery_stop.py', 'training/c5_recovery_storage.py',
    'training/c5_reuse_evidence.py', 'plugin/rhino_listener/c5_formal_reuse_scope.py',
    'plugin/rhino_listener/c5_run_package_policy.py', 'plugin/rhino_listener/c5_research_native.py',
    'plugin/rhino_listener/c5_research_channel.py',
)


def control_scope(root):
    root = Path(root)
    require((root==REMOTE_SOURCE and sys.platform=='linux') or (root==MAC_SOURCE and sys.platform=='darwin'),
            'run_package_control_fixed_deployment')
    state=REMOTE_STATE if root==REMOTE_SOURCE else MAC_STATE
    spec = json.loads((root/SPEC_FILE).read_bytes())
    freeze = json.loads((root/FREEZE_FILE).read_bytes())
    grant = read_json(state, 'owner-approval.json')
    authority(spec, freeze, grant, check_time=False)
    original_pair = digest(spec), digest(freeze)
    def guard():
        require((digest(json.loads((root/SPEC_FILE).read_bytes())),
                 digest(json.loads((root/FREEZE_FILE).read_bytes()))) == original_pair
                and read_json(state, 'owner-approval.json') == grant,
                'run_package_control_grant_drift')
        require(all(name in freeze['control_source_files'] for name in CONTROL_FILES)
                and all(freeze['source_files'].get(name)==h and file_sha(root/name)==h
                        for name,h in freeze['control_source_files'].items()),
                'run_package_control_code_drift')
    guard()
    return spec, freeze, guard


def code_closure(root,entry,files):
    """Preparation-only AST closure. Never imports or executes a candidate."""
    import ast
    root=Path(root);pending=[entry];seen=set()
    def add(module):
        if module and module.split('.')[0] in ('plugin','training','tools','agent','data_pipeline'):
            for name in (module.replace('.','/')+'.py',module.replace('.','/')+'/__init__.py'):
                if name in files and name not in seen:pending.append(name)
    while pending:
        name=pending.pop()
        if name in seen:continue
        seen.add(name);parts=name[:-3].split('/')
        parent=parts[:-1]
        for node in ast.walk(ast.parse((root/name).read_text())):
            if isinstance(node,ast.Import):
                for item in node.names:add(item.name)
            if isinstance(node,ast.ImportFrom):
                base=('.'.join(parent[:len(parent)-node.level+1])+'.' if node.level else '')+(node.module or '')
                base=base.rstrip('.');add(base)
                for item in node.names:add(base+'.'+item.name)
    return {name:files[name] for name in sorted(seen)}
