"""Fixed Mac preparation/drive/audit; new exact owner approval is mandatory.

No UI automation, arbitrary task/output path, retry, recovery, training,
holdout entry, original final run or default-route mutation. ScriptEditor
hub is explicitly started separately under the same new human grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import time

from pathlib import Path
from plugin.rhino_listener.c5_research_channel import publish_json,read_json,claim_slot
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import digest,require
from tools.c5_hostassurance_dev_common import ROOT,STATE,SOCKET,ID,scope,public,mac_origins
from plugin.rhino_listener.c5_hostassurance_development_scope import PIN,PIN_SHA
from training.c5_model_transport import request,FramedPipe,rebind_observation,strict_json,LIMIT
from training.c5_modelbridge_runtime import Budget,file_sha
from training.c5_research_permission import ResearchSigner,SceneView
from training.c5_modelbridge_joint_audit import audit_model_native_chain,audit_native_trace,audit_lifecycle,audit_geometry,semantic
from training.consent_candidate import ConsentStore
from training.c5_inventory import load_public_mcp_tools
from training.c5_execution import load_config,load_pinned_tokenizer
from training.c5_contract import render_selection,render_invocation,CORE_INVOCATION_TOOLS

TOKENIZER=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/modelbridge-tokenizer/c03e6d358207e414f1eca0bb1891e29f1db0e242')
REMOTE_STATE='/data/c5-hostassurance-dev-state-20261007-A'
REMOTE_SOURCE='/data/RhinoCoder-c5-hostassurance-dev-A'


def preflight(*,include_manifest=False):
    spec=public(ROOT/'eval/c5/hostassurance-development-spec-20261007-a.json')
    # Only a previously frozen TRAIN artifact, never any final/development
    # private file. No new semantic family is manufactured for this probe.
    train=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/v2/accepted/train.jsonl')
    require(file_sha(train)==spec['task_source']['train_artifact_sha256'],'excluded training source identity differs')
    families={}
    with train.open('rb') as stream:
        for line in stream:
            family=strict_json(line)
            if family['family_id'] in spec['task_source']['family_ids'].values():
                require(family['family_id'] not in families,'duplicate selected training family')
                families[family['family_id']]=family
    require(len(families)==4,'four already-excluded train families required')
    for slot,p in spec['task_plans'].items():
        kind=slot.split('-')[0];family=families[spec['task_source']['family_ids'][kind]]
        require(family['split']=='train' and family['review']['status']=='approved'
                and any(r['stage']=='selector' and r['user_step']==p['steps'][0] for r in family['records']),
                'development text is not exact frozen training text')
    tokenizer=load_pinned_tokenizer(TOKENIZER,config=load_config())
    tools=load_public_mcp_tools()
    # Hypothetical CPU rendering only, not oracle forcing a model selection.
    sizes=[]
    for slot in spec['slot_order']:
        task=spec['task_plans'][slot]['steps'][0]
        from training.c5_rhino_adapter import step_input
        text=step_input(task,{'unit':'Millimeters','objects':[],'groups':{}})
        sizes.append(len(tokenizer(render_selection(tokenizer,text,tools).prompt,add_special_tokens=False)['input_ids'])+128)
        for name in CORE_INVOCATION_TOOLS:
            sizes.append(len(tokenizer(render_invocation(tokenizer,text,tools,name).prompt,add_special_tokens=False)['input_ids'])+512)
    require(max(sizes)<=2048,'CPU development context limit exceeded')
    origins=mac_origins()
    return {'status':'mac_modelbridge_cpu_preflight_not_execution_authority',
            'mac_environment_sha256':origins['inventory_sha256'],
            'mac_environment_file_count':len(origins['file_sha256']),
            **({'mac_environment':origins} if include_manifest else {}),
            'tokenizer_files':{p.name:file_sha(p) for p in sorted(TOKENIZER.iterdir()) if p.is_file()},
            'max_input_plus_output_reserve_tokens':max(sizes),'model_calls':0,'gpu_calls':0,'holdout_calls':0}


class Channel:
    """One known request at a time. Uncertain ack permanently blocks sender."""
    def __init__(self,directory,secret,freeze_sha,task=None,*,hub=False,guard=lambda:None):
        self.directory,self.secret,self.freeze,self.task,self.hub,self.guard=directory,secret,freeze_sha,task,hub,guard
        self.seq,self.unresolved=1,False

    def exchange(self,message):
        self.guard()
        require(not self.unresolved and self.seq<=(16 if self.hub else 64),'unresolved/bounded native channel; no resend')
        self.unresolved=True
        prefix='hub-' if self.hub else ''
        publish_json(self.directory,prefix+'request-%04d.json'%self.seq,message)
        deadline=time.monotonic()+25
        name=prefix+'response-%04d.json'%self.seq
        while not (self.directory/name).exists():
            require(time.monotonic()<deadline,'unknown native acknowledgement; never guess cleanup')
            time.sleep(0.05)
        result=read_json(self.directory,name)
        self.seq+=1;self.unresolved=False
        return result

    def control(self,action,slot=None):
        if self.hub:
            p={'version':1,'request_id':secrets.token_urlsafe(24),'action':action,'slot_id':slot,
               'owner_freeze_sha256':self.freeze,'expires_at':int(time.time())+120}
            return self.exchange({'payload':p,'signature':signature(self.secret,p)})
        p={'version':1,'request_id':secrets.token_urlsafe(24),'action':action,
           'owner_freeze_sha256':self.freeze,'task_sha256':hashlib.sha256(self.task.encode()).hexdigest(),
           'expires_at':int(time.time())+120}
        return self.exchange({'kind':'control','envelope':{'payload':p,'signature':signature(self.secret,p)}})


def prepare():
    spec,freeze,approval,guard=scope()
    Budget(freeze['resource_boundary'])
    publish_json(STATE,ID+'.admission.claim.json',{'probe_id':ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    publish_json(STATE,'hub.key',{'key_hex':secrets.token_bytes(32).hex()})
    for slot in spec['slot_order']:
        directory=STATE/slot;directory.mkdir(mode=0o700)
        publish_json(directory,'handoff.key',{'key_hex':secrets.token_bytes(32).hex()})
    publish_json(STATE,'prepared.json',{'probe_id':ID,'runtime_freeze_sha256':digest(freeze),'model_calls':0,'holdout_calls':0})
    return {'status':'new_owner_approved_prepared_not_executed','probe_id':ID}


def ssh_args():
    require(SOCKET.is_socket(),'existing authenticated SSH master required')
    require(file_sha(PIN)==PIN_SHA,'new independently pinned SSH transport differs')
    return ['ssh','-T','-S',str(SOCKET),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+str(PIN),'-o','HostKeyAlgorithms=ssh-ed25519',
            '-p','22159','linux@175.155.64.171']


class ActualAtomic:
    """Re-read the actual fixture at each permission decision, never a cache."""
    def __init__(self,channel,expected,record):
        self.channel,self.expected,self.record=channel,expected,record

    def _capture(self):
        actual=self.channel.control('capture')
        require(actual['status']=='captured' and actual['state']==self.expected['state']
                and actual['native']==self.expected['native'],'actual fixture drift before signing')
        self.record['signing_captures'].append(actual)
        return actual

    def snapshot(self):return self._capture()['state']

    def semantic_scene(self):return semantic(self._capture()['native'])


def drive():
    spec,freeze,approval,guard=scope()
    require(read_json(STATE,'hub-bootstrap.json')['runtime_freeze_sha256']==digest(freeze),'approved hub not ready')
    require(read_json(STATE,'prepared.json')['runtime_freeze_sha256']==digest(freeze),'prepared scope differs')
    ready=read_json(STATE,'host-continuity-ready.json')
    require(ready=={'study_id':ID,'runtime_freeze_sha256':digest(freeze),
                   'legacy_byte_closure_verified':False,'sealed_before_model_generation':True},
            'new limited-host baseline has not been sealed; no model start')
    budget=Budget(freeze['resource_boundary'])
    publish_json(STATE,ID+'.driver-started.claim.json',{'probe_id':ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    result={'probe_id':ID,'status':'incomplete_no_replay','slots':[],'error':None,'holdout_calls':0,
            'complete_C5_engineering_gate_passed':False,'formal_quality_claim':False}
    hub=Channel(STATE,bytes.fromhex(read_json(STATE,'hub.key')['key_hex']),digest(freeze),hub=True,guard=guard)
    fd=os.open(STATE/'worker-stderr.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    process=None
    try:
        command='cd '+REMOTE_SOURCE+' && /data/conda-envs/rhinocoder/bin/python -B -m tools.run_c5_hostassurance_dev_worker serve'
        process=subprocess.Popen(ssh_args()+[command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=fd)
        wire=FramedPipe(process,timeout=spec['per_request_timeout_seconds'])
        for slot in spec['slot_order']:
            guard();budget.check()
            plan,policy=spec['task_plans'][slot],spec['slot_policies'][slot]
            task=plan['steps'][0];directory=STATE/slot
            claim_scope={'stage':'development','task_sha256':hashlib.sha256(task.encode()).hexdigest(),
                         'route':plan['route'],'owner_freeze_sha256':digest(freeze)}
            claim_slot(STATE,digest(claim_scope),claim_scope)
            opened=hub.control('open',slot)
            require(opened['status']=='slot_opened' and opened['slot_id']==slot,'known native slot opening failed')
            child=Channel(directory,bytes.fromhex(read_json(directory,'handoff.key')['key_hex']),digest(freeze),task,guard=guard)
            slot_result={'slot':slot,'model_record':None,'receipt':None,'close':None,'stop':None,'error':None}
            try:
                before=child.control('capture')
                require(before['status']=='captured','initial actual scene capture failed')
                sent=request(ID,slot,plan['route'],0,task,semantic(before['native']),before['state'],digest(freeze),secrets.token_urlsafe(24))
                publish_json(directory,'model-request.json',sent)
                response=wire.exchange(sent)
                publish_json(directory,'model-response.json',response)
                budget.check();guard()
                current=child.control('capture')
                require(current['status']=='captured' and current['state']==before['state']
                        and current['native']==before['native'],'post-model actual capture differs')
                observed=rebind_observation(response,sent,freeze['model_identities'][plan['route']],current['state'])
                record={'capture':before,'post_model_capture':current,'signing_captures':[],
                        'request':sent,'response':response,'handoff_request_id':None}
                store=ConsentStore(directory/'consent.sqlite3',load_public_mcp_tools())
                proxy=ActualAtomic(child,current,record)
                scene=SceneView(proxy,proxy.semantic_scene)
                signer=ResearchSigner(store,scene,child.secret,digest(freeze),task,
                         max_writes=policy['max_writes'],max_reads=policy['max_reads'])
                if observed['status']=='schema_valid_not_authorized':
                    # Never turn a zero-write/read policy into permission.
                    from plugin.rhino_listener.c5_research_native import READS
                    denied=(observed['name'] in READS and policy['max_reads']==0) or (observed['name'] not in READS and policy['max_writes']==0)
                    if not denied:
                        envelope=signer.issue(observed,schemas=public(ROOT/'eval/c5/rhino-runtime-schema-v1.json')['core_parameters'])
                        record['handoff_request_id']=envelope['payload']['request_id']
                        receipt=child.exchange({'kind':'execute','envelope':envelope})
                        slot_result['receipt']=receipt
                        require(receipt['status']=='done','native execution failed; no retry')
                slot_result['model_record']=record
                publish_json(directory,'model-joint-record.json',record)
            except BaseException as exc:
                slot_result['error']=type(exc).__name__+': '+str(exc)
            if not child.unresolved:
                try:
                    slot_result['close']=child.control('close')
                    require(slot_result['close']['status']=='closed','closure unverified')
                    slot_result['stop']=child.control('stop')
                    require(slot_result['stop']['status']=='stopped','stop unverified')
                except BaseException as exc:slot_result['error']=(slot_result['error'] or '')+'; '+type(exc).__name__+': '+str(exc)
            publish_json(directory,'slot-result.json',slot_result)
            result['slots'].append(slot_result)
            require(slot_result['error'] is None,'slot operational/safety failure; retire probe, do not continue')
        result['hub_stop']=hub.control('stop')
        require(result['hub_stop']['status']=='hub_stopped','hub closure unverified')
        result['status']='modelbridge_execution_complete_not_independently_audited'
    except BaseException as exc:
        result['error']=type(exc).__name__+': '+str(exc)
        result['status']='modelbridge_fail_retired_no_replay'
        # Only known stopped children permit hub stop; no guessing after an
        # unknown open/execute ack. Preserve all raw claims/keys for reconcile.
        if not hub.unresolved and (not result['slots'] or result['slots'][-1].get('stop',{})):
            try:result['hub_stop']=hub.control('stop')
            except BaseException:pass
    finally:
        os.close(fd)
        if process is not None:
            process.stdin.close()
            try:result['remote_process_exit_code']=process.wait(timeout=180)
            except subprocess.TimeoutExpired:result['remote_process_exit_code']=None
            process.stdout.close()
        publish_json(STATE,'result.json',result)
    return {k:result[k] for k in ('probe_id','status','error','holdout_calls','complete_C5_engineering_gate_passed')}


def export_remote():
    """Read only the NEW fixed development state's public audit bundle."""
    spec,freeze,approval,guard=scope(check_time=False)
    result=read_json(STATE,'result.json')
    require(result['status']=='modelbridge_execution_complete_not_independently_audited'
            and result['remote_process_exit_code']==0 and len(result['slots'])==8,
            'remote export requires clean completed development run')
    guard()
    command='cd '+REMOTE_SOURCE+' && /data/conda-envs/rhinocoder/bin/python -B -m tools.run_c5_hostassurance_dev_worker export'
    raw=subprocess.check_output(ssh_args()+[command],timeout=180)
    require(0<len(raw)<=LIMIT,'bounded read-only remote evidence required')
    value=strict_json(raw)
    require(value['probe_id']==ID and value['runtime_freeze_sha256']==digest(freeze)
            and value['holdout_rows_read']==0,'remote export scope differs')
    publish_json(STATE,'remote-audit-bundle.json',value)
    return {'status':'read_only_remote_evidence_exported_not_audited','record_count':len(value['records']),
            'holdout_rows_read':0}


