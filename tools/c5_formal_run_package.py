#!/usr/bin/env python3
"""One private execution command; read-only status/summary share its package."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('run','status','summary'))
    args=parser.parse_args()
    try:
        if args.mode=='run':
            from training.c5_formal_run_package_entry import run_package
            value=run_package()
        else:
            from training.c5_formal_reuse_control import control_scope
            from training.c5_formal_reuse_admission import open_formal_campaign
            from training.c5_formal_run_package import public_status
            from plugin.rhino_listener.c5_formal_reuse_scope import attempt_state
            from plugin.rhino_listener.c5_research_channel import read_json
            from plugin.rhino_listener.c5_formal_reuse_scope import SPEC_FILE,FREEZE_FILE,MAC_STATE
            from plugin.rhino_listener.c5_research_native import digest
            if not (MAC_STATE/'owner-approval.json').exists():
                spec=json.loads((ROOT/SPEC_FILE).read_bytes());freeze=json.loads((ROOT/FREEZE_FILE).read_bytes())
                value={'status':'UNAPPROVED_PACKAGE' if freeze['execution_ready'] else 'DISABLED_PREPARATION',
                    'study_id':spec['study_id'],'package_id':spec['instance_id'],
                    'spec_sha256':digest(spec),'runtime_sha256':digest(freeze),
                    'frozen_prior_attempts':spec.get('run_package',{}).get('timing_migration',{}).get('prior_attempts_consumed'),
                    'formal_execution_authority':False,'private_content_included':False}
                print(json.dumps(value,sort_keys=True));return 0
            spec,freeze,_=control_scope(ROOT)
            grant=read_json(MAC_STATE,'owner-approval.json')
            campaign=open_formal_campaign(spec,freeze,grant,freeze['history'])
            try:
                state=attempt_state('mac',max(1,campaign.observation()['attempts']))
                value=read_json(state,'owner-public-audit-summary.json') if args.mode=='summary' \
                    and (state/'owner-public-audit-summary.json').exists() else public_status(campaign,state)
            finally:campaign.log.close()
        print(json.dumps(value,ensure_ascii=False,sort_keys=True));return 0
    except BaseException as error:
        print(json.dumps({'status':'PAUSED','error_type':type(error).__name__,
                          'private_content_included':False}),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
