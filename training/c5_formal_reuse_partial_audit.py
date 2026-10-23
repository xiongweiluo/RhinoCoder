"""Additional owner-only retrospective partial audit; no field authority.

Original full40 gates and all deployed code remain unchanged. The remote
verifier is copied from the frozen original with only its minimum population
changed from 40 to 0; exact prefix/claim joins below constrain every attempt.
No model, Rhino operation, decryption, new grant, ledger mutation or retry.
SQLite readers may create sidecars: the owner wrapper MUST audit a verified
private copy and compare the original inventory before and after.
"""
import hashlib,hmac,math,os
from plugin.rhino_listener.c5_research_gate import signature
from training.c5_formal_reuse_joint_audit_base import (read_json,digest,require,STUDY_ID,file_sha,_sha_record)

def audit_partial_remote(state, spec, freeze):
    v2=spec.get('field_protocol_version')==2
    from training.c5_formal_reuse_evidence_audit import audit_resource
    stop = read_json(state, 'worker-stop-response.json')
    require(stop.get('status') == 'formal_worker_stopped' and stop.get('runtime_freeze_sha256') == digest(freeze)
        and stop.get('request_sha256') == digest({'kind': 'formal_stop', 'study_id': STUDY_ID,
            'runtime_freeze_sha256': digest(freeze)}), 'formal raw worker stop scope differs')
    require(read_json(state, 'worker-process-exit.json') == {'exit_code': 0, 'replay_allowed': False}, 'formal remote exit unknown')
    raw = stop['raw_records']
    required = {'bootstrap.json', 'loaded-runtime.json', 'worker-summary.json', 'resource-settlement.json',
        'formal20.worker-started.claim.json'}
    if v2: required |= {'worker-startup-ready.json','worker-bootstrap-response.json','owner-approval.json'}
    require(set(raw) == required, 'formal remote lifecycle population differs')
    require(raw['bootstrap.json'] == read_json(state, 'worker-bootstrap-request.json')
        and raw['bootstrap.json']['plans'] == read_json(state, 'model-plans-hashed.json')
        and raw['bootstrap.json']['started'] == read_json(state, 'formal20.started.json'), 'formal bootstrap/local claim differs')
    require(raw['formal20.worker-started.claim.json'] == {'study_id': STUDY_ID,
        'runtime_freeze_sha256': digest(freeze), 'replay_allowed': False}, 'formal worker permanent claim differs')
    ready = read_json(state, 'worker-bootstrap-response.json')
    expected_ready={'status':'formal_worker_ready','request_sha256':digest(raw['bootstrap.json']),
        'runtime_freeze_sha256':digest(freeze),'model_identities':freeze['model_identities']}
    if v2:
        from training.c5_startup_audit import audit_startup_ready
        expected_ready['startup_receipt']=read_json(state,'worker-startup-ready.json')
        audit_startup_ready(expected_ready['startup_receipt'],raw['worker-startup-ready.json'],freeze,STUDY_ID)
        require(raw['worker-bootstrap-response.json']==expected_ready
            and raw['owner-approval.json']==__import__('plugin.rhino_listener.c5_formal_reuse_scope',
                fromlist=['expected_grant']).expected_grant(spec,freeze,
                    execution_approved=raw['owner-approval.json'].get('actual_execution_approved') is True)
            and ('run_package' not in spec or raw['owner-approval.json'].get('actual_execution_approved') is True),
            'formal raw ready/grant inventory differs')
    require(ready==expected_ready,'formal model ready binding differs')
    assets, loaded = stop['asset_environment_preflight'], raw['loaded-runtime.json']
    require(assets['source_files'] == freeze['source_files'] and assets['source_inventory_sha256'] == freeze['source_inventory_sha256']
        and assets['fixed_public_files'] == freeze['fixed_public_files'] and assets['environment_sha256'] == freeze['environment_sha256']
        and digest(assets['environment']) == freeze['environment_sha256']
        and {'base': digest(assets['snapshot']), 'lora': assets['adapter_sha256']} == freeze['model_identities']
        and digest(assets['adapter_files']) == freeze['model_identities']['lora'], 'formal asset/environment raw inventory differs')
    require(loaded['study_id'] == STUDY_ID and loaded['environment_sha256'] == freeze['environment_sha256']
        and loaded['source_inventory_sha256'] == freeze['source_inventory_sha256'] and loaded['model_identities'] == freeze['model_identities']
        and loaded['gpu'] == 'NVIDIA GeForce RTX 3090' and loaded['default_route_changed'] is False
        and loaded['base_route'] == 'same PEFT-wrapped base with disable_adapter context'
        and loaded['base_dtype_cast'] == 'prepare_model_for_kbit_training_no_checkpoint_hooks', 'formal loaded model route differs')
    resource = raw['resource-settlement.json']; boundary = freeze['resource_boundary']
    require(stop['resource'] == resource and resource['status'] == 'formal_worker_stopped_no_replay'
        and resource['study_id'] == STUDY_ID and resource['resource_boundary_sha256'] == digest(boundary)
        and resource['replay_allowed'] is False, 'formal resource settlement binding differs')
    for k in ('elapsed_seconds_including_load_and_idle', 'cap_seconds', 'start_epoch', 'stop_epoch'):
        require(type(resource[k]) in (int, float) and math.isfinite(resource[k]), 'formal finite settlement required')
    elapsed = resource['elapsed_seconds_including_load_and_idle']
    audit_resource(resource,boundary,status='formal_worker_stopped_no_replay',
        first_epoch=read_json(state,'load-permit.json')['first_load_epoch'],
        package=freeze.get('run_package'),permit=read_json(state,'load-permit.json'))
    summary = raw['worker-summary.json']
    keys = summary['attempted_keys']
    require(isinstance(keys, list) and len(keys) == len(set(keys)) == summary['requests']
        and 0 <= len(keys) <= (56 if v2 else 120) and type(summary['generation_stages']) is int
        and summary['generation_stages'] <= spec['max_generation_stages'], 'formal worker attempts/count differs')
    all_records, stages = dict(raw), 0
    for key in keys:
        export = read_json(state, key + '-remote-evidence.json')
        require(set(export) == {'status', 'request_sha256', 'key', 'records'} and export['status'] == 'formal_raw_step_evidence'
            and export['key'] == key and export['request_sha256'] == digest({'kind': 'formal_export_step',
                'study_id': STUDY_ID, 'runtime_freeze_sha256': digest(freeze), 'key': key}), 'formal export response differs')
        records = export['records']
        sent = read_json(state, key + '-model-request.json'); response = read_json(state, key + '-model-response.json')
        require(records.get(key + '-request.json') == sent and records.get(key + '-response.json') == response
            and records.get('generation-' + key + '.claim.json') == {'request_sha256': digest(sent), 'replay_allowed': False},
            'formal raw generation request/claim/response differs')
        require(key == digest({'slot': sent['slot_id'], 'step': sent['step_index'], 'freeze': digest(freeze)}),
            'formal generation key differs')
        expected = {key + '-request.json', key + '-response.json', 'generation-' + key + '.claim.json'}
        for receipt in response['generation_receipts']:
            stage = receipt['stage']; stages += 1
            attempt = {'stage': stage, 'prompt_sha256': receipt['prompt_sha256'], 'attempted': True, 'tokens': 0, 'seconds': 0.0}
            require(records.get(key + '-' + stage + '-attempt.json') == attempt
                and records.get(key + '-' + stage + '-raw.json') == receipt, 'formal raw attempt/output differs')
            expected.update({key + '-' + stage + '-attempt.json', key + '-' + stage + '-raw.json'})
        require(set(records) == expected, 'formal extra/missing remote generation records')
        require(not set(all_records) & set(records), 'formal duplicate remote evidence')
        all_records.update(records)
    require(stages == summary['generation_stages'] and set(stop['file_sha256']) == set(all_records)
        and all(stop['file_sha256'][n] == _sha_record(v) for n, v in all_records.items()), 'formal complete remote raw byte inventory differs')
    require({p.name for p in state.glob('*-model-request.json')} == {k + '-model-request.json' for k in keys}
        and {p.name for p in state.glob('*-model-response.json')} == {k + '-model-response.json' for k in keys}
        and {p.name for p in state.glob('*-remote-evidence.json')} == {k + '-remote-evidence.json' for k in keys},
        'formal extra/missing local model attempts')
    return {'generation_stages': stages, 'elapsed_seconds_including_load_and_idle': elapsed,
        'peak_allocated_bytes': summary['peak_allocated_bytes'], 'peak_reserved_bytes': summary['peak_reserved_bytes'], 'keys': keys}

