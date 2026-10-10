"""Aggregate-only progress; synthetic tmp state, never real private inputs."""
import json
import os
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_research_native import NativeError
from training.c5_formal20_public_progress import publish_progress,read_public_progress,validate_progress
from plugin.rhino_listener.c5_host_observer_clr import ClrObserverBackend


def publish(state,sequence=0,**kwargs):
    values={'phase':'route_slot_finished','sequence':sequence,'slots_attempted':1,'slots_finished':1,
        'confirmed_generation_stages':2,'counters_complete':True,'elapsed_seconds':1.0,
        'runtime_freeze_sha256':'a'*64,'public_commitment_sha256':'b'*64}
    values.update(kwargs);return publish_progress(state,**values)


def test_missing_before_started_is_read_only_and_no_authority(tmp_path):
    path=tmp_path/'absent'
    assert read_public_progress(path)['started_claim_present'] is False
    assert not path.exists()


def test_missing_after_started_does_not_assert_zero_or_permit_replay(tmp_path):
    state=tmp_path/'state';state.mkdir(mode=0o700)
    publish_json(state,'formal20.started.json',{'synthetic':True})
    value=read_public_progress(state)
    assert value['slots_attempted'] is value['confirmed_generation_stages'] is None
    assert value['replay_allowed'] is False and value['started_claim_present'] is True


def test_atomic_current_and_immutable_history_no_private_keys(tmp_path):
    state=tmp_path/'state';state.mkdir(mode=0o700)
    publish_json(state,'formal20.started.json',{'synthetic':True})
    first=publish(state);second=publish(state,1,slots_attempted=2,slots_finished=2)
    assert read_public_progress(state)==second
    assert read_json(state,'formal20.public-0000.json')==first
    assert not list(state.glob('*.tmp'))
    assert not any(k in second for k in ('task','family_id','answers','raw','identity_file','key','scene'))
    with pytest.raises(FileExistsError):publish(state)


@pytest.mark.parametrize('bad',[{'slots_attempted':41},{'slots_finished':2},{'confirmed_generation_stages':241},
    {'elapsed_seconds':float('nan')},{'counters_complete':1},{'phase':'raw private text'},{'sequence':True}])
def test_out_of_schema_progress_rejected(tmp_path,bad):
    state=tmp_path/'state';state.mkdir(mode=0o700)
    publish_json(state,'formal20.started.json',{'synthetic':True})
    with pytest.raises(NativeError):publish(state,**bad)


def test_no_implicit_consumption_or_private_file_follow(tmp_path):
    state=tmp_path/'state';state.mkdir(mode=0o700)
    with pytest.raises(NativeError):publish(state)
    publish_json(state,'formal20.started.json',{'synthetic':True})
    sensitive=tmp_path/'synthetic-private.json';sensitive.write_text('NOT VALID JSON DO NOT READ')
    (state/'public-progress.json').symlink_to(sensitive)
    with pytest.raises(OSError):read_public_progress(state)
    with pytest.raises(NativeError):publish(state)
    assert sensitive.read_text()=='NOT VALID JSON DO NOT READ'


def test_observer_origin_reader_never_hashes_private_json_or_escape(tmp_path):
    source=tmp_path/'code';source.mkdir()
    secret=tmp_path/'synthetic-private.json';secret.write_text('synthetic do not inspect')
    link=source/'code.py';link.symlink_to(secret)
    backend=object.__new__(ClrObserverBackend)
    backend.spec={'code_read_roots':[str(source)],'code_read_exact_files':[]}
    value=backend.file_record(secret)
    assert value['origin'] is value['file_sha256'] is None
    value=backend.file_record(link)
    assert value['origin'] is value['file_sha256'] is None
    safe=source/'module.py';safe.write_text('# synthetic\n')
    assert backend.file_record(safe)['state']=='file_backed_bytes_only'
