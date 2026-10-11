"""New-entry negative controls; public CPU fixtures, never actual GPU/Rhino."""
import copy
import contextlib
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from eval.test_c5_reuse_field_preparation import records,binding,peer
from eval.test_c5_reuse_entry_guards import ChildOps
from training.c5_reuse_evidence import sha,canonical
from training.c5_reuse_field_scope import bind,PROTOCOL,STUDY,common_scope
from training.c5_reuse_owned_child import OwnedChildStop,POLICY
from training.c5_reuse_process_identity import LinuxIdentity,stable_file_sha
from training.c5_reuse_control_journal import ControlJournal,read_control
from training.c5_reuse_gpu_supervisor import Watchdog,PACKET
from training.c5_reuse_gpu_loader import validate_plan,MANIFEST_SHA,SNAPSHOT,ADAPTER,ADAPTER_FILES,PYTHON,ENTRY,LOADER_POLICY
from training.c5_reuse_worker_loop import validate_begin,receive,send,serve
from training.c5_reuse_field_wire import frame
from training.c5_reuse_development_plan import ORDER
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_field_journal import FieldJournal
from training.c5_reuse_generation import GenerationPeer
from training.c5_reuse_ssh import POLICY as SSH_POLICY,command,validate_transport,validate_ready,FieldSSHSession


def plan_records(tmp_path):
    spec,runtime,approval,plans=records(tmp_path)
    acceptance={'instance_id':spec['instance_id']}
    plan={'protocol':PROTOCOL,'study_id':STUDY,'instance_id':spec['instance_id'],
          'environment':{'mac':{'cpu_fixture':True},'gpu':{'cpu_fixture':True,'executable_sha256':'a'*64}},
          'model_assets':{'manifest_raw_sha256':MANIFEST_SHA,'snapshot_dir':str(SNAPSHOT),
              'base_files':{'file-%02d'%i:'a'*64 for i in range(14)},'adapter_root':str(ADAPTER),'adapter_files':ADAPTER_FILES.copy()},
          'host_readable_files':{'cpu_fixture':'a'*64},'gpu_process':{'python':str(PYTHON),'entry':ENTRY,
              'boot_id':'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','uid':1000,
              'gpu_uuid':'GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','stop_policy':copy.deepcopy(POLICY)},
          'loader_policy':copy.deepcopy(LOADER_POLICY),'transport':{'policy':copy.deepcopy(SSH_POLICY),
              'ssh_executable_sha256':'a'*64},'host_acceptance':acceptance,
          'resource_basis':{'platform_hour_quota':None,
              'remaining_gpu_seconds_meaning':'research_reservation_within_original_cap_not_platform_balance',
              'prior_cumulative_upper_bound_basis':'explicit CPU fixture, no actual resource fact'}}
    spec['host_policy']['acceptance_record_sha256']=sha(acceptance)
    runtime['host_policy']=copy.deepcopy(spec['host_policy']);runtime['spec_sha256']=sha(spec)
    for key,section in [('environment_sha256','environment'),('model_assets_sha256','model_assets'),
                        ('host_readable_files_sha256','host_readable_files')]:runtime[key]=sha(plan[section])
    approval.update(spec_sha256=sha(spec),runtime_sha256=sha(runtime))
    return spec,runtime,plan,approval


@pytest.mark.parametrize('change',['valid','adapter','snapshot','base_size','base_path','policy','loader','uid',
                                  'env_hash','host_hash','acceptance','quota','resource_meaning','prior_basis'])
def test_new_environment_plan_cannot_rebind_original_model_or_stop_policy(tmp_path,change):
    spec,runtime,plan,_=plan_records(tmp_path)
    if change=='adapter':plan['model_assets']['adapter_files']['adapter_config.json']='0'*64
    elif change=='snapshot':plan['model_assets']['snapshot_dir']='/data/other'
    elif change=='base_size':plan['model_assets']['base_files'].pop('file-00')
    elif change=='base_path':plan['model_assets']['base_files']['../hidden']='a'*64;plan['model_assets']['base_files'].pop('file-00')
    elif change=='policy':plan['gpu_process']['stop_policy']['signals_max']=2
    elif change=='loader':plan['loader_policy']['training']=True
    elif change=='uid':plan['gpu_process']['uid']=True
    elif change=='env_hash':plan['environment']['gpu']['extra']=1
    elif change=='host_hash':plan['host_readable_files']['other']='b'*64
    elif change=='acceptance':plan['host_acceptance']['instance_id']='retired'
    elif change=='quota':plan['resource_basis']['platform_hour_quota']=100
    elif change=='resource_meaning':plan['resource_basis']['remaining_gpu_seconds_meaning']='platform_balance'
    elif change=='prior_basis':plan['resource_basis']['prior_cumulative_upper_bound_basis']=''
    if change not in ('env_hash','host_hash','acceptance'):
        runtime['model_assets_sha256']=sha(plan['model_assets'])
    if change=='valid':validate_plan(spec,runtime,plan)
    else:
        with pytest.raises((ValueError,KeyError)):validate_plan(spec,runtime,plan)