def failed_admission(state,spec,freeze):
    from training.c5_formal_reuse_admission import open_formal_campaign
    from plugin.rhino_listener.c5_formal_reuse_scope import MAC_STATE
    campaign=open_formal_campaign(spec,freeze,read_json(MAC_STATE,'owner-approval.json'),freeze['history'])
    try:
        value=campaign.observation();rows=campaign.log.rows();permit=read_json(state,'load-permit.json')
        require(value['status']=='FORMAL_CONSUMED_NO_RETRY' and value['formal_consumed'] is True
            and value['active'] is False and value['attempts']==int(state.name.removeprefix('preload-')),
            'partial_original_consumed_failure_required')
        require(rows[:len(permit['rows'])]==permit['rows']
            and sum(r['kind']=='private_exposure_intent' for r in rows)==1
            and sum(r['kind']=='generation_begin_intent' for r in rows)==1
            and value['first_load_epoch']==permit['first_load_epoch'], 'partial_original_history_join')
        return {'attempts_consumed':value['attempts'],'formal_exposures':1,'first_load_epoch':value['first_load_epoch'],
            'original_history_preserved':True,'ledger_usage_unsettled':value['attempts'] not in value['settled_attempts']}
    finally:campaign.log.close()


def partial_signatures(state,freeze,order,cases,opened):
    labels=['hub']+[s['slot_id'] for s in order];by_id={c['family_id']:c for c in cases}
    slots={s['slot_id']:s for s in order};custody=state/'audit-key-custody';seen=set();count=0
    require({p.name for p in custody.iterdir()}=={n+'.json' for n in labels},'partial_exact_41_key_custody')
    for label in labels:
        key=read_json(custody,label+'.json')
        require(set(key)=={'key_hex','runtime_sha256'} and key['runtime_sha256']==digest(freeze)
            and type(key['key_hex']) is str and len(key['key_hex'])==64,'partial_key_scope')
        secret=bytes.fromhex(key['key_hex']);directory=state if label=='hub' else state/label
        paths=sorted(directory.glob('hub-request-*.json' if label=='hub' else 'request-*.json'))
        require(bool(paths)==(label=='hub' or label in opened),'partial_signed_request_population')
        for path in paths:
            message=read_json(directory,path.name);envelope=message if label=='hub' else message['envelope'];body=envelope['payload']
            require(body['owner_freeze_sha256']==digest(freeze) and body['request_id'] not in seen
                and hmac.compare_digest(envelope['signature'],signature(secret,body)),'partial_hmac_or_duplicate')
            if label!='hub':require(body['task_sha256']==hashlib.sha256(by_id[slots[label]['family_id']]['task_text'].encode()).hexdigest(),
                'partial_signed_private_task_binding')
            seen.add(body['request_id']);count+=1
        require(not os.path.lexists(directory/('hub.key' if label=='hub' else 'handoff.key')),'partial_dispatch_key_remains')
    return {'signed_requests_recomputed':count,'audit_keys_retained':41,'dispatch_keys_absent':True,'memory_erasure_proven':False}


