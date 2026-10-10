#!/usr/bin/env python3
"""Owner-terminal-only new formal entry. No agent private-data invocation.

New exact formal approval first. Verify host/model readiness with zero private
rows, then owner enters age package/key paths without echo; permanent formal
started is written BEFORE decryption. No retry/reconnect/reseal/training.
"""
import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_formal20_scope_v2 import MAC_STATE,STUDY_ID
from plugin.rhino_listener.c5_research_channel import read_json,publish_json
from plugin.rhino_listener.c5_research_native import require,digest
from training.c5_formal20_field_scope_v2 import scope,public
from training.c5_formal20_budget_v2 import FormalBudgetV2
from training.c5_formal20_adapters_v2 import NativeAdapterV2,ModelAdapterV2
from training.c5_formal20_runner import FormalRunner
from training.c5_formal20_joint_audit_v2 import audit_run_v2,public_summary
from tools.c5_formal20_owner_run import sealed_loader
from tools.c5_formal20_public_preflight import preflight as public_preflight
from training.c5_modelbridge_runtime import file_sha


def commitment(spec):
    path=ROOT/'eval/c5/rhino-formal20-public-commitment-v1.json'
    value=public(path);checked=public_preflight(path)
    require(checked['public_commitment_sha256']==spec['public_commitment_sha256']
        and value['family_merkle_root_sha256']==spec['family_merkle_root_sha256']
        and value['slot_order_sha256']==spec['slot_order_sha256'],'same registered public commitment required')
    return value


def verify_private_metadata(sealed,identity,value,freeze):
    """Owner-only metadata/cipher hash checks, no key/plaintext/decryption read."""
    from tools.c5_rhino_formal20_owner_exclusion import _worktrees,_require_owner_private_path
    from plugin.rhino_listener.c5_research_channel import private_directory
    roots=_worktrees(repository_root=Path(freeze['repository_root_for_private_boundary']))
    for path in (sealed,identity):
        _require_owner_private_path(path,roots)
        require(path.is_absolute() and path.resolve()==path and path.is_file()
            and path.stat().st_uid==os.geteuid() and (path.stat().st_mode & 0o777)==0o600,
            'owner private input metadata invalid')
        fd=private_directory(path.parent);os.close(fd)
    require(sealed!=identity and sealed.stat().st_size==value['encrypted_artifact']['bytes']
        and file_sha(sealed)==value['encrypted_artifact']['sha256'], 'owner cipher commitment differs')
    require(file_sha(Path(freeze['decryption_executable']))==freeze['decryption_executable_sha256'],
        'owner frozen age executable drift')


def run_interactive():
    require(sys.stdin.isatty() and sys.stderr.isatty(),'owner private terminal required before any field operation')
    spec,freeze,approval,guard=scope()
    require(time.time()<spec['latest_owner_start_epoch'],
        'full formal window plus zero-stage startup margin no longer available; no admission')
    value=commitment(spec)
    budget=FormalBudgetV2(freeze['resource_boundary'])
    publish_json(MAC_STATE,'formal20.zero-started.claim.json',{'study_id':STUDY_ID,
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    native=NativeAdapterV2(MAC_STATE,spec,freeze,guard=guard)
    model=ModelAdapterV2(MAC_STATE,spec,freeze,guard=guard)
    try:
        native.arm()
        print('C5_FORMAL20_WAIT_APPROVED_RHINO_ARM_ZERO_PRIVATE_ROWS',flush=True)
        native.wait_zero_ready();budget.check()
        model.start_zero();budget.check()
        publish_json(MAC_STATE,'formal20.zero-readiness.json',{'study_id':STUDY_ID,
            'runtime_freeze_sha256':digest(freeze),
            'host_ready_sha256':digest(read_json(MAC_STATE,'host-continuity-ready.json')),
            'model_ready_sha256':digest(read_json(MAC_STATE,'worker-startup-ready.json')),
            'private_rows_read':0,'formal_started_present':False})
        sealed=Path(getpass.getpass('已封存age文件绝对路径（不回显）：').strip())
        identity=Path(getpass.getpass('age identity绝对路径（不回显）：').strip())
        verify_private_metadata(sealed,identity,value,freeze)
        guard();budget.check()
        runner=FormalRunner(state=MAC_STATE,spec=spec,freeze=freeze,approval=approval,model=model,native=native,
            source_guard=guard,budget_guard=budget.check)
        result=runner.run(sealed_loader(sealed,identity,value,freeze,state=MAC_STATE,
            repository_root=Path(freeze['repository_root_for_private_boundary'])))
        return {k:result[k] for k in ('study_id','status','slots_attempted','route_slots_required','error_type','c5_6_gate_claim')}
    finally:
        # Also stop the known zero-generation worker if owner decryption or
        # validation failed AFTER started but BEFORE hash bootstrap. This is
        # not a claim that Mac consumption never happened.
        if model.process is not None and not model.bootstrapped \
                and not (MAC_STATE/'worker-process-exit.json').exists():
            try:model.stop_zero()
            except BaseException:pass
        if not (MAC_STATE/'formal20.hub-started.claim.json').exists():
            try:native.finish()
            except BaseException:pass
        budget.settle(MAC_STATE,'formal_mac_driver_finished')


def audit_owner(external_seal_sha):
    require(sys.stdin.isatty() and sys.stderr.isatty(),'owner private audit terminal required')
    spec,freeze,_,guard=scope(check_time=False);commitment(spec)
    from training.c5_execution import load_pinned_tokenizer,load_config
    directory=Path(freeze['tokenizer_dir'])
    require(all(file_sha(directory/n)==sha for n,sha in freeze['tokenizer_file_sha256'].items()),
        'owner audit tokenizer drift')
    tokenizer=load_pinned_tokenizer(directory,config=load_config());guard()
    private=audit_run_v2(MAC_STATE,read_json(MAC_STATE,'private-cases.json'),spec,freeze,tokenizer,
        source_guard=guard,external_seal_sha=external_seal_sha)
    publish_json(MAC_STATE,'independent-audit.json',private)
    summary=public_summary(private,spec,freeze,external_seal_sha)
    publish_json(MAC_STATE,'owner-public-audit-summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('run','audit'))
    parser.add_argument('--external-host-seal-sha256')
    args=parser.parse_args()
    try:
        if args.mode=='audit':
            require(args.external_host_seal_sha256 is not None,'actual independently captured Rhino receipt required')
            result=audit_owner(args.external_host_seal_sha256)
        else:result=run_interactive()
        print(json.dumps(result,sort_keys=True));return 0
    except BaseException as exc:
        # No traceback, private paths, task strings or age stderr disclosure.
        print(json.dumps({'status':'formal_owner_entry_stopped_no_retry','error_type':type(exc).__name__,
            'private_content_included':False}),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
