"""Public CPU fixtures only. No new final questions, model, GPU or Rhino.

The repeated synthetic cases are deliberately not independent research data;
all of this file and derivatives belong to development exclusions.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from eval.test_c5_formal20_preparation import cases20
from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import NativeError, digest
from plugin.rhino_listener.lora_final_admission import admit, approval_record, validate_runtime
from tools.build_lora_final_package import build, ROOT
from training.lora_final_custody import seal, CATEGORIES, FLAGS
from training.lora_development_authority import WorkBudget, validate_package


def synthetic():
    originals=cases20(); rows=[]
    for layer,n in build()['comparison_plan']['strata'].items():
        examples=[r for r in originals if r['stratum']==layer]
        for i in range(n):
            row=copy.deepcopy(examples[i%len(examples)])
            label='cpu-only-'+layer+'-'+str(i)
            row.update(family_id=label,template_family=label,
                task_text='CPU synthetic excluded fixture '+''.join(chr(97+b%26) for b in hashlib.sha256(label.encode()).digest()))
            rows.append(row)
    exclusions={k:[{'task_text':'excluded historical CPU toy '+k} for _ in range(build()['exclusion_reference']['minimum_counts'][k])] for k in CATEGORIES}
    attestation={k:True for k in FLAGS}
    attestation.update(actor='repository_owner',sealed_at_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
    return rows,exclusions,{'sha256':'a'*64,'bytes':123,'format':'age-x25519'},attestation


def toy_spec():
    from tools.c5_rhino_formal20_owner_exclusion import _merkle_root
    spec=build()
    spec['exclusion_reference']['original80_merkle_root']=_merkle_root(synthetic()[1]['original80'])
    return spec


def test_owner_seal_binds_every_private_view_without_exporting_content():
    spec=toy_spec(); cases,exclusions,encrypted,attestation=synthetic()
    package,receipt=seal(spec,cases,exclusions,encrypted,attestation)
    assert validate_runtime(spec,receipt,package)==package
    public=json.dumps(receipt)
    for case in cases:
        assert case['task_text'] not in public and case['family_id'] not in public
    assert 'expected_operations' not in json.dumps(package)
    assert 'final_assertions' not in json.dumps(package)
    assert receipt['execution_authorized'] is False
    assert len(package['compiled']['views']['schedule'])==80
    with pytest.raises((ValueError,NativeError)): validate_package(package)


@pytest.mark.parametrize('fault',['task','score','order','choices','source'])
def test_any_sealed_runtime_change_is_rejected(fault):
    spec=toy_spec(); package,receipt=seal(spec,*synthetic())
    if fault=='task': package['compiled']['views']['model']['common-000']['task']+=' changed'
    if fault=='score': package['compiled']['cases_sha256']='f'*64
    if fault=='order': package['compiled']['views']['schedule'].reverse()
    if fault=='choices': package['choices_sha256']='f'*64
    if fault=='source': package['source_files']={}
    with pytest.raises(NativeError): validate_runtime(spec,receipt,package)


@pytest.mark.parametrize('fault',['overlap','later_step','category_missing','unconfirmed','numeric_reuse'])
def test_custody_refuses_incomplete_or_contaminated_seals(fault):
    cases,exclusions,encrypted,attestation=synthetic()
    if fault=='overlap': exclusions['original20']=[cases[0]]
    if fault=='later_step': exclusions['original80']=[{'records':[{'user_step':'a distinct earlier toy'}, {'user_step':cases[0]['task_text']}]}]
    if fault=='category_missing': del exclusions['a5_p2']
    if fault=='unconfirmed': attestation[FLAGS[0]]=False
    if fault=='numeric_reuse': cases[1]['task_text']=cases[0]['task_text']+' 7'
    with pytest.raises((ValueError,NativeError,RuntimeError)): seal(toy_spec(),cases,exclusions,encrypted,attestation)


@pytest.mark.parametrize('arguments', [[], ['--check-cases']])
def test_public_owner_entry_refuses_noninteractive_before_any_private_prompt(arguments):
    result=subprocess.run([sys.executable,str(ROOT/'tools/seal_lora_final_owner.py'),*arguments],input='',text=True,capture_output=True,timeout=10)
    assert result.returncode==2 and result.stdout.strip()=='owner_interactive_terminal_required' and not result.stderr


def test_owner_case_check_reuses_contract_without_sealing_or_echoing_cases():
    from training.lora_final_case_check import check_cases
    cases=synthetic()[0]; before=copy.deepcopy(cases)
    report=check_cases(build(),cases)
    assert report['status']=='case_structure_passed_not_sealed' and not report['sealed']
    assert cases==before and not report['execution_authorized']
    assert not report['geometry_correctness_verified'] and not report['independence_verified']
    assert all(c['family_id'] not in json.dumps(report) and c['task_text'] not in json.dumps(report) for c in cases)
    cases[0]['max_steps']=3
    report=check_cases(build(),cases)
    assert report['errors']==[{'row':1,'code':'dispatch_or_step_budget_differs_from_expected_sequence'}]


@pytest.mark.parametrize('fault', ['count','strata','reuse','unhashable','blank','exception'])
def test_owner_case_check_never_repairs_input_or_prints_unknown_private_exception(fault,monkeypatch):
    import training.lora_final_case_check as check
    cases=synthetic()[0]
    if fault=='count': cases.pop()
    if fault=='strata': cases[12]['stratum']='error_recovery'
    if fault=='reuse': cases[1]['family_id']=cases[0]['family_id']
    if fault=='unhashable': cases[0]['expected_operations'][0]['name']={'private-secret':'private-value'}
    if fault=='blank': cases[0]=json.loads((ROOT/'eval/lora-development/final-case-blank-template.json').read_text())
    if fault=='exception':
        def fail(case): raise ValueError('private-secret private-value')
        monkeypatch.setattr(check,'validate_case',fail)
    before=copy.deepcopy(cases)
    report=check.check_cases(build(),cases)
    assert report['status']=='needs_correction' and report['errors'] and cases==before
    assert 'private-secret' not in json.dumps(report) and 'private-value' not in json.dumps(report)


def test_new_lease_binding_keeps_research_choices_and_historical_freeze():
    old=json.loads((ROOT/'eval/lora-development/final-public-spec-20261027.json').read_text())
    new=build()
    assert old['lease_end_epoch']==int(datetime(2026,10,30,19,tzinfo=timezone.utc).timestamp())
    assert new['lease_end_epoch']==int(datetime(2026,11,4,19,tzinfo=timezone.utc).timestamp())
    for key in ('choices','choices_sha256','comparison_plan','limits','assets','model_identities','loader_policy'):
        assert new[key]==old[key]
    assert new['resource_policy']['extension_cost'] is None
    assert not new['execution_authorized']


def test_owner_interactive_case_check_reads_only_cases_and_writes_nothing(tmp_path,monkeypatch,capsys):
    import tools.seal_lora_final_owner as owner
    import tools.c5_rhino_formal20_owner_exclusion as private
    import plugin.rhino_listener.lora_development_admission as development
    root=tmp_path/'public'; root.mkdir()
    (root/'lora-final-spec.json').write_text(json.dumps(build()))
    path=tmp_path/'private-synthetic-cases.json'
    path.write_text(json.dumps(synthetic()[0]))
    monkeypatch.setattr(owner,'ROOT',root)
    monkeypatch.setattr(owner.sys,'argv',['owner','--check-cases'])
    monkeypatch.setattr(owner.sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(owner.sys.stdout,'isatty',lambda:True)
    monkeypatch.setattr(private,'_worktrees',lambda **kwargs:[ROOT])
    monkeypatch.setattr(development,'source_guard',lambda *args:None)
    prompts=[]
    def prompt(label): prompts.append(label); return str(path)
    monkeypatch.setattr(owner.getpass,'getpass',prompt)
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert owner.main()==0 and len(prompts)==1
    output=capsys.readouterr()
    assert json.loads(output.out)['status']=='case_structure_passed_not_sealed' and not output.err
    assert str(path) not in output.out
    assert before=={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_real_historical_inventory_cannot_be_replaced_by_toy_exclusions():
    with pytest.raises(NativeError,match='inventory count or original80 identity'):
        seal(build(),*synthetic())


def test_mac_final_host_timeout_cancels_and_settles_without_launching_gpu(tmp_path,monkeypatch):
    import tools.run_lora_development_mac as entry
    import plugin.rhino_listener.lora_final_admission as admission
    import plugin.rhino_listener.lora_common_probe as transport
    from training import lora_development_authority
    spec=toy_spec()
    spec['endpoints']['mac'].update(state_root=str(tmp_path),python=str(Path(sys.executable).resolve()))
    spec['lease_end_epoch']=9999999999
    package,receipt=seal(spec,*synthetic()); config=package['limits']
    monkeypatch.setattr(admission,'admit',lambda *a:(package,tmp_path,receipt))
    monkeypatch.setattr(lora_development_authority,'verify_source',lambda *a:None)
    monkeypatch.setattr(entry.shutil,'disk_usage',lambda *a:SimpleNamespace(free=8*1024**3))
    monkeypatch.setattr(entry.subprocess,'Popen',lambda *a,**k:pytest.fail('no GPU launch before host readiness'))
    def wait(directory,name,deadline,runtime,*,stop_on_timeout):
        if name=='host-ready.json':
            transport.request_shutdown(directory,runtime)
            raise TimeoutError('synthetic host readiness timeout')
        assert name=='host-settlement.json'
        assert read_json(directory,'shutdown.request.json')['runtime_sha256']==runtime
        return {'status':'host_stopped','runtime_sha256':runtime,'exact_delegate_remove_returned':True}
    monkeypatch.setattr(transport,'wait_for_host_reply',wait)
    ready={'config':config,'tokenizer':None,'check_environment':lambda:None,
           'controller':None,'journal':None,'pipe':None,'schedule':package['compiled']['views']['schedule']}
    entry.run(ROOT,package,ready,Path('/unused-synthetic-control'))
    result=read_json(tmp_path,'final-result.json')
    assert not result['gpu_launch_attempted'] and result['claimed_slots'] is None
    assert result['key_removal']['actual_absence_checked'] and not (tmp_path/'host-secret.json').exists()
    assert result['error_type']=='TimeoutError' and 'phase_one_complete' not in result


def test_final_admission_rejects_old_grant_before_opening_private_runtime(tmp_path,monkeypatch):
    import plugin.rhino_listener.lora_final_admission as module
    spec=toy_spec(); spec['endpoints']['mac'].update(source_root=str(tmp_path),state_root=str(tmp_path/'state'))
    _,receipt=seal(spec,*synthetic())
    (tmp_path/'lora-final-spec.json').write_text(json.dumps(spec))
    reads=[]
    def read(directory,name):
        reads.append(name)
        if name=='owner-receipt.json': return receipt
        if name=='owner-approval.json': return {'approved':True,'scope':'old_development'}
        raise AssertionError('must not open private runtime')
    monkeypatch.setattr(module,'read_json',read)
    monkeypatch.setattr(module,'source_guard',lambda *args:None)
    with pytest.raises(NativeError,match='separate exact final'): admit(tmp_path,'mac')
    assert reads==['owner-receipt.json','owner-approval.json']


def test_formal_budget_covers_80_without_expanding_development_default():
    spec=toy_spec(); limits=spec['limits']; clock=lambda:0
    budget=WorkBudget(limits,100000,first_wall=0,first_mono=0,wall=clock,mono=clock,maximum_slots=80)
    budget.work(remaining_slots=80,loading=True)
    with pytest.raises(NativeError): budget.work(remaining_slots=81)
    old=WorkBudget(limits,100000,first_wall=0,first_mono=0,wall=clock,mono=clock)
    with pytest.raises(NativeError): old.work(remaining_slots=80)


@pytest.mark.parametrize('fault',[None,'loading'])
def test_actual_final_supervisor_routes_to_final_worker_and_cannot_retry(tmp_path,monkeypatch,fault):
    from training import lora_development_gpu_entry as module
    spec=toy_spec(); spec['lease_end_epoch']=9999999999
    package,receipt=seal(spec,*synthetic())
    ready={'status':'ready','package_sha256':digest(package),'model_identities':package['model_identities']}
    commands=[]; messages=[{'action':'stop','package_sha256':digest(package)}]
    monkeypatch.setattr(module,'JsonPipe',lambda *a:SimpleNamespace(send=lambda *a:None,receive=lambda *a:messages.pop(0)))
    monkeypatch.setattr(module,'work_source',lambda *a:None)
    monkeypatch.setattr(module.shutil,'disk_usage',lambda *a:SimpleNamespace(free=8*1024**3))
    monkeypatch.setattr(module,'gpu_absent',lambda *a:True)
    monkeypatch.setattr(module,'sys',SimpleNamespace(stdin=SimpleNamespace(fileno=lambda:1),stdout=SimpleNamespace(fileno=lambda:2)))
    class Child:
        def __init__(self,command,**kwargs): commands.append(command); self.pipe=self
        def send(self,*args): pass
        def receive(self,*args):
            if fault: raise TimeoutError('CPU synthetic')
            return ready
        def close(self): return {'pid':100,'exit_observed':True}
    monkeypatch.setattr(module,'OwnedChild',Child)
    result=module.supervise(tmp_path,package,tmp_path)
    assert len(commands)==1 and str(tmp_path/'tools/run_lora_final_gpu.py') in commands[0]
    assert result['status']=='gpu_stopped' and result['additional_cost'] is None
    assert len(result['attempts'])==1
    with pytest.raises(FileExistsError): module.supervise(tmp_path,package,tmp_path)
    assert len(commands)==1


def test_final_gpu_startup_requires_full_four_gib_before_claim(tmp_path,monkeypatch):
    from training import lora_development_gpu_entry as module
    package,_=seal(toy_spec(),*synthetic())
    monkeypatch.setattr(module.shutil,'disk_usage',lambda *a:SimpleNamespace(free=3*1024**3))
    with pytest.raises(NativeError,match='GPU evidence reserve'):
        module.supervise(tmp_path,package,tmp_path)
    assert not (tmp_path/'gpu-started.claim.json').exists()


def test_actual_deployed_gpu_cpu_entry_has_no_private_io_or_backend(tmp_path):
    from tools.check_lora_development_source import PROBE
    spec=build()
    for name in spec['source_files']:
        target=tmp_path/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes((ROOT/name).read_bytes())
    (tmp_path/'lora-final-spec.json').write_text(json.dumps(spec))
    probe=PROBE+"\nsys.argv=['seal_lora_final_owner.py','--check']\nimport tools.seal_lora_final_owner as owner\nassert owner.main()==0\nsys.argv=['run_lora_final_gpu.py','--check']\nimport tools.run_lora_final_gpu as entry\nentry.main()\n"
    result=subprocess.run([sys.executable,'-I','-S','-B','-c',probe,str(tmp_path),''],cwd=tmp_path,capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout.splitlines()[-1])
    assert report['private_inputs_read'] is False and report['configuration']['host_messages_max']==2416
    assert not list(tmp_path.rglob('*.claim.json'))
