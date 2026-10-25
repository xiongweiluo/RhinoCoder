"""Full fixed source/grant guard. Read-only until explicitly approved setup."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import time
from .c5_followup_runtime_scope import read_bytes
from .c5_reuse_field_scope import canonical,sha,strict,require,is_sha
from .c5_recovery_profile import SPEC,RUNTIME,PLAN,HISTORY,STUDY,INSTANCE,RECOVERY_POLICY
from .c5_recovery_scope import paths,material,campaign_scope

class SourceGuard:
    def __init__(self,root,files,*,private_prefixes=()):
        self.root=Path(root);self.files=dict(files);self.expected=sha(files)
        self.prefixes=('training','plugin','tools','agent','data_pipeline','main','_client','schemas_geometry','schemas_transform','schemas_property','schemas_perception','rhino_client')+tuple(private_prefixes)
        require(self.root.is_absolute() and self.root.resolve()==self.root and 0<len(files)<=512,'recovery_source_root')
        for name,h in files.items():
            p=Path(name)
            require(not p.is_absolute() and '..' not in p.parts and str(p)==name and is_sha(h)
                and ((name.endswith('.py') and p.parts[0] in self.prefixes[:5])
                     or (p.parts[:2]==('eval','c5') and p.suffix=='.json')
                     or name in ('requirements.txt','requirements-training.txt')),'recovery_public_source_population')
    def __call__(self,*,cleanup_only=False):
        for n,h in self.files.items():
            require(hashlib.sha256(read_bytes(self.root/n,limit=16*1024*1024)).hexdigest()==h,'recovery_source_byte_drift')
        for name,module in tuple(sys.modules.items()):
            if name.split('.')[0] not in self.prefixes:continue
            origin=getattr(module,'__file__',None)
            if origin is None:
                roots=getattr(module,'__path__',())
                require(roots and all(Path(p).resolve().is_relative_to(self.root) for p in roots),'recovery_source_namespace')
                continue
            p=Path(origin)
            if p.suffix=='.pyc':p=Path(importlib.util.source_from_cache(str(p)))
            require(p.is_absolute() and p.resolve()==p and p.is_relative_to(self.root)
                and p.relative_to(self.root).as_posix() in self.files,'recovery_loaded_project_origin')
        return self.expected

def grant_for(scope,approval):
    expected={'actor':'repository_owner','approved':True,'protocol':RECOVERY_POLICY['protocol'],
        'scope_sha256':sha(scope),'spec_sha256':scope['spec_sha256'],
        'runtime_sha256':scope['runtime_sha256'],'policy_sha256':sha(RECOVERY_POLICY)}
    require(approval==expected,'recovery_new_exact_execution_grant_required')

def approved_entry(root,endpoint,attempt,*,now=time.time,private_prefixes=(),cleanup_only=False):
    root=Path(root);fixed=paths(endpoint,attempt)
    require(root==Path(fixed['source_root']) and root.resolve()==root,'recovery_fixed_entry_root')
    raws={n:read_bytes(root/n,limit=16*1024*1024) for n in (SPEC,RUNTIME,PLAN,HISTORY)}
    spec,runtime,plan,history=(strict(raws[n]) for n in (SPEC,RUNTIME,PLAN,HISTORY))
    binding=material(spec,runtime,endpoint=endpoint,attempt=attempt,now=now(),cleanup_only=cleanup_only)
    fixed=binding['paths']
    from .c5_recovery_plan import validate as validate_plan
    validate_plan(spec,runtime,plan,history)
    require(all(n in runtime['source_files'] for n in (SPEC,PLAN,HISTORY))
            and sha(plan['environment'])==runtime['environment_sha256']
            and sha(plan['model_assets'])==runtime['model_assets_sha256']
            and sha(plan['host_readable_files'])==runtime['host_readable_files_sha256']
            and sha(history)==binding['recovery']['scope']['history_sha256'],'recovery_complete_materials')
    state=Path(fixed['state_root']).parent
    approval_raw=read_bytes(state/'owner-approval.json',private=True)
    approval=strict(approval_raw);grant_for(binding['recovery']['scope'],approval)
    source=SourceGuard(root,runtime['source_files'],private_prefixes=private_prefixes)
    from .c5_recovery_admission import verify_history
    def guard(*,cleanup_only=cleanup_only):
        require(all(read_bytes(root/n,limit=16*1024*1024)==raw for n,raw in raws.items())
                and read_bytes(state/'owner-approval.json',private=True)==approval_raw,'recovery_approved_materials_changed')
        material(spec,runtime,endpoint=endpoint,attempt=attempt,now=now(),cleanup_only=cleanup_only)
        grant_for(binding['recovery']['scope'],approval)
        require(cleanup_only or not os.path.lexists(Path(fixed['state_root'])/'cancelled.json'),
                'recovery_attempt_launch_revoked')
        verify_history(binding,history)
        return source(cleanup_only=cleanup_only)
    guard();return spec,runtime,binding,plan,history,approval,guard