def test_generation_cutoff_blocks_loading_but_not_exact_cleanup_binding(tmp_path):
    spec,runtime,approval,_=records(tmp_path)
    with pytest.raises(ValueError,match='resource_boundary'):bind(spec,runtime,approval,now=9001,endpoint='gpu')
    result=bind(spec,runtime,approval,now=9001,endpoint='gpu',cleanup_only=True)
    assert not result['whole_field_authority_verified']
    approval['runtime_sha256']='0'*64
    with pytest.raises(ValueError):bind(spec,runtime,approval,now=9001,endpoint='gpu',cleanup_only=True)


@pytest.mark.parametrize('now',[float('inf'),float('nan'),True])
def test_cleanup_does_not_relax_finite_clock_or_numeric_type(tmp_path,now):
    spec,runtime,approval,_=records(tmp_path)
    with pytest.raises(ValueError):bind(spec,runtime,approval,now=now,endpoint='gpu',cleanup_only=True)


def proc_fixture(tmp_path):
    root=tmp_path/'proc';p=root/'123';p.mkdir(parents=True)
    boot=root/'sys/kernel/random/boot_id';boot.parent.mkdir(parents=True);boot.write_text('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\n')
    executable=tmp_path/'python';executable.write_bytes(b'CPU executable fixture');executable.chmod(0o600)
    (p/'exe').symlink_to(executable);(p/'cwd').symlink_to(tmp_path)
    # Process comm can contain spaces/parentheses; starttime is stat field 22.
    (p/'stat').write_text('123 (fixture ) worker) '+' '.join(['S','200']+['0']*17+['456'])+'\n')
    (p/'cmdline').write_bytes(b'python\0-I\0-B\0entry.py\0--serve\0')
    return LinuxIdentity(root),p,executable


@pytest.mark.parametrize('change',['valid','zombie','boot','pid','argv','fifo','exe_link','exe_hardlink'])
def test_proc_identity_is_one_exact_target_and_rejects_ambiguous_or_changed_inputs(tmp_path,change):
    reader,p,executable=proc_fixture(tmp_path)
    if change=='zombie':(p/'stat').write_text((p/'stat').read_text().replace(' S ',' Z '))
    elif change=='boot':(reader.root/'sys/kernel/random/boot_id').write_text('not-a-boot')
    elif change=='pid':(p/'stat').write_text((p/'stat').read_text().replace('123 (','124 ('))
    elif change=='argv':(p/'cmdline').write_bytes(b'no terminator')
    elif change=='fifo':(p/'cmdline').unlink();os.mkfifo(p/'cmdline',0o600)
    elif change=='exe_link':
        alias=tmp_path/'alias';alias.symlink_to(executable)
        with pytest.raises(ValueError):stable_file_sha(alias)
        return
    elif change=='exe_hardlink':os.link(executable,tmp_path/'alias')
    if change=='valid':
        value=reader(123);assert value['start_ticks']==456 and reader.parent(123)==200
        assert value['argv_sha256']==hashlib.sha256((p/'cmdline').read_bytes()).hexdigest()
    else:
        with pytest.raises((ValueError,OSError)):reader(123)


@pytest.mark.parametrize('change',['valid','before_ready','duplicate_ready','return_first','duplicate_start','old_time',
                                  'future_time','expired','clock_back','unknown','stage_cap','fragmented'])