def failed_pre_model_slot(state,case,slot,result,freeze,tokenizer):
    """Narrow read-only branch: failed before first model step, closed/stopped."""
    from training.c5_formal20_plan import validate_fixture_readback
    from training.c5_formal_reuse_model_native_audit import audit_model_native_chain,audit_lifecycle
    directory=state/slot['slot_id']
    require(result['slot_id']==slot['slot_id'] and result['family_id']==case['family_id']
        and result['route']==slot['route'] and result['error_type']=='FormalPlanError'
        and result['initial_native'] is None and result['steps']==[] and result['final_native'] is None
        and result['close']=='closed' and result['stop']=='stopped','partial_narrow_pre_model_failure')
    names=['%04d.json'%n for n in range(1,4)]
    require(sorted(p.name for p in directory.glob('request-*.json'))==['request-'+n for n in names]
        and sorted(p.name for p in directory.glob('response-*.json'))==['response-'+n for n in names]
        and not list(directory.glob('execute-*.json')) and not list(directory.glob('signing-*.json')),
        'partial_failed_slot_no_hidden_dispatch')
    responses=[]
    for n,action in enumerate(('capture','close','stop'),1):
        sent=read_json(directory,'request-%04d.json'%n);response=read_json(directory,'response-%04d.json'%n)
        require(sent['kind']=='control' and sent['envelope']['payload']['action']==action,'partial_failed_control_order')
        responses.append(response)
    initial,close,stop=responses
    require(initial['status']=='captured','partial_failed_actual_initial_capture')
    reproduced=False
    try:validate_fixture_readback(case,initial['native'])
    except ValueError:reproduced=True
    bootstrap=read_json(directory,'bootstrap.json');created=read_json(directory,'engine-created.json')
    require(bootstrap['native']==initial['native'] and bootstrap['owner_freeze_sha256']==digest(freeze)
        and bootstrap['task_sha256']==hashlib.sha256(case['task_text'].encode()).hexdigest()
        and created['rhino_version']==freeze['rhino_version'],'partial_failed_actual_bootstrap')
    last={'unit':'Millimeters','objects':[],'groups':{}}
    expected=[]
    for n,recipe in enumerate(case['fixture_recipe']):
        claim=read_json(directory,'seed-%02d.claim.json'%n);seeded=read_json(directory,'seed-%02d.result.json'%n)
        require(claim=={'index':n,**recipe,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False}
            and seeded['index']==n and seeded['operation']==recipe['operation'] and seeded['arguments']==recipe['arguments']
            and seeded['before']==last,'partial_failed_seed_chain')
        last=seeded['after'];expected+=['seed-%02d.claim.json'%n,'seed-%02d.result.json'%n]
    require(last==bootstrap['native'] and sorted(p.name for p in directory.glob('seed-*.json'))==sorted(expected),
        'partial_failed_seed_population')
    backups=read_json(directory,'database-backups.json')
    require(set(backups)=={'consent','fixture'} and all(file_sha(directory/(n+'-audit.sqlite3'))==sha for n,sha in backups.items()),
        'partial_failed_sqlite_snapshot_hash')
    chain=audit_model_native_chain([],[],directory/'consent-audit.sqlite3',directory/'fixture-audit.sqlite3',
        task=case['task_text'],freeze_sha=digest(freeze),model_identity=freeze['model_identities'][slot['route']],tokenizer=tokenizer)
    lifecycle=audit_lifecycle(bootstrap,created,close,stop,initial['native'],freeze['source_inventory_sha256'],
        key_present=os.path.lexists(directory/'handoff.key'))
    require(lifecycle['had_failure'] is False and chain['native_executions']==0,'partial_failed_known_cleanup')
    return {'pre_model_failure_verified':True,'initial_fixture_validation_rejection_reproduced':reproduced,
        'diagnosis':'initial_fixture_readback_rejected' if reproduced else 'unattributed_pre_model_FormalPlanError',
        'model_requests':0,'native_model_dispatches':0,'known_lifecycle_verified':True}


