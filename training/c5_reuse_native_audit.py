"""Independent complete public-eight native/lifecycle raw population reducer.

Imports no controller, entry, hub, signer, loader or producer. Quality is
recomputed separately from engineering; legal wrong geometry is preserved.
External witness integrity here never manufactures human-origin evidence.
"""
import hashlib
import hmac
import os
from pathlib import Path
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import digest
from plugin.rhino_listener.c5_reuse_runtime_scope import read_bytes
from training.c5_reuse_evidence import require,exact,sha,ZERO
from training.c5_reuse_field_scope import validate_binding
from training.c5_reuse_native_handoff_audit import audit_handoffs
from training.c5_modelbridge_joint_audit import audit_native_trace,audit_lifecycle,audit_geometry,semantic
from training.c5_lifecycle_joint_audit import audit_native_timing
from training.c5_host_assurance_audit import audit_host_continuity,audit_request_checkpoint_bindings

ORDER=('write-base','write-lora','read-lora','read-base','clarify-base','clarify-lora','unsupported-lora','unsupported-base')


def replay_native(rows,binding,head):
    validate_binding(binding);require(type(rows) is list and 0<len(rows)<=128,'reuse_native_audit_rows')
    previous=ZERO
    for i,row in enumerate(rows):
        exact(row,('seq','previous_sha256','scope_sha256','kind','payload','record_sha256'))
        require(type(row['seq']) is int and row['seq']==i and row['previous_sha256']==previous
                and row['scope_sha256']==sha(binding)
                and row['record_sha256']==sha({k:v for k,v in row.items() if k!='record_sha256'}),'reuse_native_audit_chain')
        previous=row['record_sha256']
    require(previous==head and rows[0]['kind']=='native_controller_open'
            and rows[0]['payload']=={'binding':binding},'reuse_native_audit_anchor')
    kinds=['native_controller_open','host_ready_before_remote_launch']
    for _ in ORDER:kinds+=['slot_open_intent','slot_model_scene','slot_native_result','slot_closed']
    kinds+=['hub_closed','controller_completed_records']
    return [r['kind'] for r in rows]==kinds


