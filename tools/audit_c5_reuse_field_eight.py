#!/usr/bin/env python3
"""Owner-side fixed public-eight original raw audit; no model or Rhino calls."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from plugin.rhino_listener.c5_reuse_mac_scope import mac_scope
    from plugin.rhino_listener.c5_reuse_runtime_scope import MAC_PARENT,INSTANCE,read_bytes,PLAN
    from plugin.rhino_listener.c5_reuse_field_scope import bind
    from plugin.rhino_listener.c5_reuse_public_plan import public_plan,SOURCE
    from plugin.rhino_listener.c5_research_channel import read_json
    from training.c5_reuse_evidence import strict,require,sha
    from training.c5_reuse_field_journal import read_journal,read_record
    from training.c5_reuse_control_journal import read_control
    from training.c5_reuse_field_eight_audit import audit_field_eight
    from training.c5_execution import load_pinned_tokenizer,load_config
    spec,runtime,mac,plan,guard=mac_scope(ROOT,cleanup_only=True,private_prefixes=('__main__',))
    state=Path(mac['paths']['state_root']);custody=MAC_PARENT/(INSTANCE+'-external-custody')
    external=strict(read_bytes(custody/'owner-final-custody.json',private=True))
    approval=read_json(state,'owner-approval.json')
    import time
    gpu=bind(spec,runtime,approval,now=time.time(),endpoint='gpu',cleanup_only=True)
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
    guard(cleanup_only=True)
    result=audit_field_eight(mac=mac,gpu=gpu,spec=spec,runtime=runtime,plan=plan,plan_raw=read_bytes(ROOT/PLAN),
        controller=controller,controller_head=external['controller_head_sha256'],export=export,native=native,
        native_head=external['native_head_sha256'],public=public,
        schemas=strict(read_bytes(ROOT/'eval/c5/rhino-runtime-schema-v1.json'))['core_parameters'],slot_inputs=slots,
        hub_secret=bytes.fromhex(hub_key['key_hex']),tokenizer=tokenizer,external=external,
        write_assertions=strict(read_bytes(ROOT/SOURCE))['independent_write_assertions'],
        actual_deployment_receipts=strict(read_bytes(custody/'actual-deployment-byte-receipts.json',private=True)),
        mac_lifecycle=read_control(state/'controller-lifecycle',mac,'controller-lifecycle',head=external['mac_lifecycle_head_sha256']),
        mac_lifecycle_head=external['mac_lifecycle_head_sha256'],gpu_export_raw=export_raw)
    guard(cleanup_only=True)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
