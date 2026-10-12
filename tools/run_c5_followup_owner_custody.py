#!/usr/bin/env python3
"""Owner-operated readiness/final custody. No model, Rhino, score or signal.

Must be run by the owner in their private interactive terminal after exact
approval. The agent/producer cannot execute this on the owner's behalf or
invent a terminal receipt. Statements are bound, not cryptographic origin.
"""
import argparse
import json
import os
import stat
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
LOG_NAME='controller-output.log'
BYTE_RECEIPTS=Path('/private/tmp/rhinocoder-c5-reuse-c-actual-deployment-byte-receipts.json')
CONFIRM='确认并保管'


def readiness_record(binding,host,worker):
    from training.c5_reuse_evidence import require,sha,is_sha,exact
    from training.c5_followup_ssh import validate_ready
    exact(host,('study_id','runtime_sha256','host_baseline_head_sha256','generation_stages','full_byte_closure_proven'))
    require(host['study_id']==binding['study_id'] and host['runtime_sha256']==binding['runtime_sha256']
        and is_sha(host['host_baseline_head_sha256']) and type(host['generation_stages']) is int and host['generation_stages']==0
        and host['full_byte_closure_proven'] is False,'reuse_owner_live_host_readiness')
    validate_ready(binding,worker)
    return {k:binding[k] for k in ('study_id','instance_id','spec_sha256','runtime_sha256')}|{
        'host_baseline_head_sha256':host['host_baseline_head_sha256'],'worker_readiness_sha256':sha(worker),
        'actor':'repository_owner','captured_after_host_baseline':True,'approved_generation_start':True}


def byte_receipts(value,binding,runtime):
    from training.c5_reuse_evidence import require,sha
    require(set(value)=={'mac','gpu'} and all(r['spec_sha256']==binding['spec_sha256']
        and r['runtime_sha256']==binding['runtime_sha256'] and r['source_inventory_sha256']==sha(runtime['source_files'])
        and r['actual_source_bytes_verified'] is r['actual_installed_asset_bytes_verified'] is True
        for r in value.values()),'reuse_owner_actual_byte_receipts')
    return value


def final_record(binding,owner,completed,terminal,heads,export):
    from training.c5_reuse_evidence import require,sha,exact,is_sha
    exact(completed,('native_head_sha256','worker_final_head_sha256','whole_field_pass','external_final_capture_required'))
    exact(heads,('controller_head_sha256','native_head_sha256','mac_lifecycle_head_sha256'))
    require(all(is_sha(v) for v in heads.values()),'reuse_owner_final_anchors')
    from training.c5_reuse_field_scope import common_scope
    require(common_scope(export['binding'])==common_scope(binding),'reuse_owner_export_identity')
    require(completed['whole_field_pass'] is False and completed['external_final_capture_required'] is True
        and completed['native_head_sha256']==heads['native_head_sha256']
        and completed['worker_final_head_sha256']==export['worker_head'],'reuse_owner_complete_controller_output')
    exact(terminal,('study_id','seal_sha256','journal_head_sha256','record_count','blocked','execution_authority'))
    require(terminal['study_id']==binding['study_id'] and is_sha(terminal['seal_sha256'])
        and is_sha(terminal['journal_head_sha256']) and type(terminal['record_count']) is int
        and 0<terminal['record_count']<=4096 and terminal['blocked'] is False and terminal['execution_authority'] is False,
        'reuse_owner_actual_external_host_terminal')
    require(owner['actor']=='repository_owner' and owner['captured_after_host_baseline'] is True
        and owner['approved_generation_start'] is True and is_sha(owner['host_baseline_head_sha256'])
        and is_sha(owner['worker_readiness_sha256']),'reuse_owner_readiness_statement')
    require(all(owner[k]==binding[k] for k in ('study_id','instance_id','spec_sha256','runtime_sha256')),
            'reuse_owner_readiness_identity')
    return {'actor':'repository_owner',**{k:binding[k] for k in ('study_id','instance_id','spec_sha256','runtime_sha256')},
        **heads,'gpu_export_sha256':sha(export),'host_seal_sha256':terminal['seal_sha256'],
        'owner_readiness':owner,'captured_outside_producer':True,'private_custody_confirmed':True}


def last_head(root,cap,read,scope):
    from training.c5_reuse_evidence import strict,require,sha
    names=set(p.name for p in root.iterdir())
    require(0<len(names)<=cap and names=={'raw-%04d.json'%i for i in range(len(names))},'reuse_owner_raw_anchor_population')
    row=strict(read(root/('raw-%04d.json'%(len(names)-1)),private=True))
    require(row['seq']==len(names)-1 and row['scope_sha256']==sha(scope)
        and row['record_sha256']==sha({k:v for k,v in row.items() if k!='record_sha256'}),'reuse_owner_raw_anchor')
    return row['record_sha256']


