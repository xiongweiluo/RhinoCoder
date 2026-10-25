#!/usr/bin/env python3
"""Owner-side fixed public-eight original raw audit; no model or Rhino calls."""
import hashlib
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--attempt',type=int,required=True,choices=(1,2,3));a=p.parse_args()
    from plugin.rhino_listener.c5_recovery_mac_scope import mac_scope
    from plugin.rhino_listener.c5_recovery_runtime_scope import read_bytes
    from plugin.rhino_listener.c5_recovery_profile import INSTANCE,PLAN
    MAC_PARENT=Path("/Users/xiongweiluo/RhinoCoder/data/training/c5")
    from plugin.rhino_listener.c5_recovery_scope import material
    from plugin.rhino_listener.c5_reuse_public_plan import public_plan,SOURCE
    from plugin.rhino_listener.c5_research_channel import read_json
    from training.c5_reuse_evidence import strict,require,sha
    from training.c5_reuse_field_journal import read_journal,read_record
    from training.c5_reuse_control_journal import read_control
    from training.c5_recovery_field_eight_audit import audit_field_eight
    from training.c5_execution import load_pinned_tokenizer,load_config
    spec,runtime,mac,plan,history,approval,guard=mac_scope(ROOT,a.attempt,cleanup_only=True,private_prefixes=('__main__',))
    state=Path(mac['paths']['state_root']);custody=state.parent/'owner-custody'
    external=strict(read_bytes(custody/('owner-final-attempt-'+str(a.attempt)+'.json'),private=True))
    import time
    gpu=material(spec,runtime,now=time.time(),endpoint='gpu',attempt=a.attempt,cleanup_only=True)
    export_raw=read_bytes(state/'gpu-public-eight-raw-export.json',limit=64*1024*1024,private=True)
    export=strict(export_raw,limit=64*1024*1024)
    controller=read_journal(state/'controller',mac,'controller',external['controller_head_sha256'])
    native_root=state/'native-controller';names=set(p.name for p in native_root.iterdir())
    require(0<len(names)<=128 and names=={'raw-%04d.json'%i for i in range(len(names))},'reuse_audit_native_disk_population')
    native=[read_record(native_root,'raw-%04d.json'%i)[0] for i in range(len(names))]
    public=public_plan(ROOT);slots={}
    for slot in public['order']:
        key=read_json(state/'audit-key-custody',slot+'.json')
        require(key['runtime_sha256']==mac['runtime_sha256'],'reuse_audit_key_scope')
        d=state/slot
        slots[slot]={'secret':bytes.fromhex(key['key_hex']),'consent_path':d/'consent.sqlite3','ledger_path':d/'fixture.sqlite3'}
    hub_key=read_json(state/'audit-key-custody','hub.json')
    require(hub_key['runtime_sha256']==mac['runtime_sha256'],'reuse_audit_hub_key_scope')
    tokenizer=load_pinned_tokenizer(MAC_PARENT/'modelbridge-tokenizer'/spec['comparison']['base_revision'],
                                   config=load_config(ROOT/'eval/c5/c5-engineering-config.json'))
    from training.c5_recovery_history import open_campaign
    from training.c5_recovery_controller import replay
    from training.c5_recovery_field_permit import permit
    campaign_log=open_campaign(mac['paths']['admission_root'],'mac',mac['recovery']['scope'],history)
    try:
        initial=campaign_log.binding;campaign_rows=campaign_log.rows()
    finally:campaign_log.close()
    load_permit=strict(read_bytes(state/'load-permit.json',limit=1048576,private=True),limit=1048576)
    ready_raw=read_bytes(state/'ready-proof-stdout.raw',limit=1048576,private=True)
    ready_proof=strict(ready_raw,limit=1048576)
    guard(cleanup_only=True)
    result=audit_field_eight(mac=mac,gpu=gpu,spec=spec,runtime=runtime,plan=plan,plan_raw=read_bytes(ROOT/PLAN),
        controller=controller,controller_head=external['controller_head_sha256'],export=export,native=native,
        native_head=external['native_head_sha256'],public=public,
        schemas=strict(read_bytes(ROOT/'eval/c5/rhino-runtime-schema-v1.json'))['core_parameters'],slot_inputs=slots,
        hub_secret=bytes.fromhex(hub_key['key_hex']),tokenizer=tokenizer,external=external,
        write_assertions=strict(read_bytes(ROOT/SOURCE))['independent_write_assertions'],
        actual_deployment_receipts=strict(read_bytes(custody/'actual-deployment-byte-receipts.json',private=True)),
        mac_lifecycle=read_control(state/'controller-lifecycle',mac,'controller-lifecycle',head=external['mac_lifecycle_head_sha256']),
        mac_lifecycle_head=external['mac_lifecycle_head_sha256'],gpu_export_raw=export_raw,
        campaign_initial_scope=initial,campaign_rows=campaign_rows,load_permit=load_permit,grant=approval,ready_proof=ready_proof)
    guard(cleanup_only=True)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