def audit_partial(state,cases,spec,freeze,tokenizer,*,source_guard,on_stage=lambda _:None):
    """Additional retrospective component audit; never the original full PASS."""
    from training.c5_formal20_plan import validate_families,slot_order,family_merkle_root,slot_order_sha256
    from training.c5_formal_reuse_joint_audit_base import audit_run,audit_slot,semantic
    from training.c5_host_assurance_audit import audit_host_continuity,audit_request_checkpoint_bindings
    from training.c5_lifecycle_joint_audit import audit_native_timing
    from training.c5_lifecycle_timing_audit import audit_phase
    from training.c5_formal_reuse_evidence_audit import audit_supervisor,audit_resource,audit_residency_join
    from training.c5_formal_reuse_runtime import hashed_model_plans
    from training.c5_rhino_adapter import step_input
    source_guard();cases=validate_families(cases);order=slot_order(cases,seed=spec['slot_seed']);sha=digest(freeze)
    require(family_merkle_root(cases)==spec['family_merkle_root_sha256'] and slot_order_sha256(order)==spec['slot_order_sha256'],
        'partial_original_case_schedule_commitment')
    run=read_json(state,'formal20.run-result.json');n=run['slots_attempted']
    require(type(n) is int and 1<=n<40 and run=={'study_id':STUDY_ID,'status':'formal_incomplete_no_replay',
        'slots_attempted':n,'route_slots_required':40,'error_type':'FormalRunError','c5_6_gate_claim':False},'partial_incomplete_original_run')
    try:audit_run(state,cases,spec,freeze,tokenizer,source_guard=source_guard)
    except (ValueError,RuntimeError) as error:require(str(error)=='formal incomplete run cannot pass audit','partial_unexpected_original_gate_error')
    else:raise ValueError('partial_original_full_gate_must_reject')
    require(read_json(state,'formal20.started.json')=={'study_id':STUDY_ID,'spec_sha256':digest(spec),
        'runtime_freeze_sha256':sha,'public_commitment_sha256':spec['public_commitment_sha256'],'replay_allowed':False},'partial_original_exposure')
    used=order[:n];labels=[s['slot_id'] for s in used];by_id={c['family_id']:c for c in cases}
    require(sorted(p.name for p in state.glob('F*.result.json'))==sorted(s+'.result.json' for s in labels)
        and sorted(p.name for p in state.glob('F*.engine-started.claim.json'))==sorted(s+'.engine-started.claim.json' for s in labels),
        'partial_exact_attempted_prefix')
    native={'slot_order':order,'plans':{s['slot_id']:{k:by_id[s['family_id']][k] for k in
        ('task_text','fixture_recipe','max_writes','max_reads')} for s in order}}
    model=hashed_model_plans({s['slot_id']:{'route':s['route'],'steps':[by_id[s['family_id']]['task_text']]*by_id[s['family_id']]['max_steps']} for s in order})
    require(read_json(state,'native-plans.json')==native and read_json(state,'model-plans-hashed.json')==model
        and read_json(state,'native-prepared.json')=={'study_id':STUDY_ID,'native_plans_sha256':digest(native),'runtime_freeze_sha256':sha},
        'partial_complete_original_40_plans')
    custody=read_json(state,'owner-automatic-receipt-custody.json');terminal=read_json(state,'host-continuity-terminal-receipt.json')
    require(custody=={'receipt':terminal,'custody':'owner_authorized_automatic_capture','manual_external_receipt_attestation':False,
        'runtime_sha256':sha},'partial_actual_automatic_receipt_custody')
    on_stage('host_continuity')
    host=audit_host_continuity(state,STUDY_ID,sha,freeze['source_inventory_sha256'],terminal['seal_sha256'],
        normal_limit=2048,cleanup_limit=256,journal_limit=4096)
    bindings=audit_request_checkpoint_bindings(state,labels,sha,journal_limit=4096)
    timings=[audit_native_timing(state,sha,hub=True)]+[audit_native_timing(state/s,sha) for s in labels]
    on_stage('remote_raw_inventory')
    remote=audit_partial_remote(state,spec,freeze)
    supervisor=audit_supervisor(state,spec,freeze)
    admission=failed_admission(state,spec,freeze)
    require(supervisor['permit_first_load_epoch']==admission['first_load_epoch'],'partial_original_first_load_join')
    partial_sign=partial_signatures(state,freeze,order,cases,set(labels))
    on_stage('slot_raw_chains')
    keys=[];prompts={};native_calls=0;completed=0;failed=None;expected_steps=set();expected_claims=set()
    for i,slot in enumerate(used):
        label=slot['slot_id'];case=by_id[slot['family_id']];result=read_json(state,label+'.result.json')
        scope={'stage':'formal','task_sha256':hashlib.sha256(case['task_text'].encode()).hexdigest(),
            'route':slot['route'],'owner_freeze_sha256':sha};claim=digest(scope)+'.claim.json';expected_claims.add(claim)
        require(read_json(state,claim)=={'version':1,'slot_sha256':digest(scope),'scope':scope,'replay_allowed':False}
            and read_json(state,label+'.engine-started.claim.json')=={'study_id':STUDY_ID,'slot_id':label,
                'runtime_freeze_sha256':sha,'replay_allowed':False},'partial_slot_permanent_consumption')
        if i==n-1:
            failed=failed_pre_model_slot(state,case,slot,result,freeze,tokenizer)
            require(not result['steps'],'partial_no_failed_slot_generation')
        else:
            proof,chain=audit_slot(state,case,slot,result,freeze,tokenizer)
            native_calls+=chain['native_executions'];completed+=1
            prompt=step_input(case['task_text'],semantic(result['initial_native']))
            if case['family_id'] in prompts:require(prompts[case['family_id']]==prompt,'partial_paired_initial_prompt')
            else:prompts[case['family_id']]=prompt
        for index,step in enumerate(result['steps']):
            prefix=label+'-step-%d'%index;expected_steps.add(prefix)
            require(read_json(state,prefix+'.record.json')==step and read_json(state,prefix+'.claim.json')=={
                'slot_id':label,'step_index':index,'scene_sha256':digest(step['before']['native']),
                'runtime_freeze_sha256':sha,'replay_allowed':False},'partial_raw_step_binding')
            keys.append(digest({'slot':label,'step':index,'freeze':sha}))
    require(keys==remote['keys'] and {p.name for p in state.glob('F*-step-*.claim.json')}=={s+'.claim.json' for s in expected_steps}
        and {p.name for p in state.glob('F*-step-*.record.json')}=={s+'.record.json' for s in expected_steps}
        and {p.name for p in state.glob('*.claim.json') if len(p.name)==75}==expected_claims,'partial_exact_raw_generation_prefix')
    bootstrap=read_json(state,'hub-bootstrap.json');stop=read_json(state,'hub-stop.json')
    require(bootstrap['study_id']==STUDY_ID and bootstrap['runtime_freeze_sha256']==sha
        and bootstrap['source_sha256']==stop['source_sha256']==freeze['source_inventory_sha256']
        and bootstrap['native_plans_sha256']==digest(native) and stop['status']=='hub_stopped' and stop['opened_slots']==labels
        and set(stop['unused_keys_removed'])=={s['slot_id'] for s in order[n:]}
        and len(stop['unused_keys_removed'])==40-n and stop['had_failure'] is False
        and stop['hook_removed_in_same_callback'] is True and stop['hub_key_absence']=={'key_removed':True,'actual_absence_checked':True}
        and bootstrap['active_serial']==stop['active_serial'] and bootstrap['active_sha256']==stop['active_sha256']
        and not os.path.lexists(state/'hub.key'),'partial_hub_full_cleanup')
    require(sorted(p.name for p in state.glob('hub-request-*.json'))==['hub-request-%04d.json'%i for i in range(1,n+2)]
        and sorted(p.name for p in state.glob('hub-response-*.json'))==['hub-response-%04d.json'%i for i in range(1,n+2)],'partial_hub_controls')
    for i in range(1,n+2):
        sent=read_json(state,'hub-request-%04d.json'%i)['payload'];response=read_json(state,'hub-response-%04d.json'%i)
        require(sent['owner_freeze_sha256']==sha,'partial_hub_request_scope')
        if i<=n:require(sent['action']=='open' and sent['slot_id']==labels[i-1] and response['status']=='slot_opened'
            and response['slot_id']==sent['slot_id'] and response['fixture_serial']==read_json(state/sent['slot_id'],'engine-created.json')['fixture_serial'],
            'partial_hub_open_original_fixture')
        else:require(sent['action']=='stop' and sent['slot_id'] is None and response==stop,'partial_hub_stop')
    ready=read_json(state,'worker-startup-ready.json');audit_phase(read_json(state,'startup-time.json'),role='startup',sequence=0,
        freeze_sha=sha,request=None,response=ready,cap=600)
    for seq,key in enumerate(keys,1):audit_phase(read_json(state,key+'-model-time.json'),role='model',sequence=seq,
        freeze_sha=sha,request=read_json(state,key+'-model-request.json'),response=read_json(state,key+'-model-response.json'),cap=360)
    require({p.name for p in state.glob('*-model-time.json')}=={k+'-model-time.json' for k in keys},'partial_model_timing_population')
    controls=len(keys)+2
    for seq in range(1,controls+1):
        prefix='control-%04d-'%seq;sent=read_json(state,prefix+'request.json');response=read_json(state,prefix+'response.json')
        expected_request=read_json(state,'worker-bootstrap-request.json') if seq==1 else {'kind':'formal_stop','study_id':STUDY_ID,
            'runtime_freeze_sha256':sha} if seq==controls else {'kind':'formal_export_step','study_id':STUDY_ID,'runtime_freeze_sha256':sha,'key':keys[seq-2]}
        expected_response=read_json(state,'worker-bootstrap-response.json') if seq==1 else read_json(state,'worker-stop-response.json') if seq==controls else read_json(state,keys[seq-2]+'-remote-evidence.json')
        require(sent==expected_request and response==expected_response,'partial_control_raw_binding')
        audit_phase(read_json(state,prefix+'time.json'),role='formal-control',sequence=seq,freeze_sha=sha,request=sent,response=response,cap=360)
    for suffix in ('request','response','time'):require({p.name for p in state.glob('control-*-'+suffix+'.json')}=={
        'control-%04d-%s.json'%(i,suffix) for i in range(1,controls+1)},'partial_control_timing_population')
    on_stage('resource_join')
    local=read_json(state,'resource-settlement.json');permit=read_json(state,'load-permit.json')
    audit_resource(local,freeze['resource_boundary'],status='formal_mac_driver_finished',first_epoch=permit['first_load_epoch'],
        package=freeze.get('run_package'),permit=permit)
    residency=audit_residency_join(state,spec,freeze) if 'run_package' in freeze else None
    source_guard()
    return {'schema_version':1,'study_id':STUDY_ID,'status':'additional_partial_raw_joint_components_verified_not_full40',
        'spec_sha256':digest(spec),'runtime_freeze_sha256':sha,'original_complete_40_gate_passed':False,
        'original_complete_gate_rejection':'formal incomplete run cannot pass audit','recorded_slots_attempted':n,
        'completed_slot_raw_chains_verified':completed,'failed_pre_model_slot':failed,'unattempted_slots':40-n,
        'raw_model_requests_verified':len(keys),'generation_stages_verified':remote['generation_stages'],
        'native_model_executions_verified':native_calls,'host_continuity_audit':host,'host_request_bindings':bindings,
        'native_timing_audits':timings,'signature_audit':partial_sign,'qualified_gpu_audit':supervisor,
        'admission_audit':admission,'residency_audit':residency,'external_host_seal_sha256':terminal['seal_sha256'],
        'paired_summary':None,'full40_quality_result':None,'partial_quality_scores_reported':False,
        'c5_6_gate_claim':False,'original_c5_no_go_changed':False,'default_product_route_changed':False,
        'read_only_retrospective_extension':True,'manual_per_receipt_attestation':False,
        'new_independent_holdout_claimed':False,'private_content_included':False,'model_or_rhino_calls':0,
        'research_restarted':False,'replay_allowed':False}