def audit_native_eight(rows,binding,head,handoffs,handoff_head,public,schemas,slot_inputs,hub_secret,
                       *,source_files,external_host_seal_sha256,write_assertions):
    complete=replay_native(rows,binding,head)
    require(complete,'reuse_native_audit_incomplete_no_promotion')
    state=Path(binding['paths']['state_root']);runtime=binding['runtime_sha256'];source=sha(source_files)
    require(public['order']==list(ORDER) and set(slot_inputs)==set(ORDER),'reuse_native_audit_exact_eight')
    handoff=audit_handoffs(handoffs,binding,handoff_head,public,slot_inputs,schemas)
    require(handoff['complete_handoff_records'] and handoff['completed_handoff_classifications']==8,
            'reuse_native_audit_missing_handoff')
    captures={slot:[] for slot in ORDER};intents={};observed={};current=None
    for row in handoffs:
        p=row['payload']
        if row['kind']=='native_handoff_intent':
            current=p['request']['request']['slot_id'];intents[current]=p
        elif row['kind']=='native_signing_capture':captures[current].append(p['capture'])
        elif row['kind']=='native_dispatch_observed':observed[current]=p['receipt']
    host_ready=rows[1]['payload'];require(host_ready['release']==read_json(state,'entry-return-release.json')
        and host_ready['ready']==read_json(state,'host-continuity-ready.json')
        and host_ready['release']['source_inventory_sha256']==source,'reuse_native_audit_baseline_before_launch')
    quality={};timing=0;serials=set();request_ids=set()
    for i,slot in enumerate(ORDER):
        opening,model,native,closing=[r['payload'] for r in rows[2+i*4:6+i*4]]
        require(all(p['slot_id']==slot for p in (opening,model,native,closing)),'reuse_native_audit_order')
        directory=state/slot;intent=intents[slot];sent=model['request'];receipt=observed.get(slot)
        require(intent['request']==sent and intent['model_result']==native['model_result']
                and intent['before']=={k:model['capture'][k] for k in ('state','native')}
                and native['post_model_capture']['state']==model['capture']['state']
                and native['post_model_capture']['native']==model['capture']['native'], 'reuse_native_audit_model_raw_join')
        require(receipt==native['native_result'] if receipt is not None else
                native['native_result'].get('permission_reserved') is False,'reuse_native_audit_dispatch_join')
        # Construct expected capture trace from raw handoff captures, never
        # expected scoring geometry. Native trace must have exact population.
        signing=[{'status':'captured',**p,'active_sha256':model['capture']['active_sha256']} for p in captures[slot]]
        record={'capture':model['capture'],'post_model_capture':native['post_model_capture'],'signing_captures':signing}
        audit_native_trace(directory,record,receipt,closing['close'],closing['stop'])
        for path in sorted(directory.glob('request-*.json')):
            message=read_json(directory,path.name);e=message['envelope'];p=e['payload']
            require(p['request_id'] not in request_ids and p['owner_freeze_sha256']==runtime
                    and p['task_sha256']==hashlib.sha256(public['task_plans'][slot]['steps'][0].encode()).hexdigest()
                    and hmac.compare_digest(e['signature'],signature(slot_inputs[slot]['secret'],p)),
                    'reuse_native_audit_control_signature')
            request_ids.add(p['request_id'])
        created=read_json(directory,'engine-created.json');serial=created['fixture_serial']
        require(serial not in serials,'reuse_native_audit_fixture_reuse');serials.add(serial)
        last=receipt['after'] if receipt else model['capture']['native']
        lifecycle=audit_lifecycle(read_json(directory,'bootstrap.json'),created,closing['close'],closing['stop'],last,
            source,key_present=os.path.lexists(directory/'handoff.key'))
        require(not lifecycle['had_failure'],'reuse_native_audit_bridge_failure')
        if receipt:
            require(receipt['stable_idle_samples']==3 and 3<=len(receipt['settling_samples'])<=8
                    and receipt['settling_samples'][-1]==receipt['settling_samples'][-2]==receipt['settling_samples'][-3]
                    and receipt['settling_samples'][-1]['native']==receipt['after']
                    and receipt['settling_samples'][-1]['state']==receipt['after_state'],'reuse_native_audit_settled_raw')
        timing+=audit_native_timing(directory,runtime)['native_requests_with_complete_timing']
        kind=slot.split('-')[0];status=native['model_result']['observation']['status']
        if kind=='write':quality[slot]=bool(receipt) and audit_geometry(receipt['before'],receipt['after'],write_assertions)['geometry_passed']
        elif kind=='read':quality[slot]=bool(receipt) and receipt['payload']['operation']=='get_scene_summary' and receipt['result']==semantic(model['capture']['native'])
        elif kind=='clarify':quality[slot]=status=='abstained_no_dispatch' and receipt is None
        else:quality[slot]=status in ('abstained_no_dispatch','unsupported_for_c5_no_dispatch') and receipt is None
        for proof in closing['database_backups']:
            p=directory/proof['name']
            require(p.name in ('fixture-audit.sqlite3','consent-audit.sqlite3')
                    and hashlib.sha256(read_bytes(p,limit=16*1024*1024,private=True)).hexdigest()==proof['raw_sha256'],'reuse_native_audit_backup_hash')
    requests=sorted(state.glob('hub-request-*.json'))
    require(len(requests)==9,'reuse_native_audit_hub_population')
    for i,path in enumerate(requests):
        require(path.name=='hub-request-%04d.json'%(i+1),'reuse_native_audit_hub_sequence')
        e=read_json(state,path.name);p=e['payload'];response=read_json(state,'hub-response-%04d.json'%(i+1))
        require(p['owner_freeze_sha256']==runtime and p['action']==('open' if i<8 else 'stop')
                and p['slot_id']==(ORDER[i] if i<8 else None)
                and hmac.compare_digest(e['signature'],signature(hub_secret,p)),'reuse_native_audit_hub_control')
        if i<8:require(response=={'status':'slot_opened','slot_id':ORDER[i],
            'fixture_serial':read_json(state/ORDER[i],'engine-created.json')['fixture_serial']},'reuse_native_audit_open_response')
        else:require(response==rows[-2]['payload']['receipt']==read_json(state,'hub-stop.json'), 'reuse_native_audit_hub_stop_response')
    stopped=rows[-2]['payload']['receipt']
    require(stopped['opened_slots']==list(ORDER) and stopped['unused_keys_removed']==[] and not stopped['had_failure']
            and stopped['hub_key_absence']=={'key_removed':True,'actual_absence_checked':True}
            and stopped['hook_removed_in_same_callback'] is True and not os.path.lexists(state/'hub.key'),
            'reuse_native_audit_hub_cleanup')
    timing+=audit_native_timing(state,runtime,hub=True)['native_requests_with_complete_timing']
    host=audit_host_continuity(state/'host',binding['study_id'],runtime,source,external_host_seal_sha256,
                               normal_limit=2048,cleanup_limit=256,journal_limit=4096)
    require(host['limited_visible_continuity_verified'],'reuse_native_audit_host_continuity')
    terminal=read_json(state,'host-continuity-terminal-receipt.json')
    require(terminal==rows[-2]['payload']['host_terminal'] and terminal['seal_sha256']==external_host_seal_sha256,
            'reuse_native_audit_external_terminal_join')
    audit_request_checkpoint_bindings(state,ORDER,runtime,journal_limit=4096,host_root=state/'host')
    warmup=read_json(state,'warmup.result.json');c=warmup['close_capture']
    require(warmup['study_id']==binding['study_id'] and warmup['runtime_freeze_sha256']==runtime
        and warmup['before_native']=={'unit':'Millimeters','objects':[],'groups':{}}
        and c['fixture_before_close_native']==warmup['before_native'] and c['fixture_registry_absent'] is True
        and c['initial_active_sha256']==c['before_close_active_sha256']==c['after_close_active_sha256']==warmup['active_sha256']
        and warmup['model_calls']==warmup['tool_dispatches']==0,'reuse_native_audit_warmup')
    return {'complete_eight_native_permission_lifecycle_records':True,'quality_by_slot':quality,
            'all_eight_quality_passed':all(quality.values()),'raw_timed_native_messages':timing,
            'limited_host_continuity':host,'private_audit_keys_retained':True,'memory_erasure_proven':False,
            'human_origin_independently_proven':False,'physical_gpu_release_verified':None,'whole_field_pass':False}
