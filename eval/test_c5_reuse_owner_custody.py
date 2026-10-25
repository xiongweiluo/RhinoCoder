"""Custody record/interactive boundary controls with synthetic CPU data only."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from eval.test_c5_reuse_field_preparation import binding
from training.c5_reuse_field_scope import common_scope
from training.c5_reuse_evidence import sha,canonical
from training.c5_reuse_worker_loop import readiness
from plugin.rhino_listener.c5_reuse_runtime_scope import read_bytes
from tools.run_c5_reuse_owner_custody import readiness_record,final_record,live_line,byte_receipts


def inputs(tmp_path):
    b=binding(tmp_path,endpoint='mac');gpu={**b,'endpoint':'gpu','paths':b['endpoints']['gpu']}
    host={'study_id':b['study_id'],'runtime_sha256':b['runtime_sha256'],'host_baseline_head_sha256':'c'*64,
        'generation_stages':0,'full_byte_closure_proven':False}
    worker=readiness(gpu,'a'*64,'b'*64);owner=readiness_record(b,host,worker)
    heads={'controller_head_sha256':'d'*64,'native_head_sha256':'e'*64,'mac_lifecycle_head_sha256':'f'*64}
    export={'binding':gpu,'worker_head':'a'*64}
    completed={'native_head_sha256':'e'*64,'worker_final_head_sha256':'a'*64,
        'whole_field_pass':False,'external_final_capture_required':True}
    terminal={'study_id':b['study_id'],'seal_sha256':'b'*64,'journal_head_sha256':'c'*64,
        'record_count':10,'blocked':False,'execution_authority':False}
    return b,host,worker,owner,completed,terminal,heads,export


def test_schema_joins_bound_statements_without_claiming_raw_audit_pass(tmp_path):
    b,h,w,o,c,t,heads,e=inputs(tmp_path)
    result=final_record(b,o,c,t,heads,e)
    assert set(result)=={'actor','study_id','instance_id','spec_sha256','runtime_sha256','controller_head_sha256',
        'native_head_sha256','gpu_export_sha256','host_seal_sha256','owner_readiness','captured_outside_producer',
        'private_custody_confirmed','mac_lifecycle_head_sha256'}
    assert result['gpu_export_sha256']==sha(e) and result['host_seal_sha256']==t['seal_sha256']
    assert 'status' not in result and 'whole_field_pass' not in result


@pytest.mark.parametrize('change',['host_runtime','host_generation','host_bool','worker_scope','worker_generation',
    'terminal_blocked','terminal_study','terminal_authority','native_head','worker_head','old_export',
    'producer_actor','missing_confirmation','pretend_pass','extra_head'])
def test_wrong_or_uncertain_actual_output_cannot_become_owner_custody(tmp_path,change):
    b,h,w,o,c,t,heads,e=inputs(tmp_path)
    if change=='host_runtime':h['runtime_sha256']='0'*64
    elif change=='host_generation':h['generation_stages']=1
    elif change=='host_bool':h['generation_stages']=False
    elif change=='worker_scope':w['scope_sha256']='0'*64
    elif change=='worker_generation':w['generation_stages_before_ready']=1
    elif change=='terminal_blocked':t['blocked']=True
    elif change=='terminal_study':t['study_id']='retired'
    elif change=='terminal_authority':t['execution_authority']=True
    elif change=='native_head':c['native_head_sha256']='0'*64
    elif change=='worker_head':c['worker_final_head_sha256']='0'*64
    elif change=='old_export':e['binding']['study_id']='C5DEV-REUSE-20261011-A'
    elif change=='producer_actor':o['actor']='agent'
    elif change=='missing_confirmation':o['captured_after_host_baseline']=False
    elif change=='pretend_pass':c['whole_field_pass']=True
    else:heads['extra']='0'*64
    with pytest.raises((ValueError,KeyError)):
        if change.startswith(('host_','worker_scope','worker_generation')):readiness_record(b,h,w)
        else:final_record(b,o,c,t,heads,e)


def test_live_log_waits_for_complete_line_and_handles_empty_file_readonly(tmp_path):
    p=tmp_path/'controller-output.log';p.touch(mode=0o600);clock=[0.];calls=[]
    prefix=b'C5_REUSE_EXTERNAL_READINESS_REQUIRED ';value={'cpu_synthetic':True}
    def sleep(seconds):
        clock[0]+=seconds
        p.write_bytes(prefix+(b'{' if clock[0]<.15 else canonical(value)+b'\n'))
    result=live_line(p,prefix,read_bytes,lambda:calls.append('guard'),seconds=1,
                     clock=lambda:clock[0],sleep=sleep)
    assert result==value and calls==['guard','guard']


@pytest.mark.parametrize('change',['duplicate','partial_timeout','public_log','alias'])
def test_ambiguous_or_untrusted_log_cannot_create_a_readiness_record(tmp_path,change):
    p=tmp_path/'controller-output.log';prefix=b'READY ';p.write_bytes(prefix+b'{}\n');p.chmod(0o600);clock=[0.]
    if change=='duplicate':p.write_bytes((prefix+b'{}\n')*2)
    elif change=='partial_timeout':p.write_bytes(prefix+b'{')
    elif change=='public_log':p.chmod(0o644)
    else:
        target=tmp_path/'saved';p.rename(target);p.symlink_to(target)
    def sleep(seconds):clock[0]+=seconds
    with pytest.raises(ValueError):live_line(p,prefix,read_bytes,lambda:None,seconds=.2,
        clock=lambda:clock[0],sleep=sleep)


def test_noninteractive_producer_refuses_before_fixed_scope_or_files(tmp_path):
    root=Path(__file__).resolve().parents[1]
    r=subprocess.run([sys.executable,'-I','-S','-B',str(root/'tools/run_c5_reuse_owner_custody.py'),'--ready'],
        stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=10,cwd=tmp_path)
    assert r.returncode!=0 and 'owner private interactive terminal required' in r.stderr
    assert list(tmp_path.iterdir())==[]


@pytest.mark.parametrize('change',['valid','missing_endpoint','wrong_spec','wrong_runtime','wrong_inventory','unverified_asset','unverified_source'])
def test_actual_byte_receipts_are_bound_to_complete_freeze(tmp_path,change):
    b,*_=inputs(tmp_path);runtime={'source_files':{'training/c5_contract.py':'a'*64}}
    one={'spec_sha256':b['spec_sha256'],'runtime_sha256':b['runtime_sha256'],
        'source_inventory_sha256':sha(runtime['source_files']),'actual_source_bytes_verified':True,
        'actual_installed_asset_bytes_verified':True}
    receipts={'mac':copy.deepcopy(one),'gpu':copy.deepcopy(one)}
    if change=='missing_endpoint':receipts.pop('gpu')
    elif change=='wrong_spec':receipts['gpu']['spec_sha256']='0'*64
    elif change=='wrong_runtime':receipts['gpu']['runtime_sha256']='0'*64
    elif change=='wrong_inventory':receipts['gpu']['source_inventory_sha256']='0'*64
    elif change=='unverified_asset':receipts['gpu']['actual_installed_asset_bytes_verified']=False
    elif change=='unverified_source':receipts['mac']['actual_source_bytes_verified']=False
    if change=='valid':assert byte_receipts(receipts,b,runtime)==receipts
    else:
        with pytest.raises(ValueError):byte_receipts(receipts,b,runtime)
