"""Post-run CPU review of this approved new development only; no live calls.

Reads only revision 0002 plus the public original failure review. Never loads
model weights, creates a Rhino document, grants work or changes task scores.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import sqlite3
import sys
import tarfile
import tempfile


def main():
    if not __debug__:
        raise RuntimeError("Run this evidence review without -O; its assertions are required.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    ROOT = pathlib.Path(__file__).resolve().parents[2]
    record = ROOT / 'eval/lora-development'
    p = json.loads((record / 'development-package-recovery-20261026.json').read_text())
    canonical = json.dumps(p, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    runtime = hashlib.sha256(canonical.encode()).hexdigest()
    assert runtime == '3ddd03265f0485f1d6947cb47c5c95c60325ee6acb492b737820de04c5093ab6'
    source = pathlib.Path(p['endpoints']['mac']['source_root'])
    # Use the executed source, never a later checkout's changed parser or scorer.
    sys.path.insert(0, str(source))
    from plugin.rhino_listener.c5_research_native import digest
    from training.lora_development_export import verify_archive,read_stable
    from training.lora_development_authority import verify_source
    from training.lora_development_local_tokenizer import load_tokenizer
    from training.lora_development_scope import field_views
    from training.lora_development_cases import build_cases
    from training.lora_development_wire import reparse_response,user_step
    from training.lora_development_controller import audit_read,audit_ledger
    from training.c5_formal20_scorer import score_route,AUDIT_KEYS
    from training.c5_formal20_plan import validate_fixture_readback
    s=pathlib.Path(p['endpoints']['mac']['state_root'])
    def read(path):return json.loads(read_stable(path))
    result=read(s/'development-result.json');assert result['package_sha256']==runtime
    assert result['gpu']['status']=='gpu_stopped' and result['gpu']['stop']['exit_observed'] and result['gpu']['stop']['gpu_absence_verified']
    assert result['host']['status']=='host_stopped' and result['host']['exact_delegate_remove_returned']
    assert result['key_removal']['actual_absence_checked'] and not (s/'host-secret.json').exists()
    verify_source(source,p['source_files'])
    export=verify_archive(s/'gpu-evidence.tar',p);assert export==result['gpu_export']==read(s/'gpu-export-verified.json')
    with tarfile.open(s/'gpu-evidence.tar') as archive:
     data={m.name:archive.extractfile(m).read() for m in archive if m.isfile()}
    assert json.loads(data['gpu-settlement.json'])==result['gpu']
    views=field_views(p['development_plan']);cases={r['case']['family_id']:r['case'] for r in build_cases()}
    tokenizer=load_tokenizer(p['assets'])
    rows={r['identity']['slot_id']:r for r in result['rows']};assert len(rows)==len(result['rows'])
    assert list(rows)==[c['slot_id'] for c in views['schedule'][1:1+len(rows)]]
    original=p['campaign_policy']['resume']['review']['first_slot'];assert result['historical_rows']==[original]
    assert original['may_advance'] is False and original['outcome']=='engineering_failure'
    assert result['claimed_slots']==sum('.step-' not in f.name for f in (s/'journal').glob('*.claim.json'))
    global_root=s.parents[2]
    global_claims=sorted(f.name for f in global_root.glob('slot-*.claim.json'))
    assert global_claims==['slot-'+c['slot_id']+'.claim.json' for c in views['schedule'][:1+result['claimed_slots']]]
    assert read(global_root/'run-0002.settlement.json')['cleanup_verified'] is True
    host_requests=sorted((s/'host').glob('host-*.request.json'))
    exchanges={}
    for index,path in enumerate(host_requests,1):
     assert path.name=='host-%04d.request.json'%index
     request=read(path);response=read(s/'host'/('host-%04d.response.json'%index));payload=request['payload'];rp=response['payload']
     assert request==read(s/'controller'/('controller-host-%04d.request.json'%index))
     assert request==read(s/'host'/('request-%04d.json'%index))
     assert response==read(s/'controller'/('controller-host-%04d.response.json'%index))==read(s/'host'/('response-%04d.json'%index))
     assert payload['sequence']==rp['sequence']==index and payload['runtime_sha256']==rp['runtime_sha256']==runtime
     assert rp['slot_id']==payload['slot_id'] and rp['request_sha256']==digest(payload['request'])
     exchanges.setdefault(payload['slot_id'],[]).append((payload['request'],rp['value'],response))
    proof={k:0 if k in {'critical_safety_errors','duplicate_writes','unverified_cleanup'} else True for k in AUDIT_KEYS}
    counts=collections.Counter();summaries=[];model_requests=0;generation_stages=0;native_reads=0;tokens=0;generation_seconds=0;gpu_keys=set()
    for cell in views['schedule']:
     slot=cell['slot_id'];row=original if slot=='lora-dev-00' else rows.get(slot)
     if row is None:
      summaries.append({**cell,'outcome':'not_attempted'});continue
     if slot=='lora-dev-00':summaries.append({**cell,'outcome':row['outcome'],'historical_failure_preserved':True});continue
     e=read(s/'controller'/(slot+'.evidence.json'));assert digest(e)==row['evidence_sha256'] and e['cell']==cell
     journal_key=digest(row['identity']);assert read(s/'journal'/(journal_key+'.result.json'))==row
     assert read(global_root/('slot-'+slot+'.claim.json'))=={'package_sha256':runtime,'revision_id':2,'slot_id':slot}
     case=cases[cell['family_id']];history=exchanges[slot]
     assert history[0][0]['action']=='open'
     created=read(s/'fixtures'/slot/'created.json');assert created['headless'] and created['existing_document_content_read'] is False and created['runtime_sha256']==runtime
     assert history[0][1]['fixture_serial']==created['serial']
     captures=[v for req,v,env in history if req['action']=='capture']
     assert e['initial_native']==captures[0]['native']
     validate_fixture_readback(case,e['initial_native'])
     receipts=[];step_summaries=[];slot_generation_seconds=0
     for index,step in enumerate(e['steps']):
      saved=read(s/'controller'/(slot+'-step-%d.model.json'%index));sent,response=saved['request'],saved['response']
      obs=reparse_response(response,sent,model_views=views['model'],runtime=runtime,identity=p['model_identities'][cell['route']],tokenizer=tokenizer)
      assert obs==step['observation'];assert sent['step_index']==index
      key=digest({'slot_id':slot,'step_index':index,'runtime':runtime});gpu_keys.add(key)
      assert json.loads(data['load-0/peer/'+key+'.request.json'])==sent
      assert json.loads(data['load-0/peer/'+key+'.response.json'])==response
      for gen in response['generations']:
       assert json.loads(data['load-0/peer/'+key+'.'+gen['stage']+'.raw.json'])==gen
       generation_stages+=1;tokens+=gen['tokens'];generation_seconds+=gen['seconds'];slot_generation_seconds+=gen['seconds']
      model_requests+=1
      if step['receipt'] is not None:
       receipt=step['receipt'];matched=[(i,req) for i,(req,v,env) in enumerate(history) if req['action']=='execute' and v==receipt]
       assert len(matched)==1;i,req=matched[0]
       assert history[i-1][0]['action']=='capture'
       audit_read(receipt,req['envelope'],obs,history[i-1][1]);receipts.append(receipt);native_reads+=1
      step_summaries.append({'index':index,'status':obs['status'],'operation':obs.get('name'),'arguments':obs.get('arguments'),
        'policy_denied':step['policy_denied'],'native_dispatched':step['receipt'] is not None,'progress_status':sent['progress']['status'],
        'progress_rendered':sent['system']!='original','raw_generation_stages':len(response['generations'])})
     if e['error_type'] is None:
      assert [req['action'] for req,_,_ in history][-2:]==['close','stop']
      assert history[-2][1]==e['close'] and history[-1][1]==e['stop']
      assert e['close']['fixture_registry_absent'] and e['stop']['fixture_registry_absent'] and not e['stop']['host_blocked']
      assert e['close']['fixture_serial']==created['serial'] and e['close']['fixture_before_close_native']==e['final_native']==captures[-1]['native']
      audit_ledger(e['stop']['ledger'],receipts)
      # Read copied SQLite+WAL, never open or checkpoint the original evidence DB.
      fixture=s/'fixtures'/slot
      with tempfile.TemporaryDirectory(prefix='lora-audit-ledger-') as td:
       target=pathlib.Path(td)
       for f in fixture.glob('fixture.sqlite3*'):(target/f.name).write_bytes(read_stable(f))
       db=sqlite3.connect(str(target/'fixture.sqlite3'));db.row_factory=sqlite3.Row
       try:
        db.execute('PRAGMA query_only=ON');assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        ledger={name:[dict(r) for r in db.execute('SELECT * FROM '+name)] for name in ('candidate_write','c5_read')}
       finally:db.close()
      assert ledger==e['stop']['ledger'];audit_ledger(ledger,receipts)
      rescored=score_route(case,{'family_id':cell['family_id'],'slot_id':slot,'route':'base' if cell['route']=='base' else 'lora',
       'steps':e['steps'],'initial_native':e['initial_native'],'final_native':e['final_native'],'close':'closed','stop':'stopped'},proof)
      assert rescored==e['score'] and row['outcome']==('success' if rescored['outcome_correct'] else 'task_failure')
     else:assert row['outcome']=='engineering_failure'
     summary={**cell,'outcome':row['outcome'],'steps':step_summaries,'score':e['score'],'failure_stages':[f['stage'] for f in e['failures']],
     'execution':row.get('execution'),'generation_seconds':slot_generation_seconds,'evidence_sha256':digest(e)}
     summaries.append(summary)
    actual_gpu_keys={name.rsplit('/',1)[-1].removesuffix('.request.json') for name in data if name.startswith('load-0/peer/') and name.endswith('.request.json')}
    assert actual_gpu_keys==gpu_keys
    assert len(list((s/'controller').glob('*.model.json')))==model_requests
    selection=read(s/'journal/selection.json') if (s/'journal/selection.json').exists() else None
    if selection:assert selection['selected_system']=='original' and selection['selection_complete'] is False and selection['candidate_promoted'] is False
    for row in summaries:counts[(row['role'],row['route'],row['system'],row['outcome'])]+=1
    aggregate=[]
    for role in ('selection','acceptance'):
     for route in p['development_plan']['routes']:
      for system in p['development_plan']['systems']:
       aggregate.append({'role':role,'route':route,'system':system,'fixed_n':4,'counts':{outcome:counts[(role,route,system,outcome)] for outcome in ('success','task_failure','engineering_failure','evidence_unknown','not_attempted')}})
    report={'schema_version':1,'package_sha256':runtime,'executed_commit':'82e3dee514fbb15c4f537f97100b2f61e3cb2621','ci_run_id':40406546105,
     'original_population':32,'historical_consumed_slots':1,'new_consumed_slots':result['claimed_slots'],'new_completed_results':len(rows),'rows':summaries,'aggregate':aggregate,
     'model_requests':model_requests,'generation_stages':generation_stages,'native_reads':native_reads,'model_writes':0,'generated_tokens':tokens,
     'generation_seconds':generation_seconds,'gpu_supervisor_seconds':result['gpu']['elapsed_seconds_including_load_and_idle'],
     'cumulative_gpu_supervisor_seconds':93.39306430588476+result['gpu']['elapsed_seconds_including_load_and_idle'],
     'mac_controller_seconds':result['elapsed_seconds'],'cumulative_loads_consumed':5,'remaining_loads':0,'selection':selection,
     'gpu_export':export,'host_settlement':result['host'],'gpu_stop':result['gpu']['stop'],'host_secret_absence_verified':True,
     'controller_error_type':result['error_type'],'controller_failures':result.get('failures',[]),
     'independent_review':{'source_bytes':True,'request_response_copies_and_bindings':True,'raw_output_reparse':True,'gpu_controller_output_join':True,
     'actual_sqlite_ledger_read_copy':True,'native_receipt_and_final_readback':True,'unchanged_score_recompute':True,'cleanup_and_export':True,
     'hmac_reverified_after_key_removal':False,'hmac_limit':'Live frozen controller/host verified HMAC; disposed secret is not recreated or retained for post-run re-verification.',
     'whole_host_byte_closure_proven':False,'historical_family_independence_proven':False},
     'actual_paid_lease_amount':None,'additional_resource_actions':0,'training_executed':False,'final_test_executed':False,'phase_one_complete':False}
    # Raw generations and new fixture geometry stay private; report contains only public case labels, observations and audit statistics.
    assert not report['controller_failures'], 'sanitize and review failures before public publication'
    with args.output.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('new_consumed_slots','new_completed_results','model_requests','generation_stages','native_reads','gpu_supervisor_seconds','aggregate')},ensure_ascii=False))


if __name__ == "__main__":
    main()
