"""Independent synthetic raw joins, including rehashed semantic tampering."""
import contextlib
import copy
import hashlib
from pathlib import Path

import pytest

from eval.test_c5_model_transport import Tokenizer
from eval.test_c5_reuse_gpu_entry import plan_records,begin_for,Pipe
from training.c5_model_transport import request
from training.c5_reuse_evidence import canonical,raw_sha,sha,ZERO
from training.c5_reuse_field_scope import bind,STUDY,PROTOCOL,common_scope
from training.c5_reuse_development_plan import public_plan,ORDER
from training.c5_reuse_field_wire import envelope,frame
from training.c5_reuse_control_journal import ControlJournal
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_generation import GenerationPeer
from training.c5_reuse_worker_loop import serve,readiness
from training.c5_reuse_gpu_entry_audit import audit_gpu_entry
from training.c5_reuse_budget import ReuseBudget
from plugin.rhino_listener.c5_reuse_runtime_scope import PLAN


def bundle(tmp_path):
    spec,runtime,plan,approval=plan_records(tmp_path)
    plans=public_plan(Path(__file__).resolve().parents[1])['task_plans']
    spec['development_plan_sha256']=sha(plans)
    plan_raw=canonical(plan);runtime['source_files'][PLAN]=raw_sha(plan_raw)
    runtime['spec_sha256']=sha(spec);approval.update(spec_sha256=sha(spec),runtime_sha256=sha(runtime))
    b=bind(spec,runtime,approval,now=100,endpoint='gpu')
    (tmp_path/'gpu').mkdir();Path(b['paths']['state_root']).mkdir(mode=0o700)
    clock=[100.0];budget=ReuseBudget(spec['resources'],wall=lambda:clock[0],mono=lambda:clock[0])
    supervisor=ControlJournal(b,'supervisor');lifecycle=ControlJournal(b,'worker-lifecycle')
    argv=['/data/conda-envs/rhinocoder/bin/python3.11','-I','-B',b['paths']['source_root']+'/tools/run_c5_reuse_gpu_entry.py','--serve']
    parent={'pid':200,'uid':1000,'boot_id':plan['gpu_process']['boot_id'],'start_ticks':1,'executable_sha256':'a'*64,
            'argv_sha256':hashlib.sha256(b'\0'.join(s.encode() for s in argv)+b'\0').hexdigest(),'cwd':b['paths']['source_root']}
    child={**parent,'pid':201,'start_ticks':2}
    def generate(prompt,stage):
        raw='{"tool":"create_box"}' if stage=='selector' else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'
        return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':raw_sha(prompt.encode()),'output_sha256':raw_sha(raw.encode())}
    with AdmissionRegistry(b,create=True) as registry:
        peer=GenerationPeer(b,registry,plans,Tokenizer(),generate,lambda _:contextlib.nullcontext(),lambda:None,lambda:None)
        supervisor.append('child_launch_intent',{'parent':parent,'worker_open_head_sha256':peer.journal.head,
                          'policy_sha256':sha(plan['gpu_process']['stop_policy']),'budget':budget.observation()})
        q={'target':child,'parent_pid':200,'policy_sha256':sha(plan['gpu_process']['stop_policy']),'model_loading_started':False}
        supervisor.append('owned_child_qualified',q)
        lifecycle.append('model_loading_intent',{'qualification_sha256':sha(q),'worker_open_head_sha256':peer.journal.head})
        lifecycle.append('model_loaded',{'qualification_sha256':sha(q),'training':False,'parse_repair':False})
        ready=readiness(b,sha(q),peer.journal.head)
        chunks=[frame(begin_for(b,sha(ready)))]
        for slot in ORDER:
            inner=request(STUDY,slot,plans[slot]['route'],0,plans[slot]['steps'][0],
                          {'unit':'Millimeters','objects':[],'groups':{}},
                          {'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64},b['runtime_sha256'],'new-'+slot)
            chunks.append(frame(envelope(b,inner)))
        chunks.append(frame({'kind':'reuse_worker_close','protocol':PROTOCOL,'scope_sha256':sha(common_scope(b))}))
        serve(peer,Pipe(chunks),sha(q),lambda:None,lambda:None,lifecycle.append)
        clock[0]=109;lifecycle.append('worker_budget_observation',budget.observation())
        supervisor.append('owned_stop_result',{'signal_attempts':0,'exit_observed':True,'gpu_release_verified':None,
                                              'status':'already_exited_no_signal'})
        clock[0]=110
        supervisor.append('supervisor_final_observation',{'child_wait_status':0,'child_exit_reaped':True,'budget':budget.observation(),
                             'physical_gpu_release_verified':None,'whole_field_pass':False})
        return {'supervisor':copy.deepcopy(supervisor.rows),'lifecycle':copy.deepcopy(lifecycle.rows),
                'worker':copy.deepcopy(peer.journal.records),'binding':b,'plan':plan,'resources':spec['resources'],
                'spec':spec,'runtime':runtime,'plan_raw':plan_raw,'supervisor_head':supervisor.head,
                'lifecycle_head':lifecycle.head,'worker_head':peer.journal.head,'plans':plans,'tokenizer':Tokenizer()}


def rechain(rows):
    previous=ZERO
    for i,row in enumerate(rows):
        row.update(seq=i,previous_sha256=previous)
        row['record_sha256']=sha({k:v for k,v in row.items() if k!='record_sha256'})
        previous=row['record_sha256']
    return previous


def test_complete_entry_records_are_not_whole_field_quality_or_human_approval(tmp_path):
    result=audit_gpu_entry(**bundle(tmp_path))
    assert result['complete_eight_slot_entry_records'] and result['original_order_recomputed']
    assert result['generation']['requests_complete']==8 and result['generation']['recorded_generation_attempts']==16
    assert result['recorded_signal_attempts']==0 and result['elapsed_wall_seconds']==10
    assert result['physical_gpu_release_independently_verified'] is None
    assert not result['human_readiness_or_approval_origin_independently_verified']
    assert not result['native_geometry_permission_cleanup_verified'] and not result['whole_field_pass']


@pytest.mark.parametrize('change',['parent','preload','signal_without_intent','budget_flag','reservation','ready_boolean',
                                  'loaded_training','close_head','wrong_scope','anchor','frozen_plan','extra_supervisor'])
def test_rehashed_entry_tampering_does_not_become_a_valid_field_record(tmp_path,change):
    b=bundle(tmp_path)
    if change=='parent':b['supervisor'][2]['payload']['parent_pid']=999
    elif change=='preload':b['supervisor'][2]['payload']['model_loading_started']=True
    elif change=='signal_without_intent':b['supervisor'][3]['payload']['signal_attempts']=1
    elif change=='budget_flag':
        b['supervisor'][-1]['payload']['budget']['elapsed_wall_seconds']=4000
    elif change=='reservation':b['supervisor'][-1]['payload']['budget']['reserved_wall_seconds']=4000
    elif change=='ready_boolean':b['lifecycle'][3]['payload']['ready']['model_requests_before_ready']=False
    elif change=='loaded_training':b['lifecycle'][2]['payload']['training']=True
    elif change=='close_head':b['lifecycle'][5]['payload']['receipt']['worker_final_head_sha256']='0'*64
    elif change=='wrong_scope':b['lifecycle'][4]['payload']['begin']['owner_readiness']['runtime_sha256']='0'*64
    elif change=='frozen_plan':b['plan']['gpu_process']['stop_policy']['signals_max']=2
    elif change=='extra_supervisor':b['supervisor'][3]['kind']='hidden_retry'
    b['supervisor_head']=rechain(b['supervisor']);b['lifecycle_head']=rechain(b['lifecycle'])
    if change=='anchor':b['supervisor_head']='0'*64
    with pytest.raises(ValueError):audit_gpu_entry(**b)


def test_missing_close_is_incomplete_and_cannot_supply_formal_admission(tmp_path):
    b=bundle(tmp_path);b['lifecycle'].pop(5);b['lifecycle_head']=rechain(b['lifecycle'])
    result=audit_gpu_entry(**b)
    assert not result['complete_eight_slot_entry_records'] and not result['whole_field_pass']
