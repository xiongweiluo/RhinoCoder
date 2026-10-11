"""Independent new-development raw signing/permission/ledger reducer.

No producer import, signing, dispatcher, model or Rhino API. Requires raw
databases and the exact public development plans; lifecycle/cleanup separate.
"""
import hashlib
import hmac
import os
from pathlib import Path
import stat

from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import digest, READS
from training.c5_reuse_evidence import canonical, require, sha
from training.c5_reuse_field_journal import replay_records
from training.c5_reuse_field_wire import approved_request,validate_peer_result
from training.c5_modelbridge_joint_audit import semantic
from training.c5_research_audit import audit_permission_execution, _tables
from training.c5_formal20_prepermission import rejection

WIRE_KINDS=frozenset(('wire_intent','wire_sent','wire_received','wire_ack','wire_retired'))


def audit_handoffs(rows,binding,head,plan,slot_inputs,schemas):
    replay_records(rows,binding,'controller',head)
    require(plan['development_plan_sha256']==binding['development_plan_sha256'], 'native_audit_public_plan')
    opened=False; retired=False; active=None; permission=None; signed=None
    completed=[]; spent=set(); audited={}; captures=0
    def source_for(slot):
        source=slot_inputs.get(slot)
        require(source is not None and set(source)=={'secret','consent_path','ledger_path'}, 'native_audit_slot_inputs')
        directory=Path(binding['paths']['state_root'])/slot
        require(directory.resolve()==directory,'native_audit_directory_alias')
        for key,names in (('consent_path',('consent.sqlite3','consent-audit.sqlite3')),
                          ('ledger_path',('fixture.sqlite3','fixture-audit.sqlite3','ledger.sqlite3'))):
            p=Path(source[key])
            require(p.parent==directory and p.name in names,'native_audit_database_scope')
            if os.path.lexists(p):
                info=p.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==os.getuid()
                        and not info.st_mode & 0o077,'native_audit_database_file')
        return source
    for row in rows[1:]:
        kind,p=row['kind'],row['payload']
        if kind in WIRE_KINDS: continue  # Whole raw model/transport reducer is separate.
        require(not retired, 'native_audit_event_after_retirement')
        if kind=='native_handoff_open':
            require(not opened and active is None and p=={'development_plan_sha256':binding['development_plan_sha256']},
                    'native_audit_open')
            opened=True
        elif kind=='native_handoff_intent':
            require(opened and active is None and set(p)=={'request','model_result','before'}, 'native_audit_intent')
            approved_request(binding,p['request'],plan['task_plans'])
            validate_peer_result(binding,p['request'],p['model_result'])
            inner=p['request']['request']; key=(inner['slot_id'],inner['step_index'])
            require(key not in spent and inner['step_index']==0,'native_audit_duplicate')
            spent.add(key); active=p; permission=signed=None; captures=0
            require(set(p['before'])=={'state','native'} and digest(p['before']['state'])==inner['binding_sha256']
                    and semantic(p['before']['native'])==inner['scene'], 'native_audit_actual_scene')
        elif kind=='native_signing_capture':
            require(active is not None and set(p)=={'capture'} and p['capture']==active['before'], 'native_audit_capture')
            captures+=1
        elif kind=='native_permission_intent':
            require(active is not None and captures>0 and permission is None and set(p)=={'bound_observation'}, 'native_audit_permission_order')
            expected=dict(active['model_result']['observation']); expected['scene_binding']=active['before']['state']
            require(expected['status']=='schema_valid_not_authorized' and p['bound_observation']==expected, 'native_audit_unchanged_model')
            permission=p['bound_observation']
        elif kind=='native_signed_handoff':
            require(active is not None and permission is not None and signed is None and set(p)=={'envelope'}, 'native_audit_signed_order')
            slot=active['request']['request']['slot_id']; source=source_for(slot)
            value=p['envelope']; require(set(value)=={'payload','signature'}, 'native_audit_signed_shape')
            payload=value['payload']; task=active['request']['request']['task']
            require(type(value['signature']) is str and hmac.compare_digest(value['signature'],signature(source['secret'],payload))
                    and payload['operation']==permission['name'] and payload['arguments']==permission['arguments']
                    and payload['expected']==active['before']['state']
                    and payload['owner_freeze_sha256']==binding['runtime_sha256']
                    and payload['task_sha256']==hashlib.sha256(task.encode()).hexdigest(), 'native_audit_signature_model_binding')
            policy=plan['slot_policies'][slot]
            require(policy['max_reads' if payload['operation'] in READS else 'max_writes']==1,'native_audit_task_policy')
            signed=value
        elif kind=='native_dispatch_observed':
            require(active is not None and signed is not None and set(p)=={'receipt'}, 'native_audit_dispatch_order')
            slot=active['request']['request']['slot_id']; source=source_for(slot); receipt=p['receipt']
            require(receipt.get('payload')==signed['payload'], 'native_audit_dispatch_payload')
            evidence=audit_permission_execution(source['consent_path'],source['ledger_path'],[receipt],
                task_sha256=signed['payload']['task_sha256'],owner_freeze_sha256=binding['runtime_sha256'])
            require(slot not in audited,'native_audit_extra_dispatch')
            audited[slot]=evidence; completed.append(slot); active=None
        elif kind=='native_no_permission':
            require(active is not None and permission is None and signed is None
                    and p.get('permission_reserved') is False and p.get('native_dispatches')==0
                    and p.get('status') in ('model_classified_no_native_permission','known_prepermission_rejection_no_dispatch'),
                    'native_audit_no_permission')
            observed=active['model_result']['observation']
            if observed['status']!='schema_valid_not_authorized':
                expected={'status':'model_classified_no_native_permission','model_status':observed['status'],
                          'permission_reserved':False,'native_dispatches':0}
            else:
                expected=rejection(observed['name'],observed['arguments'],active['before']['native'],schemas)
                policy=plan['slot_policies'][active['request']['request']['slot_id']]
                if expected is None and policy['max_reads' if observed['name'] in READS else 'max_writes']==0:
                    expected={'status':'known_prepermission_rejection_no_dispatch','reason':'development_task_policy',
                              'permission_reserved':False,'native_dispatches':0}
            require(expected is not None and canonical(expected)==canonical(p),'native_audit_false_refusal')
            slot=active['request']['request']['slot_id']; source=source_for(slot)
            require(not os.path.lexists(source['consent_path']),'native_audit_refusal_with_permission_database')
            ledger=_tables(source['ledger_path'],('candidate_write','c5_read'))
            require(not ledger['candidate_write'] and not ledger['c5_read'],'native_audit_hidden_dispatch_after_refusal')
            completed.append(active['request']['request']['slot_id']); active=None
        elif kind=='native_handoff_retired':
            require(set(p)=={'error_type'} and type(p['error_type']) is str,'native_audit_retired')
            retired=True
        else: raise ValueError('native_audit_unknown_event')
    require(set(slot_inputs)==set(completed), 'native_audit_extra_or_unaccounted_database')
    return {'permission_ledger_slots_verified':len(audited),'completed_handoff_classifications':len(completed),
            'complete_handoff_records':opened and bool(completed) and active is None and not retired and head is not None,
            'cleanup_verified':False,'lifecycle_verified':False,'geometry_quality_verified':False,
            'human_approval_origin_verified':False,'execution_ready':False}