def test_watchdog_independently_covers_load_and_generation_deadlines(change):
    clock=[100.0];w=Watchdog(100,3600,clock=lambda:clock[0])
    def feed(k,t=None):w.feed(PACKET.pack(k,clock[0] if t is None else t))
    if change=='before_ready': action=lambda:feed(b'S')
    elif change=='return_first':feed(b'L');action=lambda:feed(b'E')
    elif change=='old_time':action=lambda:feed(b'L',98)
    elif change=='future_time':action=lambda:feed(b'L',101)
    elif change=='expired':clock[0]=280;action=w.check
    elif change=='clock_back':clock[0]=99;action=w.check
    elif change=='unknown':action=lambda:feed(b'?')
    elif change=='duplicate_ready':feed(b'L');action=lambda:feed(b'L')
    elif change=='duplicate_start':feed(b'L');feed(b'R');feed(b'S');action=lambda:feed(b'S')
    elif change=='stage_cap':feed(b'L');feed(b'R');w.stages=112;action=lambda:feed(b'S')
    elif change=='fragmented':
        raw=PACKET.pack(b'L',100)
        w.feed(raw[:2]);assert not w.ready
        clock[0]=100.1;w.feed(raw[2:]);assert w.ready
        clock[0]=100.2;feed(b'R',100.15);feed(b'S',100.16);assert w.pending and w.deadline==280.15
        return
    else:
        feed(b'L');clock[0]=110;feed(b'R');feed(b'S');clock[0]=111;feed(b'E');feed(b'D')
        assert w.ready and not w.pending and w.stages==1 and w.deadline==291;return
    with pytest.raises(ValueError):action()


@pytest.mark.parametrize('change',['two_stages_one_deadline','duplicate_request','end_before_request','nine_requests','late_progress'])
def test_watchdog_cannot_reset_whole_request_deadline_between_selector_and_invoker(change):
    clock=[100.0];w=Watchdog(100,3600,clock=lambda:clock[0])
    def feed(kind):w.feed(PACKET.pack(kind,clock[0]))
    feed(b'L')
    if change=='end_before_request':
        with pytest.raises(ValueError):feed(b'D')
        return
    feed(b'R')
    if change=='duplicate_request':
        with pytest.raises(ValueError):feed(b'R')
        return
    if change=='nine_requests':
        for _ in range(7):feed(b'D');feed(b'R')
        feed(b'D')
        with pytest.raises(ValueError):feed(b'R')
        return
    feed(b'S');clock[0]=200;feed(b'E');feed(b'S')
    assert w.deadline==280
    if change=='late_progress':
        clock[0]=279;w.feed(PACKET.pack(b'E',210));assert w.deadline==280
    clock[0]=280
    with pytest.raises(ValueError):w.check()


@pytest.mark.parametrize('change',['valid','tamper','population','anchor','reopen'])
def test_control_records_are_durable_bound_and_not_reopenable(tmp_path,change):
    b=binding(tmp_path);Path(b['paths']['state_root']).mkdir(mode=0o700)
    journal=ControlJournal(b,'supervisor');journal.append('cpu_observation',{'actual_field_effects':0})
    if change=='reopen':
        with pytest.raises(FileExistsError):ControlJournal(b,'supervisor')
        return
    if change=='tamper':
        p=journal.root/'raw-0001.json';raw=p.read_bytes();p.write_bytes(raw.replace(b'cpu_observation',b'cpu_replaced'))
    elif change=='population':(journal.root/'extra').write_text('CPU fixture')
    head='0'*64 if change=='anchor' else journal.head
    if change=='valid':assert read_control(journal.root,b,'supervisor',head=head)==journal.rows
    else:
        with pytest.raises(ValueError):read_control(journal.root,b,'supervisor',head=head)


def test_supervised_peer_adopts_only_single_original_durable_worker_open(tmp_path):
    from eval.test_c5_model_transport import Tokenizer
    b=binding(tmp_path);plans=records(tmp_path)[3];Path(b['paths']['state_root']).mkdir(mode=0o700)
    with AdmissionRegistry(b,create=True) as registry:
        journal=FieldJournal(b,'worker',registry)
        clone=GenerationPeer(b,registry,plans,Tokenizer(),lambda *_:None,lambda _:contextlib.nullcontext(),
                             lambda:None,lambda:None,journal=journal)
        assert clone.journal is journal
        # Even before a first request, an existing in-memory journal cannot
        # acquire a second peer whose independent spent set could regenerate.
        with pytest.raises(ValueError,match='owner_already_attached'):
            GenerationPeer(b,registry,plans,Tokenizer(),lambda *_:None,lambda _:contextlib.nullcontext(),
                           lambda:None,lambda:None,journal=journal)


