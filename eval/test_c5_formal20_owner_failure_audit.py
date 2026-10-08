"""Synthetic owner evidence only; no original source/state or field access."""
import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import c5_formal20_owner_failure_audit as entry
from training.c5_formal20_incomplete_audit import audit_pre_slot_failure
from eval.test_c5_formal20_incomplete_audit import records
from plugin.rhino_listener.c5_research_channel import publish_json, read_json


def test_non_owner_tty_refuses_before_public_or_private_access(monkeypatch):
    monkeypatch.setattr(entry.sys, 'stdin', SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(entry, 'public_original', lambda: pytest.fail('access before TTY gate'))
    with pytest.raises(RuntimeError):
        entry.audit_owner('a' * 64)


def setup(tmp_path, monkeypatch):
    spec, original, values = records()
    evidence = tmp_path / 'synthetic-existing-evidence'; evidence.mkdir(mode=0o700)
    for name, value in values.items():
        publish_json(evidence, name, value)
    source = tmp_path / 'public-source'; source.mkdir(mode=0o700)
    freeze = {'audit_id': entry.ID, 'original_spec_sha256': entry.SPEC_SHA,
        'original_runtime_sha256': entry.RUNTIME_SHA,
        'source_files': {entry.CORE: 'b' * 64, entry.ENTRY: 'b' * 64},
        'environment': {'synthetic': True, 'readable_loaded_external_files': {'/synthetic/runtime.py': 'b' * 64}}}
    monkeypatch.setattr(entry, 'SOURCE', source)
    monkeypatch.setattr(entry, 'STATE', tmp_path / 'new-audit-metadata')
    monkeypatch.setattr(entry, 'EVIDENCE', evidence)
    monkeypatch.setattr(entry.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(entry.sys, 'stderr', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(entry, 'public_original', lambda: (spec, original))
    monkeypatch.setattr(entry, 'public_json', lambda _: freeze)
    monkeypatch.setattr(entry, 'file_sha', lambda _: 'b' * 64)
    monkeypatch.setattr(entry, 'environment', lambda: dict(freeze['environment']))
    monkeypatch.setattr(entry, 'load_core', lambda _: (audit_pre_slot_failure, lambda: None))
    return freeze, values


def test_owner_reads_existing_records_once_and_writes_only_new_closed_summary(tmp_path, monkeypatch):
    freeze, values = setup(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in entry.EVIDENCE.iterdir()}
    summary = entry.audit_owner(entry.digest(freeze))
    assert summary['full_joint_audit_complete'] is False
    assert summary['actual_generation_total'] is None
    assert summary['cipher_or_identity_reads'] == 0
    assert summary == read_json(entry.STATE, 'owner-public-incomplete-audit-summary.json')
    assert {p.name: p.read_bytes() for p in entry.EVIDENCE.iterdir()} == before
    assert sorted(p.name for p in entry.STATE.iterdir()) == [
        'owner-audit-admission.json', 'owner-public-incomplete-audit-summary.json']
    raw = json.dumps(summary)
    assert all(c['task_text'] not in raw for c in values['private-cases.json'])
    with pytest.raises(RuntimeError):
        entry.audit_owner(entry.digest(freeze))
    assert {p.name: p.read_bytes() for p in entry.EVIDENCE.iterdir()} == before


@pytest.mark.parametrize('drift', ['hash', 'source', 'environment', 'existing-state'])
def test_pre_read_guards_refuse_before_any_private_record(tmp_path, monkeypatch, drift):
    freeze, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr('plugin.rhino_listener.c5_research_channel.read_json',
        lambda *args: pytest.fail('private record accessed despite failed guard'))
    sha = entry.digest(freeze)
    if drift == 'hash': sha = 'd' * 64
    if drift == 'source': monkeypatch.setattr(entry, 'file_sha', lambda _: 'c' * 64)
    if drift == 'environment': monkeypatch.setattr(entry, 'environment', lambda: {'drift': True})
    if drift == 'existing-state': entry.STATE.mkdir(mode=0o700)
    with pytest.raises(RuntimeError): entry.audit_owner(sha)


def test_failure_after_admission_keeps_claim_and_never_publishes_false_success(tmp_path, monkeypatch):
    freeze, _ = setup(tmp_path, monkeypatch)
    def refused(*args):
        raise ValueError('private task sentinel')
    monkeypatch.setattr(entry, 'load_core', lambda _: (refused, lambda: None))
    with pytest.raises(ValueError): entry.audit_owner(entry.digest(freeze))
    assert sorted(p.name for p in entry.STATE.iterdir()) == ['owner-audit-admission.json']


def test_entry_error_does_not_print_exception_body(monkeypatch, capsys):
    monkeypatch.setattr(entry.sys, 'argv', ['entry', 'audit', '--freeze-sha256', 'a' * 64])
    def refused(*args): raise ValueError('PRIVATE_TASK_OR_PATH')
    monkeypatch.setattr(entry, 'audit_owner', refused)
    assert entry.main() == 1
    output = capsys.readouterr().err
    assert 'PRIVATE_TASK_OR_PATH' not in output
    assert json.loads(output)['private_content_included'] is False


def test_entry_has_no_model_decryption_rhino_or_process_executor():
    source = Path(entry.__file__).read_text()
    tree = ast.parse(source)
    imports = {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)}
    assert not imports & {'torch', 'transformers', 'Rhino', 'clr', 'subprocess', 'socket'}
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {'kill', 'pidfd_send_signal', 'remove', 'unlink', 'rmtree', 'Popen'}


def test_isolated_no_site_cpu_import_uses_explicit_dependency_root_only():
    import jsonschema
    dependency = str(Path(jsonschema.__file__).resolve().parents[1])
    root = str(Path(__file__).resolve().parents[1])
    code = ('import sys; assert sys.flags.isolated and sys.flags.no_site; '
        'sys.path.append(' + repr(dependency) + '); sys.path.insert(0,' + repr(root) + '); '
        'import training.c5_formal20_plan; print("isolated_public_import_ok")')
    result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and result.stdout.strip() == 'isolated_public_import_ok'
