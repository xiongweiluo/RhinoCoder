#!/usr/bin/env python3
"""Owner-only preload confirmation. No model, worker, signal or Rhino call."""
import argparse
from pathlib import Path
import sys
import secrets
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def final_record(binding,snap,receipt,completed,terminal,heads,export):
    from training.c5_reuse_evidence import exact,require,is_sha,sha
    from training.c5_recovery_confirmation import validate_receipt
    from training.c5_reuse_field_scope import common_scope
    validate_receipt(binding['recovery']['scope'],snap,receipt)
    exact(completed,('native_head_sha256','worker_final_head_sha256','whole_field_pass','external_final_capture_required'))
    exact(heads,('controller_head_sha256','native_head_sha256','mac_lifecycle_head_sha256'))
    require(all(is_sha(v) for v in heads.values()) and common_scope(export['binding'])==common_scope(binding)
        and completed['whole_field_pass'] is False and completed['external_final_capture_required'] is True
        and completed['native_head_sha256']==heads['native_head_sha256']
        and completed['worker_final_head_sha256']==export['worker_head'],'recovery_owner_complete_raw_heads')
    exact(terminal,('study_id','seal_sha256','journal_head_sha256','record_count','blocked','execution_authority'))
    require(terminal['study_id']==binding['study_id'] and is_sha(terminal['seal_sha256'])
        and is_sha(terminal['journal_head_sha256']) and type(terminal['record_count']) is int
        and 0<terminal['record_count']<=4096 and terminal['blocked'] is terminal['execution_authority'] is False,
        'recovery_owner_actual_host_terminal')
    return {'actor':'repository_owner',**{k:binding[k] for k in ('study_id','instance_id','spec_sha256','runtime_sha256')},
        **heads,'gpu_export_sha256':sha(export),'host_seal_sha256':terminal['seal_sha256'],
        'preload_snapshot':snap,'preload_receipt':receipt,'captured_outside_producer':True,'private_custody_confirmed':True}

