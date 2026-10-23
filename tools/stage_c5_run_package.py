#!/usr/bin/env python3
"""Stage only the unapproved public package, never old sources or state."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.prepare_c5_run_package import assemble,encoded,SPEC,RUNTIME
from training.c5_formal_reuse_deployment import stage_local
from plugin.rhino_listener.c5_followup_profile import MAC_FLAGS


def payload():
    docs=assemble();spec,freeze=docs[SPEC],docs[RUNTIME]
    files={n:encoded(docs[n]) if n in docs else (ROOT/n).read_bytes() for n in freeze['source_files']}
    files[RUNTIME]=encoded(freeze)
    return spec,freeze,files


def stage(endpoint):
    spec,freeze,files=payload();layout=spec['run_package']['layout']
    if endpoint=='gpu':
        import tools.stage_c5_formal_reuse_source as staging
        staging.payload=lambda:(spec,freeze,files)
        staging.REMOTE_SOURCE=Path(layout['gpu_source_root'])
        staging.REMOTE_STATE=Path(layout['gpu_state_root'])
        return staging.stage_gpu()
    root=Path(layout['mac_source_root'])
    stage_local(root,files,state_root=Path(layout['mac_state_root']),
                archive_root=root.parent/'run-package-unapproved-source-archive')
    script='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'+\
        'from training.c5_formal_reuse_deployment import verify;'+\
        'from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE;'+\
        'r=Path(sys.argv[1]);print(json.dumps(verify(r,json.loads((r/SPEC_FILE).read_bytes()),json.loads((r/FREEZE_FILE).read_bytes()))))'
    result=subprocess.run(['/opt/anaconda3/bin/python3.13',*MAC_FLAGS,'-c',script,str(root)],
                          capture_output=True,text=True,check=True,timeout=60)
    return json.loads(result.stdout)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('endpoint',choices=('mac','gpu'))
    print(json.dumps(stage(p.parse_args().endpoint),sort_keys=True))