def live_line(path,prefix,read,guard,*,seconds=18000,clock=time.monotonic,sleep=time.sleep):
    from training.c5_reuse_evidence import require,strict
    deadline=clock()+seconds;guard()
    while True:
        require(clock()<deadline,'reuse_owner_log_wait_expired')
        if os.path.lexists(path):
            info=path.lstat()
            require(path.resolve()==path and stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
                and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600,'reuse_owner_private_controller_log')
            if info.st_size==0:sleep(.1);continue
            try:raw=read(path,private=True)
            except ValueError as exc:
                if str(exc)!='reuse_runtime_file_race':raise
                sleep(.1);continue  # Read-only observation; no field request is resent.
            lines=raw.splitlines(keepends=True)
            matches=[line[len(prefix):] for line in lines if line.startswith(prefix) and line.endswith(b'\n')]
            require(len(matches)<=1,'reuse_owner_duplicate_controller_output')
            if matches:guard();return strict(matches[0],limit=8192)
        sleep(.1)


def confirm(value):
    from training.c5_reuse_evidence import require,canonical
    print(canonical(value).decode(),flush=True)
    require(sys.stdin.isatty() and input('本人核对实际输出并私下保管后，输入“'+CONFIRM+'”：').strip()==CONFIRM,
            'reuse_owner_interactive_confirmation_required')


def main():
    parser=argparse.ArgumentParser(description=__doc__);m=parser.add_mutually_exclusive_group(required=True)
    m.add_argument('--ready',action='store_true');m.add_argument('--final',action='store_true');args=parser.parse_args()
    if not sys.stdin.isatty():raise ValueError('owner private interactive terminal required; producer cannot sign custody')
    from plugin.rhino_listener.c5_followup_mac_scope import mac_scope
    from plugin.rhino_listener.c5_followup_runtime_scope import MAC_PARENT,INSTANCE,read_bytes
    from plugin.rhino_listener.c5_research_channel import publish_json,read_json,private_directory
    from training.c5_reuse_evidence import strict,require,canonical
    spec,runtime,binding,plan,guard=mac_scope(ROOT,cleanup_only=args.final,private_prefixes=('__main__',))
    state=Path(binding['paths']['state_root']);custody=MAC_PARENT/(INSTANCE+'-external-custody');os.umask(0o077)
    if args.ready:
        require(not os.path.lexists(custody),'reuse_owner_custody_no_replace');custody.mkdir(mode=0o700)
        receipts=byte_receipts(strict(read_bytes(BYTE_RECEIPTS,private=True)),binding,runtime)
        publish_json(custody,'actual-deployment-byte-receipts.json',receipts)
        print('C5_REUSE_OWNER_CUSTODY_ARMED_D; 等待实际host/worker输出，不要关闭此终端。',flush=True)
        value=live_line(state/LOG_NAME,b'C5_REUSE_EXTERNAL_READINESS_REQUIRED ',read_bytes,guard)
        require(set(value)=={'host','worker'} and value['host']==read_json(state,'host-continuity-ready.json'),
                'reuse_owner_current_host_output')
        owner=readiness_record(binding,value['host'],value['worker']);confirm(owner);guard()
        publish_json(custody,'owner-readiness.json',owner)
        print('C5_REUSE_OWNER_READY_CAPTURED; 完成后使用 --final 保管终止锚。',flush=True)
    else:
        fd=private_directory(custody);os.close(fd)
        require(not os.path.lexists(custody/'owner-final-custody.json'),'reuse_owner_final_no_replace')
        completed=live_line(state/LOG_NAME,b'C5_REUSE_CONTROLLER_EXTERNAL_FINAL_REQUIRED ',read_bytes,guard,seconds=120)
        raw=input('粘贴Rhino终端实际 C5_HOST_CONTINUITY_EXTERNAL_RECEIPT 完整一行：').strip()
        prefix='C5_HOST_CONTINUITY_EXTERNAL_RECEIPT ';require(raw.startswith(prefix),'reuse_owner_external_terminal_prefix')
        terminal=strict(raw[len(prefix):].encode(),limit=8192)
        require(terminal==read_json(state,'host-continuity-terminal-receipt.json'),'reuse_owner_external_terminal_join')
        raw_export=read_bytes(state/'gpu-public-eight-raw-export.json',limit=64*1024*1024,private=True)
        export=strict(raw_export,limit=64*1024*1024);require(raw_export==canonical(export)+b'\n','reuse_owner_export_serialization')
        heads={key:last_head(state/role,cap,read_bytes,binding) for key,role,cap in (
            ('controller_head_sha256','controller',4096),('native_head_sha256','native-controller',128),
            ('mac_lifecycle_head_sha256','controller-lifecycle',32))}
        record=final_record(binding,read_json(custody,'owner-readiness.json'),completed,terminal,heads,export)
        confirm(record);guard(cleanup_only=True);publish_json(custody,'owner-final-custody.json',record)
        print('C5_REUSE_OWNER_FINAL_CAPTURED; 原始联合审计尚未完成，不能由此宣称PASS。',flush=True)


if __name__=='__main__':main()
