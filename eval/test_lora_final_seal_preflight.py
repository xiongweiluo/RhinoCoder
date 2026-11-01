"""Read-only owner preflight on public synthetic fixtures, no actual private data."""
import json
import pytest
from eval.test_lora_final_owner_confirmation import inputs
from tools.build_lora_final_package import ROOT


@pytest.mark.parametrize('fault,stage,code',[
 ('none',None,None),
 ('quote','input_path','path_has_outer_quote'),
 ('missing','read_cases_json','input_file_missing_empty_or_over_size_limit'),
 ('json','read_cases_json','invalid_json_or_encoding'),
 ('existing','output_directory_check','output_directory_already_exists'),
 ('parent','output_directory_check','output_parent_missing'),
 ('format','encrypted_format_check','encryption_format_must_be_age_x25519_or_aes_256_gcm'),
 ('empty_cipher','encrypted_file_check','encrypted_file_missing_symlink_empty_or_over_10_MiB'),
 ('binding','current_file_binding','current_file_binding_not_confirmed'),
 ('overlap','custody_validation','new_set_numeric_template_overlap'),
 ('near','custody_validation','new_set_near_duplicate_overlap'),
 ('unexpected','custody_validation','unexpected_error_details_withheld'),
])
def test_preflight_never_writes_or_exposes_private_values(tmp_path,monkeypatch,capsys,fault,stage,code):
    import tools.seal_lora_final_owner as owner
    import tools.c5_rhino_formal20_owner_exclusion as private
    import plugin.rhino_listener.lora_development_admission as admission
    import training.lora_final_custody as custody
    spec,cases,_,_=inputs();root=tmp_path/'public';root.mkdir()
    (root/'lora-final-spec.json').write_text(json.dumps(spec))
    source=tmp_path/'PRIVATE_FILE.json';encrypted=tmp_path/'PRIVATE_FILE.age';output=tmp_path/'PRIVATE_OUTPUT'
    if fault=='near': cases[1]['task_text']=cases[0]['task_text']+' 17'
    if fault=='overlap':
        base=cases[0]['task_text'];cases[0]['task_text']=base+' 1';cases[1]['task_text']=base+' 2'
    source.write_text('PRIVATE_VALUE' if fault=='json' else json.dumps(cases))
    encrypted.write_bytes(b'' if fault=='empty_cipher' else b'PUBLIC_SYNTHETIC_CIPHERTEXT')
    if fault=='missing': source=tmp_path/'PRIVATE_MISSING'
    if fault=='existing': output.mkdir();(output/'keep').write_text('PRIVATE_VALUE')
    if fault=='parent': output=tmp_path/'PRIVATE_MISSING'/'out'
    if fault=='unexpected':
        def fail(*a): raise ValueError('PRIVATE_EXCEPTION')
        monkeypatch.setattr(custody,'seal_owner_confirmed',fail)
    answers=iter([("'"+str(source)+"'") if fault=='quote' else str(source),str(encrypted),str(output),
                  'PRIVATE_FORMAT' if fault=='format' else 'age-x25519','no' if fault=='binding' else 'SEAL'])
    monkeypatch.setattr(owner,'ROOT',root);monkeypatch.setattr(owner.sys,'argv',['owner','--check-seal'])
    monkeypatch.setattr(owner.sys.stdin,'isatty',lambda:True);monkeypatch.setattr(owner.sys.stdout,'isatty',lambda:True)
    monkeypatch.setattr(private,'_worktrees',lambda **k:[ROOT]);monkeypatch.setattr(admission,'source_guard',lambda *a:None)
    monkeypatch.setattr(owner.getpass,'getpass',lambda label:next(answers))
    before={str(p.relative_to(tmp_path)):p.read_bytes() if p.is_file() else None for p in tmp_path.rglob('*')}
    result=owner.main();out=capsys.readouterr();report=json.loads(out.out)
    assert not out.err and 'PRIVATE' not in out.out and str(tmp_path) not in out.out
    assert not report['sealed'] and not report['execution_authorized']
    assert before=={str(p.relative_to(tmp_path)):p.read_bytes() if p.is_file() else None for p in tmp_path.rglob('*')}
    if fault=='none':
        assert result==0 and report['status']=='seal_preflight_passed_not_sealed' and report['files_written']==0
    else:
        assert result==2 and report['stage']==stage and report['code']==code
        assert not report['output_may_be_partial']


def test_preflight_rejects_noninteractive_before_reading_or_prompting(monkeypatch,capsys):
    import tools.seal_lora_final_owner as owner
    monkeypatch.setattr(owner.sys,'argv',['owner','--check-seal'])
    monkeypatch.setattr(owner.sys.stdin,'isatty',lambda:False)
    monkeypatch.setattr(owner.getpass,'getpass',lambda *a:pytest.fail('must not prompt'))
    assert owner.main()==2
    assert capsys.readouterr().out.strip()=='owner_interactive_terminal_required'