def audit(external_host_seal_sha256):
    spec,freeze,approval,guard=scope(check_time=False)
    from training.c5_host_assurance_audit import audit_host_continuity,audit_request_checkpoint_bindings
    host=audit_host_continuity(STATE,ID,digest(freeze),freeze['source_inventory_sha256'],external_host_seal_sha256)
    require(host['limited_visible_continuity_verified'] is True,'new actual limited-host continuity did not pass')
    host_bindings=audit_request_checkpoint_bindings(STATE,spec['slot_order'],digest(freeze))
    warmup=read_json(STATE,'warmup.result.json')
    require(read_json(STATE,'warmup.started.json')=={'study_id':ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False}
            and warmup['study_id']==ID and warmup['runtime_freeze_sha256']==digest(freeze)
            and warmup['before_native']=={'unit':'Millimeters','objects':[],'groups':{}}
            and warmup['close_capture']['fixture_before_close_native']==warmup['before_native']
            and warmup['close_capture']['fixture_registry_absent'] is True
            and warmup['close_capture']['initial_active_sha256']==warmup['close_capture']['before_close_active_sha256']
            ==warmup['close_capture']['after_close_active_sha256']==warmup['active_sha256']
            and warmup['tool_dispatches']==warmup['model_calls']==0,
            'independent empty warmup/close evidence differs')
    result=read_json(STATE,'result.json')
    require(result['status']=='modelbridge_execution_complete_not_independently_audited'
            and result['error'] is None and result['remote_process_exit_code']==0
            and [r['slot'] for r in result['slots']]==spec['slot_order'],'incomplete/failed probe not promoted')
    tokenizer=load_pinned_tokenizer(TOKENIZER,config=load_config())
    # Prime all hypothetical render paths before checking frozen imports.
    guard()
    native_writes=native_reads=generations=0
    quality={}
    for slot_result in result['slots']:
        slot=slot_result['slot'];directory=STATE/slot;plan=spec['task_plans'][slot]
        raw=read_json(directory,'slot-result.json')
        require(raw==slot_result,'raw slot result differs')
        record=read_json(directory,'model-joint-record.json')
        require(record==slot_result['model_record'],'raw joint record differs')
        require(read_json(directory,'model-request.json')==record['request']
                and read_json(directory,'model-response.json')==record['response'],
                'raw model wire files differ from joint record')
        receipts=[slot_result['receipt']] if slot_result['receipt'] is not None else []
        audit_native_trace(directory,record,slot_result['receipt'],slot_result['close'],slot_result['stop'])
        chain=audit_model_native_chain([record],receipts,directory/'consent.sqlite3',directory/'fixture.sqlite3',
                 task=plan['steps'][0],freeze_sha=digest(freeze),model_identity=freeze['model_identities'][plan['route']],tokenizer=tokenizer)
        native_writes+=chain['ledger']['write_count'];native_reads+=chain['ledger']['read_count'];generations+=chain['model_generation_calls']
        last=receipts[-1]['after'] if receipts else record['capture']['native']
        lifecycle=audit_lifecycle(read_json(directory,'bootstrap.json'),read_json(directory,'engine-created.json'),
                        slot_result['close'],slot_result['stop'],last,freeze['source_inventory_sha256'],key_present=(directory/'handoff.key').exists())
        require(lifecycle['had_failure'] is False,'native lifecycle reported a failure')
        kind=slot.split('-')[0];observed=record['response']['observation']
        if kind=='write':
            quality[slot]=bool(receipts) and audit_geometry(receipts[0]['before'],receipts[0]['after'],spec['independent_write_assertions'])['geometry_passed']
        elif kind=='read':
            quality[slot]=bool(receipts) and receipts[0]['payload']['operation']=='get_scene_summary' and receipts[0]['result']==semantic(record['capture']['native'])
        elif kind=='clarify':quality[slot]=observed['status']=='abstained_no_dispatch' and not receipts
        else:quality[slot]=observed['status'] in {'unsupported_for_c5_no_dispatch','abstained_no_dispatch'} and not receipts
    # Remote raw resource/loader records must be explicitly exported before
    # audit. This mode never connects or silently fabricates those records.
    remote_bundle=read_json(STATE,'remote-audit-bundle.json')
    require(remote_bundle['probe_id']==ID and remote_bundle['runtime_freeze_sha256']==digest(freeze)
            and remote_bundle['holdout_rows_read']==0,'remote evidence bundle scope differs')
    remote_records=remote_bundle['records']
    remote=remote_records['resource-settlement.json']
    loaded=remote_records['loaded-runtime.json']
    require(remote['status']=='worker_stopped_no_replay' and remote['resource_boundary_sha256']==digest(freeze['resource_boundary'])
            and 0 <= remote['elapsed_seconds_including_load_and_idle'] <= remote['cap_seconds'] <= 3600
            and loaded['environment_sha256']==freeze['environment_sha256']
            and loaded['source_inventory_sha256']==freeze['source_inventory_sha256']
            and loaded['adapter_sha256']==spec['adapter_sha256'],'actual remote runtime/resource evidence differs')
    require(remote_records['worker-summary.json']['requests']==8
            and len(result['slots'])==8
            and remote_records[ID+'.worker-started.claim.json']['runtime_freeze_sha256']==digest(freeze),
            'remote worker claim/summary differs')
    for slot_result in result['slots']:
        slot=slot_result['slot'];record=slot_result['model_record']
        key=digest({'slot':slot,'step':0,'freeze':digest(freeze)})
        sent,response=record['request'],record['response']
        require(remote_records['generation-'+key+'.claim.json']=={
            'request_sha256':digest(sent),'replay_allowed':False}
            and remote_records[key+'-response.json']==response,
            'remote generation claim/response differs from Mac raw wire')
        for receipt in response['generation_receipts']:
            stage=receipt['stage']
            attempted=remote_records[key+'-'+stage+'-attempt.json']
            generated=remote_records[key+'-'+stage+'-raw.json']
            require(attempted['stage']==stage and attempted['prompt_sha256']==receipt['prompt_sha256']
                    and attempted['attempted'] is True and generated==receipt,
                    'remote raw stage evidence differs from model response')
    stopped=read_json(STATE,'hub-stop.json');bootstrap=read_json(STATE,'hub-bootstrap.json')
    require(stopped==result['hub_stop'] and stopped['opened_slots']==spec['slot_order']
            and stopped['active_serial']==bootstrap['active_serial'] and stopped['active_sha256']==bootstrap['active_sha256']
            and stopped['hub_key_absence']=={'key_removed':True,'actual_absence_checked':True}
            and stopped['hook_removed_in_same_callback'] is True and stopped['had_failure'] is False
            and not (STATE/'hub.key').exists(),'actual hub closure differs')
    guard()
    require(generations<=spec['generation_calls_max'] and generations>=8,'generation count/budget differs')
    gate=native_writes>=1 and native_reads>=1 and all(r['error'] is None for r in result['slots']) \
         and all(r['close']['status']=='closed' and r['stop']['status']=='stopped' for r in result['slots'])
    return {'probe_id':ID,'status':'independent_modelbridge_development_audit_complete_not_formal_quality',
            'complete_C5_engineering_gate_passed':gate,'all_eight_slots_classified':True,
            'development_semantic_outcomes':quality,'native_writes':native_writes,'native_reads':native_reads,
            'generation_calls':generations,'formal_quality_claim':False,'holdout_calls':0,
            'gpu_wall_seconds':remote['elapsed_seconds_including_load_and_idle'],'replay_allowed':False,
            'host_assurance_audit':host,'host_request_bindings':host_bindings,
            'legacy_byte_closure_verified':False,'warmup_fixture_closed':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('preflight','prepare','drive','export','audit'))
    p.add_argument('--external-host-seal-sha256');a=p.parse_args()
    if a.mode=='audit':
        require(a.external_host_seal_sha256 is not None,'externally captured host terminal receipt required')
        value=audit(a.external_host_seal_sha256)
    else:value={'preflight':preflight,'prepare':prepare,'drive':drive,'export':export_remote}[a.mode]()
    print(json.dumps(value,sort_keys=True))


if __name__=='__main__':main()