def capture_final(binding,state,owner,guard):
    from training.c5_reuse_evidence import require,strict,sha,canonical
    from training.c5_recovery_storage import read_private,write_once
    from plugin.rhino_listener.c5_recovery_runtime_scope import read_bytes
    from tools.run_c5_followup_owner_custody import last_head
    from training.c5_reuse_field_journal import read_record
    from training.c5_recovery_confirmation import input_status
    require(sys.stdin.isatty(),'owner_private_interactive_terminal_required');guard(cleanup_only=True)
    # Missing completion/export fails before asking for a terminal receipt.
    heads={name:last_head(state/folder,cap,read_bytes,binding) for name,folder,cap in
        (('controller_head_sha256','controller',4096),('native_head_sha256','native-controller',128),
         ('mac_lifecycle_head_sha256','controller-lifecycle',32))}
    names=list((state/'native-controller').iterdir());last,_=read_record(state/'native-controller','raw-%04d.json'%(len(names)-1))
    require(last['kind']=='controller_completed_records','recovery_owner_normal_completion_required')
    export_raw=read_bytes(state/'gpu-public-eight-raw-export.json',limit=64*1024*1024,private=True)
    export=strict(export_raw,limit=64*1024*1024);require(export_raw==canonical(export)+b'\n','recovery_owner_export_serialization')
    completed={'native_head_sha256':heads['native_head_sha256'],'worker_final_head_sha256':export['worker_head'],
               'whole_field_pass':False,'external_final_capture_required':True}
    print(canonical({'binding':binding,'heads':heads,'gpu_export_sha256':sha(export),
                     'human_origin_cryptographically_proven':False}).decode())
    text=input('私下粘贴实际 Rhino C5_HOST_CONTINUITY_EXTERNAL_RECEIPT 完整一行：').strip()
    prefix='C5_HOST_CONTINUITY_EXTERNAL_RECEIPT ';require(text.startswith(prefix),'recovery_owner_actual_terminal_prefix')
    terminal=strict(text[len(prefix):].encode(),limit=8192)
    snap=strict(read_private(owner/('preload-snapshot-'+binding['runtime_sha256']+'.json')));receipt=strict(read_private(owner/('owner-preload-confirmation-'+binding['runtime_sha256']+'.json')))
    record=final_record(binding,snap,receipt,completed,terminal,heads,export)
    for _ in range(3):
        try:raw=input('核对实际终止回执和完整原始材料后，输入“确认并保管”：')
        except (EOFError,KeyboardInterrupt):print('最终保管已暂停；原始材料保留。');return
        status,hidden=input_status(raw)
        if status=='confirmed':
            guard(cleanup_only=True);write_once(owner,'owner-final-attempt-'+str(binding['recovery']['attempt'])+'.json',record)
            print('C5_RECOVERY_OWNER_FINAL_CUSTODY_RECORDED');return
        if status=='cancelled':print('最终保管已暂停；原始材料保留。');return
        print('确认未匹配，请手动键入；没有覆盖或退休原始材料。')
    print('最终保管已暂停；原始材料保留。')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--attempt',type=int,required=True,choices=(1,2,3));p.add_argument('--final',action='store_true');a=p.parse_args()
    from plugin.rhino_listener.c5_recovery_mac_scope import mac_scope
    s,r,b,plan,h,g,guard=mac_scope(ROOT,a.attempt,private_prefixes=('__main__',),cleanup_only=a.final)
    if a.final:
        local=Path(b['paths']['state_root']);capture_final(b,local,local.parent/'owner-custody',guard);return
    from training.c5_recovery_confirmation import confirm_preload,snapshot
    from training.c5_recovery_history import open_campaign
    from training.c5_recovery_controller import Campaign
    from training.c5_recovery_storage import read_private,write_once,directory
    from training.c5_reuse_evidence import strict,sha,require
    log=open_campaign(b['paths']['admission_root'],'mac',b['recovery']['scope'],h)
    try:
        c=Campaign(b['recovery']['scope'],log)
        require(c.observation()['attempts']<a.attempt and not c.observation()['active'],'recovery_confirm_before_load')
        state=Path(b['paths']['state_root']);root=state.parent/'owner-custody';directory(root)
        if not (root/('preload-snapshot-'+b['runtime_sha256']+'.json')).exists():
            from plugin.rhino_listener.c5_research_channel import read_json
            host=read_json(state,'host-continuity-ready.json')
            release=read_json(state,'entry-return-release.json')
            require(host['study_id']==b['study_id'] and host['runtime_sha256']==b['runtime_sha256']
                and host['generation_stages']==0 and release['source_inventory_sha256']==sha(r['source_files']),
                'recovery_actual_host_preload_basis')
            basis={'host':host,'release':release,'host_policy':s['host_policy'],
                   'process_observation':plan['host_acceptance']['process_observation']}
            write_once(root,'host-preload-basis-'+b['runtime_sha256']+'.json',basis)
            write_once(root,'preload-snapshot-'+b['runtime_sha256']+'.json',snapshot(c.scope,sha(basis),sha(secrets.token_hex(32))))
        snap=strict(read_private(root/('preload-snapshot-'+b['runtime_sha256']+'.json')))
        require(snap['scope_sha256']==sha(c.scope),'recovery_owner_snapshot_scope')
        receipt=confirm_preload(c.scope,snap,guard)
        if receipt is None:print('C5_RECOVERY_OWNER_CONFIRMATION_PAUSED_NO_ATTEMPT');return
        write_once(root,'owner-preload-confirmation-'+b['runtime_sha256']+'.json',receipt)
        print('C5_RECOVERY_OWNER_PRELOAD_CONFIRMED_PRIVATE_CUSTODY')
    finally:log.close()
if __name__=='__main__':main()
