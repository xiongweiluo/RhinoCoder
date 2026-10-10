"""Preparation-only public metadata controls; no model/Rhino/private input."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_research_native import NativeError
from tools import prepare_c5_formal20_freeze_v2 as builder

ROOT=Path(__file__).resolve().parents[1]


def receiver(path,raw,*,size=None,sha=None):
    return subprocess.run([sys.executable,'-B','-c',builder.PUBLIC_RUNTIME_RECEIVER,
        str(path),str(len(raw) if size is None else size),
        hashlib.sha256(raw).hexdigest() if sha is None else sha],
        input=raw,capture_output=True,timeout=5)


def test_public_receiver_ack_before_input_EOF(tmp_path):
    raw=b'{"public_runtime_only":true}\n';path=tmp_path/'freeze.json'
    process=subprocess.Popen([sys.executable,'-B','-c',builder.PUBLIC_RUNTIME_RECEIVER,
        str(path),str(len(raw)),hashlib.sha256(raw).hexdigest()],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        process.stdin.write(raw);process.stdin.flush()
        assert process.wait(timeout=5)==0 # stdin is deliberately still open.
        assert json.loads(process.stdout.read())=={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        assert path.read_bytes()==raw and path.stat().st_mode & 0o777==0o600
    finally:
        process.stdin.close()
        if process.poll() is None:process.kill();process.wait(timeout=5)
        process.stdout.close();process.stderr.close()


@pytest.mark.parametrize('size',(0,1048577))
def test_receiver_rejects_invalid_size_before_writing(tmp_path,size):
    path=tmp_path/'freeze.json'
    assert receiver(path,b'public',size=size).returncode!=0
    assert not path.exists()


def test_receiver_rejects_truncation_or_wrong_hash(tmp_path):
    for index,kwargs in enumerate(({'size':10},{'sha':'0'*64})):
        path=tmp_path/('freeze%d.json'%index)
        assert receiver(path,b'public',**kwargs).returncode!=0
        assert not path.exists()


def test_receiver_never_overwrites_existing_or_symlink_file(tmp_path):
    path=tmp_path/'preserved.json';path.write_bytes(b'old public evidence')
    assert receiver(path,b'new').returncode!=0
    alias=tmp_path/'alias.json';alias.symlink_to(path)
    assert receiver(alias,b'new').returncode!=0
    assert path.read_bytes()==b'old public evidence'


def test_transfer_requires_exact_ack_and_bounded_public_payload(monkeypatch,tmp_path):
    raw=b'{"public":true}\n';calls=[]
    monkeypatch.setattr(builder,'REMOTE_SOURCE',tmp_path)
    monkeypatch.setattr(builder,'ssh_args',lambda:['ssh'])
    def transfer(args,**kwargs):
        calls.append((args,kwargs))
        return json.dumps({'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}).encode()
    monkeypatch.setattr(builder.subprocess,'check_output',transfer)
    assert builder.transfer_new_public_runtime(raw)['bytes']==len(raw)
    assert calls[0][1]=={'input':raw,'timeout':30}
    assert str(tmp_path/builder.FREEZE_FILE) in calls[0][0][-1]
    monkeypatch.setattr(builder.subprocess,'check_output',lambda *a,**k:b'{"bytes":1,"sha256":"wrong"}')
    with pytest.raises(NativeError):builder.transfer_new_public_runtime(raw)
    for invalid in (b'',b'x'*(1048576+1),'not bytes'):
        with pytest.raises(NativeError):builder.transfer_new_public_runtime(invalid)


def test_resource_renewal_preserves_contract_and_all_hour_ceilings():
    old=json.loads((ROOT/'eval/c5/rhino-formal20-spec-v3.json').read_bytes())
    new=json.loads((ROOT/'eval/c5/rhino-formal20-spec-v4.json').read_bytes())
    allowed={'deployment_revision','mac_source_root','mac_state_root','remote_source_root','remote_state_root',
        'entry_return_wrapper','latest_owner_start_epoch','lease_expiry_epoch','model_generation_cutoff_epoch',
        'observer_backend','previous_v3_authorization_retired_before_any_admission','state'}
    assert {k:old[k] for k in old if k not in allowed}=={k:new[k] for k in new if k not in allowed}
    for k in ('latest_owner_start_epoch','lease_expiry_epoch','model_generation_cutoff_epoch'):
        assert new[k]-old[k]==86400
    old_resource=json.loads((ROOT/'eval/c5/rhino-resource-boundary-v7-formal20-20261007.json').read_bytes())['formal_resource_boundary']
    new_resource=json.loads((ROOT/builder.RESOURCE_FILE).read_bytes())['formal_resource_boundary']
    for k in old_resource:
        assert new_resource[k]==old_resource[k]+(86400 if k.endswith('_epoch') else 0)
    assert new['model_generation_cutoff_epoch']-new['latest_owner_start_epoch']==18000+360
    assert new['lease_expiry_epoch']-new['model_generation_cutoff_epoch']==900
    assert new_resource['formal_max_seconds']==18000
    from tools.run_c5_formal20_worker_v2 import PUBLIC_FILES
    assert builder.RESOURCE_FILE in PUBLIC_FILES
    assert old['observer_backend']['code_read_roots']==new['observer_backend']['code_read_roots'][:-1]
    assert new['observer_backend']['code_read_roots'][-1]==str(builder.MAC_SOURCE)