def test_controller_journal_cannot_be_adopted_twice_before_first_send(tmp_path):
    from training.c5_reuse_field_transport import FieldModelChannel
    b=binding(tmp_path,endpoint='mac');plans=records(tmp_path)[3];Path(b['paths']['state_root']).mkdir(mode=0o700)
    with AdmissionRegistry(b,create=True) as registry:
        journal=FieldJournal(b,'controller',registry)
        FieldModelChannel(b,registry,None,lambda:None,lambda:None,plans,journal=journal)
        with pytest.raises(ValueError,match='owner_already_attached'):
            FieldModelChannel(b,registry,None,lambda:None,lambda:None,plans,journal=journal)


def begin_for(b,ready='a'*64):
    return {'kind':'reuse_begin_after_external_readiness','protocol':PROTOCOL,'scope_sha256':sha(common_scope(b)),
        'owner_readiness':{'study_id':STUDY,'instance_id':b['instance_id'],'spec_sha256':b['spec_sha256'],
        'runtime_sha256':b['runtime_sha256'],'host_baseline_head_sha256':'b'*64,'worker_readiness_sha256':ready,
        'actor':'repository_owner','captured_after_host_baseline':True,'approved_generation_start':True}}


@pytest.mark.parametrize('change',['valid','no_baseline','wrong_actor','old_runtime','no_start','extra'])
def test_worker_begin_requires_exact_external_readiness_record_but_not_origin_claim(tmp_path,change):
    b=binding(tmp_path);value=begin_for(b)
    if change=='no_baseline':value['owner_readiness']['captured_after_host_baseline']=False
    elif change=='wrong_actor':value['owner_readiness']['actor']='agent'
    elif change=='old_runtime':value['owner_readiness']['runtime_sha256']='0'*64
    elif change=='no_start':value['owner_readiness']['approved_generation_start']=False
    elif change=='extra':value['owner_readiness']['all_pass']=True
    if change=='valid':assert validate_begin(value,b)['actor']=='repository_owner'
    else:
        with pytest.raises(ValueError):validate_begin(value,b)


class Pipe:
    def __init__(self,chunks):self.chunks=list(chunks);self.sent=b''
    def read(self,deadline):return self.chunks.pop(0) if self.chunks else b''
    def write(self,remaining,deadline):n=min(3,len(remaining));self.sent+=remaining[:n];return n


@pytest.mark.parametrize('change',['valid','partial','eof','extra','duplicate_key','oversize'])
def test_actual_worker_frame_boundary_has_no_prefix_resend_or_eof_success(change):
    raw=frame({'cpu_fixture':True})
    chunks=[raw] if change!='partial' else [raw[:3],raw[3:]]
    if change=='eof':chunks=[raw[:3],b'']
    elif change=='extra':chunks=[raw+raw]
    elif change=='duplicate_key':chunks=[b'{"a":1,"a":2}\n']
    elif change=='oversize':chunks=[b'x'*32769]
    pipe=Pipe(chunks)
    if change in ('valid','partial'):
        assert receive(pipe,180,lambda:None)=={'cpu_fixture':True}
        send(pipe,{'cpu_fixture':True},180,lambda:None);assert pipe.sent==raw
    else:
        with pytest.raises(ValueError):receive(pipe,180,lambda:None)


