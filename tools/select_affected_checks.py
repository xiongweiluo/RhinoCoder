#!/usr/bin/env python3
"""Conservative impact selection. Unknown paths and CI changes run everything."""
import argparse
import json
import os
import re
import subprocess


def select(paths, *, force_full=False):
    full=force_full or not paths
    c5=False;ui=False;release=False
    for path in paths:
        if path.startswith(('.github/', 'requirements', 'pyproject', 'pytest.ini', 'tools/select_affected_checks.py')):
            full=True
        elif path.startswith(('agent/ui/',)):
            ui=True
        elif path.startswith(('docs/',)) or path.endswith('.md'):
            release=True
        elif path.startswith(('eval/c5/', 'eval/test_c5_', 'training/c5_',
                              'plugin/rhino_listener/c5_', 'tools/c5_', 'tools/check_c5_',
                              'tools/prepare_c5_', 'tools/register_c5_', 'tools/run_c5_', 'tools/stage_c5_')):
            c5=True
        else:
            full=True
    return {'python_scope':'full' if full else 'c5' if c5 else 'none',
            'ui':full or ui,'release':full or release,'package':full or c5,
            'selection_basis':'unknown_is_full; c5_contains_all_c5_regressions; no_duplicate_linux_gate'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base');p.add_argument('--head');p.add_argument('--full',action='store_true')
    a=p.parse_args();paths=[]
    if not a.full:
        if not all(v and re.fullmatch('[a-f0-9]{40}',v) for v in (a.base,a.head)):
            a.full=True
        else:
            value=subprocess.run(['git','diff','--name-only',a.base,a.head],capture_output=True,text=True,check=True)
            paths=value.stdout.splitlines()
    value=select(paths,force_full=a.full);print(json.dumps(value,sort_keys=True))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:
            for key,item in value.items():
                if type(item) in (str,bool):f.write(key+'='+str(item).lower()+'\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
