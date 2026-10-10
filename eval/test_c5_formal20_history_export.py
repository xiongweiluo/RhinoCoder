"""Synthetic historical inputs only; never open a real candidate/holdout."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.build_c5_formal20_history_exclusions import Collector, export


def test_all_record_steps_and_identities_are_retained_without_answers():
    c = Collector()
    c.walk({'family_id': 'old-family', 'template_family': 'old-template', 'records': [
        {'user_step': 'create synthetic box', 'target': 'SECRET ANSWER'}, {'user_step': 'move synthetic box'}]}, 'synthetic')
    rows = list(c.rows.values())
    assert {r['task_text'] for r in rows} == {'create synthetic box', 'move synthetic box'}
    assert all(r['family_id'] == 'old-family' and r['template_family'] == 'old-template' for r in rows)


def test_ast_does_not_execute_scripts_or_treat_partial_fstrings_as_tasks(tmp_path):
    source = tmp_path / 'history.py'
    source.write_text("raise RuntimeError('must never execute')\nTASK='native control description'\n"
        "CASES=({'id':'old-r-task','task':'创建一个历史盒体'},)\n"
        "task=f'请创建宽{private_width}的盒体'\n")
    c = Collector(); c.ingest(source, 'synthetic')
    texts = {r['task_text'] for r in c.rows.values()}
    assert 'native control description' in texts and '创建一个历史盒体' in texts
    assert '请创建宽' not in texts
    assert c.unresolved and c.unresolved[0]['reason'].startswith('dynamic_task_template')


def test_explicit_r_json_is_byte_equivalent_and_native_proxy_is_marked():
    c = Collector(); step = {'op':'create_box','width':347,'depth':353,'height':359}
    c.walk({'steps':[step,{'name':'move_object','arguments':{'object_id':'box-1'}}]}, 'synthetic')
    expected = json.dumps(step,sort_keys=True,separators=(',',':'))
    assert expected in {r['task_text'] for r in c.rows.values()}
    assert any('native_operation_proxy_not_original_prompt' in r['representation_kinds'] for r in c.rows.values())


def test_bounded_static_r_generator_materializes_without_eval_or_import(tmp_path):
    source=tmp_path/'history.py'
    source.write_text("raise RuntimeError('must not run')\nWRITES=tuple((f'请创建宽{25+i}深{36+i}的盒体',(25+i,36+i)) for i in range(3))\n")
    c=Collector();c.ingest(source,'synthetic')
    assert {r['task_text'] for r in c.rows.values()} == {'请创建宽25深36的盒体','请创建宽26深37的盒体','请创建宽27深38的盒体'}
    assert not c.unresolved


def test_export_private_modes_provenance_and_no_overwrite(tmp_path):
    c = Collector(); c.walk({'task':'历史开发盒体','id':'R-old'}, 'synthetic')
    c.sources['synthetic'] = {'sha256':'a'*64,'bytes':100,'new_unique_rows':1}
    out = tmp_path / 'owner-history'
    value = export(c, out, [])
    assert value['new20_body_rows_read'] == value['original80_body_rows_read'] == 0
    raw = (out / 'extra-exclusion.jsonl').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == value['extra_exclusion_sha256']
    assert os.stat(out).st_mode & 0o777 == 0o700
    assert os.stat(out / 'extra-exclusion.jsonl').st_mode & 0o777 == 0o600
    assert json.loads((out / 'coverage-report.json').read_text())['all_history_proven_complete'] is False
    with pytest.raises(ValueError): export(c,out,[])
    with pytest.raises(ValueError): export(c,tmp_path / 'inside',[tmp_path])


def test_owner_frontend_rejects_non_tty_without_reading_any_input(monkeypatch):
    from tools import c5_formal20_owner_preflight_interactive as module
    monkeypatch.setattr(module.sys, 'argv', ['owner-preflight','--history-directory','/nonexistent-history',
        '--development-root','/nonexistent-development'])
    monkeypatch.setattr(module.sys,'stdin',SimpleNamespace(isatty=lambda:False))
    monkeypatch.setattr(module.getpass,'getpass',lambda *args:pytest.fail('must not ask private paths'))
    assert module.main() == 1