@pytest.mark.parametrize('change',['complete','wrong_order','missing_close','wrong_ready'])
def test_eight_slot_loop_is_exactly_once_and_requires_external_ready_and_explicit_close(tmp_path,change):
    from training.c5_reuse_development_plan import public_plan
    from training.c5_reuse_worker_loop import readiness
    from training.c5_reuse_generation_audit import audit_generation
    from training.c5_model_transport import request
    from training.c5_reuse_field_wire import envelope
    from eval.test_c5_model_transport import Tokenizer
    plans=public_plan(Path(__file__).resolve().parents[1])['task_plans']
    b=binding(tmp_path,plans=plans);Path(b['paths']['state_root']).mkdir(mode=0o700)
    calls=[]
    def generate(prompt,stage):
        calls.append(stage)
        # Valid but deliberately inappropriate box output for several tasks;
        # the worker preserves this, never repairs it or advertises quality.
        raw='{"tool":"create_box"}' if stage=='selector' else '{"name":"create_box","arguments":{"width":2,"depth":3,"height":4}}'
        return {'raw':raw,'tokens':10,'seconds':0.01,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                'output_sha256':hashlib.sha256(raw.encode()).hexdigest()}
    with AdmissionRegistry(b,create=True) as registry:
        peer=GenerationPeer(b,registry,plans,Tokenizer(),generate,lambda _:contextlib.nullcontext(),lambda:None,lambda:None)
        ready=readiness(b,'c'*64,peer.journal.head)
        begin=begin_for(b,sha(ready))
        if change=='wrong_ready':begin['owner_readiness']['worker_readiness_sha256']='0'*64
        order=list(ORDER)
        if change=='wrong_order':order[:2]=list(reversed(order[:2]))
        requests=[envelope(b,request(STUDY,slot,plans[slot]['route'],0,plans[slot]['steps'][0],
            {'unit':'Millimeters','objects':[],'groups':{}},
            {'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64},b['runtime_sha256'],'request-'+slot)) for slot in order]
        close={'kind':'reuse_worker_close','protocol':PROTOCOL,'scope_sha256':sha(common_scope(b))}
        chunks=[frame(begin)]+[frame(s) for s in requests]+([] if change=='missing_close' else [frame(close)])
        pipe=Pipe(chunks);events=[]
        if change=='complete':
            result=serve(peer,pipe,'c'*64,lambda:None,lambda:None,lambda k,v:events.append((k,v)))
            assert result['requests']==8 and result['generation_intents']==16 and not result['whole_field_pass']
            audit=audit_generation(peer.journal.records,b,peer.journal.head,plans=plans,tokenizer=Tokenizer())
            assert audit['coverage_complete'] and audit['requests_complete']==8
            assert events[1][1]['human_provenance_independently_verified'] is False
        else:
            with pytest.raises(ValueError):serve(peer,pipe,'c'*64,lambda:None,lambda:None,lambda k,v:events.append((k,v)))
            assert len(peer.spent)==(8 if change=='missing_close' else 0)


@pytest.mark.parametrize('change',['valid','bad_policy','drift','wrong_parent'])
def test_independent_stop_rechecks_original_qualification_without_claiming_preload_now(tmp_path,change):
    b=binding(tmp_path);identity={'pid':100,'uid':1000,'boot_id':'a'*36,'start_ticks':10,
        'executable_sha256':'a'*64,'argv_sha256':'b'*64,'cwd':b['paths']['source_root']}
    q={'target':identity,'parent_pid':200,'policy_sha256':sha(POLICY),'model_loading_started':False}
    ops=ChildOps(identity,parent=999 if change=='wrong_parent' else 200);events=[]
    if change=='bad_policy':q['model_loading_started']=True
    elif change=='drift':ops.drift=True
    with AdmissionRegistry(b,create=True) as registry:
        if change=='valid':
            owned=OwnedChildStop.recheck_qualified(b,q,ops,lambda k,v:events.append((k,v)),registry)
            try:
                assert events[0][0]=='owned_stop_qualification_rechecked'
                assert owned.stop()['signal_attempts']==1
            finally:owned.close()
        else:
            with pytest.raises(ValueError):OwnedChildStop.recheck_qualified(b,q,ops,lambda k,v:events.append((k,v)),registry)
            assert 'send' not in ops.calls


@pytest.mark.parametrize('mode',['--serve','--stop'])
def test_repository_checkout_entry_cannot_launch_or_stop_without_fixed_deployment(mode):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-I','-B',str(root/ENTRY),mode],capture_output=True,text=True,timeout=10)
    assert result.returncode!=0 and 'reuse_fixed_entry_root' in result.stderr


@pytest.mark.parametrize('change',['valid','port','host','reconnect','shell','entry','binary'])
def test_ssh_transport_pin_rejects_path_endpoint_and_connection_fallback(change):
    policy={'policy':copy.deepcopy(SSH_POLICY),'ssh_executable_sha256':'a'*64}
    if change=='port':policy['policy']['port']=22159
    elif change=='host':policy['policy']['host']='other-host'
    elif change=='reconnect':policy['policy']['automatic_reconnect']=True
    elif change=='shell':policy['policy']['local_shell']=True
    elif change=='entry':policy['policy']['remote_entry']='tools/run_c5_hostassurance_dev_worker_d.py'
    elif change=='binary':policy['ssh_executable_sha256']='not-hash'
    if change=='valid':
        validate_transport(policy)
        for mode in ('serve','stop','check'):
            args=command(mode)
            assert 'ProxyCommand=/usr/bin/false' in args and 'ControlMaster=no' in args
            assert args[args.index('-p')+1]=='24151'
            assert '-F' in args and args[args.index('-F')+1]=='/dev/null'
        assert command('serve')[-1].endswith('run_c5_reuse_gpu_entry.py --serve')
        with pytest.raises(ValueError):command('arbitrary')
    else:
        with pytest.raises(ValueError):validate_transport(policy)


def test_ssh_wrong_scope_fails_before_any_process_or_admission(tmp_path,monkeypatch):
    b=binding(tmp_path,endpoint='mac');calls=[]
    monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:calls.append((a,k)))
    with pytest.raises(ValueError,match='exact_endpoint_roots'):
        FieldSSHSession(b,None,{}, {'policy':copy.deepcopy(SSH_POLICY),'ssh_executable_sha256':'a'*64},lambda:None,lambda:None)
    assert calls==[] and not Path(b['paths']['state_root']).exists()


@pytest.mark.skipif(sys.platform!='linux' or not hasattr(os,'pidfd_open'),reason='Linux owned-child CPU isolation only')
@pytest.mark.parametrize('kind',['exit','timeout'])
def test_real_cpu_owned_child_is_qualified_before_permit_and_watchdog_never_escalates(tmp_path,monkeypatch,kind):
    import training.c5_reuse_gpu_loader as loader
    import training.c5_reuse_gpu_supervisor as supervisor
    spec,runtime,approval,plans=records(tmp_path)
    spec['resources']['lease_expiry_epoch']=int(time.time())+10000
    spec['resources']['generation_cutoff_epoch']=int(time.time())+9000
    runtime['resources']=copy.deepcopy(spec['resources']);runtime['spec_sha256']=sha(spec)
    approval.update(spec_sha256=sha(spec),runtime_sha256=sha(runtime))
    b=bind(spec,runtime,approval,now=time.time(),endpoint='gpu')
    (tmp_path/'gpu').mkdir();Path(b['paths']['state_root']).mkdir(mode=0o700)
    with AdmissionRegistry(b,create=True):pass
    monkeypatch.setattr(loader,'validate_plan',lambda *_:None)
    monkeypatch.setattr(loader,'verify_entry_process',lambda b,p,r:r(os.getpid()))
    monkeypatch.setattr(loader,'preflight',lambda *_:{})
    monkeypatch.setattr('training.c5_reuse_development_plan.public_plan',lambda _: {'task_plans':plans})
    def child(b,plans,journal,registry,gate,progress_fd,qualification,inventory,guard,budget,runtime,plan):
        assert os.read(gate,2)==b'G';os.close(gate)
        supervisor.progress(progress_fd,b'L')
        if kind=='timeout':time.sleep(10)
    monkeypatch.setattr(supervisor,'child_main',child)
    if kind=='timeout':
        original=supervisor.Watchdog
        monkeypatch.setattr(supervisor,'Watchdog',lambda start,cap:original(start,0.25))
        with pytest.raises(ValueError,match='watchdog_deadline'):
            supervisor.supervise(spec,runtime,b,{},lambda **_:None)
    else:
        result=supervisor.supervise(spec,runtime,b,{},lambda **_:None)
        assert result['child_exit_success'] and not result['whole_field_pass']
    rows=read_control(Path(b['paths']['state_root'])/'supervisor',b,'supervisor')
    kinds=[r['kind'] for r in rows]
    assert kinds.index('child_launch_intent')<kinds.index('owned_child_qualified')<kinds.index('owned_stop_result')
    stopped=[r['payload'] for r in rows if r['kind']=='owned_stop_result'][0]
    assert stopped['signal_attempts']==(1 if kind=='timeout' else 0) and stopped['exit_observed']
    assert stopped['gpu_release_verified'] is None
