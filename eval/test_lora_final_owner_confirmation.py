"""Owner confirmation simplification; public synthetic CPU fixtures only."""
import copy
from datetime import datetime,timezone
import json
import pytest
from eval.test_lora_final_preparation import synthetic
from tools.build_lora_final_package import build,ROOT
from training.lora_final_custody import seal_owner_confirmed
from plugin.rhino_listener.lora_final_admission import BINDING_FLAGS,validate_receipt,validate_runtime
from plugin.rhino_listener.c5_research_native import NativeError


def inputs():
    spec=build(); cases,_,encrypted,_=synthetic()
    binding={'actor':'repository_owner','sealed_at_utc':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
             'owner_confirmation':spec['custody_policy']['owner_confirmation'],**{k:True for k in BINDING_FLAGS}}
    return spec,cases,encrypted,binding


def test_new_receipt_records_owner_basis_without_fabricated_machine_evidence():
    spec,cases,encrypted,binding=inputs()
    package,receipt=seal_owner_confirmed(spec,cases,encrypted,binding)
    assert validate_runtime(spec,receipt,package)==package
    assert receipt['schema_version']==2 and receipt['exclusions'] is None
    assert receipt['automated_overlap_count'] is None
    assert not receipt['historical_inventory_machine_checked'] and not receipt['execution_authorized']
    assert receipt['automated_checks']['full_private_historical_inventory']=='not_performed'
    for row in cases:
        assert row['task_text'] not in json.dumps(receipt) and row['family_id'] not in json.dumps(receipt)


@pytest.mark.parametrize('fault',['false_scan','zero_overlap','fake_inventory','changed_confirmation','missing_binding','legacy_spec'])
def test_receipt_rejects_false_machine_claims_and_unbound_summary(fault):
    spec,cases,encrypted,binding=inputs();_,receipt=seal_owner_confirmed(spec,cases,encrypted,binding)
    if fault=='false_scan': receipt['historical_inventory_machine_checked']=True
    if fault=='zero_overlap': receipt['automated_overlap_count']=0
    if fault=='fake_inventory': receipt['exclusions']={}
    if fault=='changed_confirmation': receipt['custodian_attestation']['owner_confirmation']={}
    if fault=='missing_binding': receipt['custodian_attestation'][BINDING_FLAGS[0]]=False
    if fault=='legacy_spec': spec.pop('custody_policy')
    with pytest.raises((NativeError,KeyError)): validate_receipt(spec,receipt)


@pytest.mark.parametrize('fault',['duplicate','public_overlap','not_bound','bad_encryption'])
def test_seal_retains_available_checks_and_current_binding(fault):
    spec,cases,encrypted,binding=inputs()
    if fault=='duplicate': cases[1]['task_text']=cases[0]['task_text']+' 17'
    if fault=='public_overlap':
        import hashlib
        from data_pipeline.training_views import numeric_template_signature
        spec['exclusion_reference']['historical_numeric_hashes'].append(hashlib.sha256(('historical-text:'+numeric_template_signature(cases[0]['task_text'])).encode()).hexdigest())
    if fault=='not_bound': binding['encryption_roundtrip_verified']=False
    if fault=='bad_encryption': encrypted['format']='plaintext'
    with pytest.raises(NativeError): seal_owner_confirmed(spec,cases,encrypted,binding)


def test_interactive_entry_never_requests_inventory_or_attestation_file(tmp_path,monkeypatch,capsys):
    import tools.seal_lora_final_owner as owner
    import tools.c5_rhino_formal20_owner_exclusion as private
    import plugin.rhino_listener.lora_development_admission as admission
    spec,cases,_,_=inputs();root=tmp_path/'public';root.mkdir()
    (root/'lora-final-spec.json').write_text(json.dumps(spec))
    source=tmp_path/'synthetic.json';source.write_text(json.dumps(cases))
    encrypted=tmp_path/'synthetic.age';encrypted.write_bytes(b'public synthetic ciphertext stand-in')
    output=tmp_path/'seal'
    answers=iter([str(source),str(encrypted),str(output),'age-x25519','SEAL']);prompts=[]
    def prompt(label): prompts.append(label); return next(answers)
    monkeypatch.setattr(owner,'ROOT',root);monkeypatch.setattr(owner.sys,'argv',['owner'])
    monkeypatch.setattr(owner.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(owner.sys.stdout,'isatty',lambda:True)
    monkeypatch.setattr(private,'_worktrees',lambda **k:[ROOT]);monkeypatch.setattr(admission,'source_guard',lambda *a:None)
    monkeypatch.setattr(owner.getpass,'getpass',prompt)
    original=private._json;reads=[]
    def read(path): reads.append(path); return original(path)
    monkeypatch.setattr(private,'_json',read)
    assert owner.main()==0
    assert reads==[source] and len(prompts)==5
    assert all('清单JSON路径' not in p and '确认JSON路径' not in p for p in prompts)
    receipt=json.loads(capsys.readouterr().out);validate_receipt(spec,receipt)
    assert sorted(p.name for p in output.iterdir())==['owner-receipt.json','runtime-package.json','scorer-cases.json']
    assert source.read_text()==json.dumps(cases)
