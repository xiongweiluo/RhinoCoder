"""Synthetic metadata only. No installed Rhino, SSH, GPU or private cases."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.c5_field_rhino_readonly_preflight import diagnostic_origins
from tools.c5_formal20_public_preflight import preflight
from tools.c5_formal20_freeze_preflight import ROOT, report
from training import c5_formal20_adapters as adapters
from plugin.rhino_listener.c5_research_native import NativeError


def test_unknown_python_and_dynamic_clr_are_not_silently_excused(tmp_path):
    known = tmp_path / 'known.dll'
    known.write_bytes(b'synthetic assembly')
    rows = [('clr', SimpleNamespace(__file__='unknown')),
            ('CLR', SimpleNamespace(__file__='unknown'))]
    assemblies = [{'name':'known', 'dynamic':False, 'location':str(known)},
                  {'name':'generated', 'dynamic':True, 'location':None},
                  {'name':'memory-only', 'dynamic':False, 'location':''}]
    value = diagnostic_origins(tmp_path / 'project', rows, assemblies, str(known))
    assert value['file_backed_partial_inventory'] == {str(known):hashlib.sha256(known.read_bytes()).hexdigest()}
    assert len(value['unverifiable_origins']) == 4
    assert value['partial_inventory_is_closure_proof'] is False


def test_missing_files_and_relative_clr_are_reported_without_proof(tmp_path):
    value = diagnostic_origins(tmp_path / 'project', [('x', SimpleNamespace(__file__=str(tmp_path/'missing.py')))],
        [{'name':'relative', 'dynamic':False, 'location':'unknown'}], 'python')
    assert {r['kind'] for r in value['unverifiable_origins']} == {
        'unresolved_python_file', 'nonabsolute_clr_location', 'nonabsolute_python_executable'}
    assert not value['file_backed_partial_inventory'] and not value['partial_inventory_is_closure_proof']


def test_known_file_inventory_never_itself_grants_admission(tmp_path):
    path = tmp_path / 'module.py'
    path.write_text('# synthetic\n')
    value = diagnostic_origins(tmp_path/'project', [('x',SimpleNamespace(__file__=str(path)))], [], str(path))
    assert not value['unverifiable_origins'] and len(value['file_backed_partial_inventory']) == 1
    assert value['partial_inventory_is_closure_proof'] is False


def test_registered_public_commitment_remains_nonconsuming():
    value = preflight(ROOT/'eval/c5/rhino-formal20-public-commitment-v1.json')
    assert value['public_commitment_sha256'] == '41c92c723df663782000a4e34934a371a2a552e5ef27d6052b7c6d07656ebaf4'
    assert value['private_task_rows_read'] == value['formal_model_calls'] == 0
    assert value['execution_ready'] is False and value['encrypted_artifact_opened'] is False
    assert report()['execution_ready'] is False


def test_resource_v5_changes_deadline_not_caps_or_authority():
    value = json.loads((ROOT/'eval/c5/rhino-resource-boundary-v5-20261006.json').read_text())
    assert value['owner_reported_expiry_epoch'] == 1791392400
    assert value['latest_generation_cutoff_epoch'] == 1791391500
    assert value['owner_reported_expiry_epoch'] - value['latest_generation_cutoff_epoch'] == 900
    assert value['development_original_allocation_seconds'] == 3600
    assert value['formal_pairing_max_seconds'] == 10800
    assert value['original_cumulative_max_seconds'] == 57600
    assert not value['execution_authorized'] and not value['provider_timestamp_independently_verified']


def test_changed_ssh_pin_stops_before_process_or_worker_files(tmp_path, monkeypatch):
    pin = tmp_path/'host-pin'
    pin.write_text('synthetic changed key\n')
    monkeypatch.setattr(adapters, 'SSH_SOCKET', SimpleNamespace(is_socket=lambda:True))
    monkeypatch.setattr(adapters, 'SSH_KNOWN_HOSTS', pin)
    attempts = []
    value = adapters.ModelAdapter(tmp_path, {}, {}, guard=lambda:None,
        process_factory=lambda *a,**k:attempts.append(a))
    with pytest.raises(NativeError, match='pinned SSH host identity differs'):
        value.start()
    assert not attempts and not (tmp_path/'worker-stderr.txt').exists()


def test_real_endpoint_in_unfrozen_draft_is_single_port_and_pinned():
    value = json.loads((ROOT/'eval/c5/rhino-formal20-spec-draft.json').read_text())
    assert value['ssh_port'] == adapters.SSH_PORT == 22159
    assert value['ssh_socket'] == str(adapters.SSH_SOCKET)
    assert value['ssh_known_hosts_file_sha256'] == adapters.SSH_KNOWN_HOSTS_SHA
    assert value['execution_ready'] is False and value['owner_approval_received'] is False
