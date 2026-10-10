"""New fixed Mac dev context. Retired modelbridge entries remain untouched."""
import sys
from pathlib import Path

from plugin.rhino_listener.c5_hostassurance_development_scope_b import (
    ID, STATE, SOCKET, SPEC, FREEZE, PIN, PIN_SHA, scope as deployed_scope, public as read_public,
)
from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_formal20_field_scope import external_origins
from training.c5_modelbridge_runtime import file_sha

ROOT = Path(__file__).resolve().parents[1]


def public(path):
    require(path.is_relative_to(ROOT), 'fixed project public file only')
    return read_public(ROOT,path.relative_to(ROOT).as_posix())


def mac_origins():
    return external_origins()


def scope(*, check_time=True):
    spec,freeze,approval,binding,source = deployed_scope(ROOT,
        private_prefixes=('plugin','training','tools','agent','data_pipeline'),check_time=check_time)
    def guard():
        source()
        actual,frozen = mac_origins(),freeze['mac_environment']
        require(actual['python'] == frozen['python'] and digest(frozen['file_sha256']) == frozen['inventory_sha256']
            and all(frozen['file_sha256'].get(n) == sha for n,sha in actual['file_sha256'].items())
            and all(file_sha(Path(n)) == sha for n,sha in frozen['file_sha256'].items()),
            'actual new Mac loaded source/environment differs')
        return freeze['source_inventory_sha256']
    guard()
    return spec,freeze,approval,guard
