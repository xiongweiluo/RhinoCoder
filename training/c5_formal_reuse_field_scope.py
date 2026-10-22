"""New formal Mac read-only grant/source/environment guard; no private task I/O."""
import importlib.util
import json
import os
import sys
from pathlib import Path
from plugin.rhino_listener.c5_formal_reuse_scope import MAC_SOURCE,MAC_STATE,SPEC_FILE,FREEZE_FILE,authority,file_sha
from plugin.rhino_listener.c5_research_native import digest,require
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_formal_reuse_source_guard import SourceGuard

ROOT=Path(__file__).resolve().parents[1]
def public(path):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path and path.is_file() and 0<path.stat().st_size<=2097152,
        'formal_reuse_public_path')
    from plugin.rhino_listener.c5_reuse_field_scope import strict as strict_json
    return strict_json(path.read_bytes())

def scope(*,check_time=True):
    spec,freeze=public(ROOT/SPEC_FILE),public(ROOT/FREEZE_FILE)
    approval=read_json(MAC_STATE,'owner-approval.json');authority(spec,freeze,approval,check_time=check_time)
    require(ROOT==MAC_SOURCE and file_sha(ROOT/SPEC_FILE)==freeze['spec_file_sha256'],
        'formal_reuse_actual_mac_source')
    from plugin.rhino_listener.c5_followup_profile import MAC_CACHE
    require(Path(sys.executable).resolve()==Path('/opt/anaconda3/bin/python3.13')
        and sys.version==freeze['mac_environment']['python'] and sys.flags.isolated==1
        and sys.dont_write_bytecode is True and sys.pycache_prefix==MAC_CACHE
        and not os.path.lexists(MAC_CACHE),'formal_reuse_actual_mac_interpreter_and_no_cache')
    project=SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'],
        project_prefixes=('agent','training','tools','plugin','data_pipeline'))
    from plugin.rhino_listener.c5_formal_reuse_origins import origin_path
    def guard():
        project()
        require(file_sha(ROOT/SPEC_FILE)==freeze['spec_file_sha256']
            and digest(public(ROOT/FREEZE_FILE))==digest(freeze)
            and read_json(MAC_STATE,'owner-approval.json')==approval,'formal_reuse_material_drift')
        for files in (freeze['rhino_environment_files'],freeze['mac_environment']['file_sha256']):
            require(all(file_sha(n)==h for n,h in files.items()),'formal_reuse_readable_environment_drift')
        for m in tuple(sys.modules.values()):
            path=origin_path(m,sys.modules,require)
            if path is None:continue
            if path.is_relative_to(ROOT):
                require(path.relative_to(ROOT).as_posix() in freeze['source_files'],'formal_reuse_unregistered_project_origin')
            else:
                require(str(path) in freeze['mac_environment']['file_sha256']
                    and file_sha(path)==freeze['mac_environment']['file_sha256'][str(path)],'formal_reuse_foreign_loaded_origin')
        require(all(file_sha(ROOT/n)==h for n,h in freeze['fixed_public_files'].items()),'formal_reuse_public_configuration_drift')
        return freeze['source_inventory_sha256']
    guard();return spec,freeze,approval,guard
