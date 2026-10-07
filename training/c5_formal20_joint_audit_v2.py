"""Custodian-only formal audit extension; no producer clock/session import.

Consumes only already-run private evidence, not a sealed package or model.
Public summary deliberately excludes task/answer/geometry/family-id bodies.
"""
from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import require,digest
from plugin.rhino_listener.c5_formal20_policy_v2 import STUDY_ID
from training.c5_formal20_joint_audit import audit_run
from training.c5_host_assurance_audit import audit_host_continuity,audit_request_checkpoint_bindings
from training.c5_lifecycle_joint_audit import audit_native_timing
from training.c5_lifecycle_timing_audit import audit_phase
from training.c5_formal20_plan import slot_order


def audit_run_v2(state,cases,spec,freeze,tokenizer,*,source_guard,external_seal_sha):
    require(spec.get('field_protocol_version')==freeze.get('field_protocol_version')==2,
        'new formal v2 audit scope required')
    source_guard()
    host=audit_host_continuity(state,STUDY_ID,digest(freeze),freeze['source_inventory_sha256'],
        external_seal_sha,normal_limit=2048,cleanup_limit=256,journal_limit=4096)
    require(host['limited_visible_continuity_verified'] is True,'formal actual host continuity incomplete')
    order=slot_order(cases,seed=spec['slot_seed']);labels=[s['slot_id'] for s in order]
    bindings=audit_request_checkpoint_bindings(state,labels,digest(freeze),journal_limit=4096)
    native=[audit_native_timing(state,digest(freeze),hub=True)]
    native += [audit_native_timing(state/slot,digest(freeze)) for slot in labels]
    require(read_json(state,'formal20.zero-started.claim.json')=={
        'study_id':STUDY_ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False},
        'formal permanent zero-stage admission missing')
    require(read_json(state,'formal20.zero-prepared.json')=={'study_id':STUDY_ID,
        'runtime_freeze_sha256':digest(freeze),'private_rows_read':0,'model_calls':0}
        and read_json(state,'formal20.hub-initialization.claim.json')=={
            'study_id':STUDY_ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False},
        'formal one-time zero preparation/private initialization differs')
    require(read_json(state,'entry-return-release.json')=={'study_id':STUDY_ID,
        'runtime_freeze_sha256':digest(freeze),'source_inventory_sha256':freeze['source_inventory_sha256'],
        'baseline_sealed':False,'replay_allowed':False}
        and read_json(state,'deferred-baseline.prepared.json')=={'study_id':STUDY_ID,
            'runtime_freeze_sha256':digest(freeze),'baseline_sealed':False,'model_calls':0}
        and not (state/'deferred-baseline.failed.json').exists(), 'formal deferred admission/release differs')
    ready=read_json(state,'worker-startup-ready.json')
    audit_phase(read_json(state,'startup-time.json'),role='startup',sequence=0,freeze_sha=digest(freeze),
        request=None,response=ready,cap=180)
    zero=read_json(state,'formal20.zero-readiness.json')
    require(zero=={'study_id':STUDY_ID,'runtime_freeze_sha256':digest(freeze),
        'host_ready_sha256':digest(read_json(state,'host-continuity-ready.json')),
        'model_ready_sha256':digest(ready),'private_rows_read':0,'formal_started_present':False},
        'actual owner pre-consumption readiness binding differs')
    warmup=read_json(state,'warmup.result.json')
    require(read_json(state,'warmup.started.json')=={'study_id':STUDY_ID,
        'runtime_freeze_sha256':digest(freeze),'replay_allowed':False},'one formal empty warmup claim required')
    require(warmup['study_id']==STUDY_ID and warmup['runtime_freeze_sha256']==digest(freeze)
        and warmup['before_native']=={'unit':'Millimeters','objects':[],'groups':{}}
        and warmup['close_capture']['fixture_before_close_native']==warmup['before_native']
        and warmup['close_capture']['fixture_registry_absent'] is True
        and warmup['close_capture']['initial_active_sha256']==warmup['close_capture']['before_close_active_sha256']
            ==warmup['close_capture']['after_close_active_sha256']==warmup['active_sha256']
        and warmup['tool_dispatches']==warmup['model_calls']==0,
        'formal empty warmup/close evidence differs')
    private=audit_run(state,cases,spec,freeze,tokenizer,source_guard=source_guard)
    keys=read_json(state,'worker-stop-response.json')['raw_records']['worker-summary.json']['attempted_keys']
    for sequence,key in enumerate(keys,1):
        audit_phase(read_json(state,key+'-model-time.json'),role='model',sequence=sequence,
            freeze_sha=digest(freeze),request=read_json(state,key+'-model-request.json'),
            response=read_json(state,key+'-model-response.json'),cap=180)
    controls=len(keys)+2
    for sequence in range(1,controls+1):
        prefix='control-%04d-'%sequence
        sent,response=read_json(state,prefix+'request.json'),read_json(state,prefix+'response.json')
        audit_phase(read_json(state,prefix+'time.json'),role='formal-control',sequence=sequence,
            freeze_sha=digest(freeze),request=sent,response=response,cap=180)
        expected_request=read_json(state,'worker-bootstrap-request.json') if sequence==1 else {
            'kind':'formal_stop','study_id':STUDY_ID,'runtime_freeze_sha256':digest(freeze)} if sequence==controls else {
            'kind':'formal_export_step','study_id':STUDY_ID,'runtime_freeze_sha256':digest(freeze),'key':keys[sequence-2]}
        expected_response=read_json(state,'worker-bootstrap-response.json') if sequence==1 else \
            read_json(state,'worker-stop-response.json') if sequence==controls else read_json(state,keys[sequence-2]+'-remote-evidence.json')
        require(sent==expected_request and response==expected_response,'formal timed control/raw evidence differs')
    require(all({p.name for p in state.glob('control-*-'+suffix+'.json')}=={
        'control-%04d-%s.json'%(n,suffix) for n in range(1,controls+1)} for suffix in ('request','response','time')),
        'extra/missing formal control timing population')
    require({p.name for p in state.glob('*-model-time.json')}=={key+'-model-time.json' for key in keys},
        'extra/missing formal model timing population')
    return {**private,'host_assurance_audit':host,'host_request_bindings':bindings,
        'native_completion_timing_audits':native,'model_complete_timing_count':len(keys),
        'control_complete_timing_count':controls,'zero_consumption_readiness_verified':True}


def public_summary(private,spec,freeze,external_seal_sha):
    require(private.get('status')=='independent_formal_raw_audit_complete'
        and private.get('zero_consumption_readiness_verified') is True,'complete owner private audit required')
    return {'study_id':STUDY_ID,'status':'owner_private_formal20_audit_verified',
        'paired_summary':dict(private['paired_summary']),
        'private_audit_sha256':digest(private),'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),
        'public_commitment_sha256':spec['public_commitment_sha256'],'external_host_seal_sha256':external_seal_sha,
        'resource_and_transport':dict(private['resource_and_transport']),
        'host_assurance_audit':dict(private['host_assurance_audit']),
        'private_content_included':False,'formal_execution_authority':False,'replay_allowed':False,
        'c5_7_decision':'not_decided_here','default_product_route_changed':False}
