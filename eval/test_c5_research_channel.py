"""Private temp I/O only: no Rhino, model, network or task corpus."""
import os

import pytest

from plugin.rhino_listener.c5_research_channel import claim_slot, publish_json, read_json, remove_private_key
from plugin.rhino_listener.c5_research_native import NativeError, digest


def directory(tmp_path):
    root = tmp_path/'private'
    root.mkdir(mode=0o700)
    return root


def test_private_publish_read_no_overwrite_and_no_symlink(tmp_path):
    root = directory(tmp_path)
    publish_json(root,'receipt.json',{'version':1})
    assert read_json(root,'receipt.json') == {'version':1}
    assert (root/'receipt.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): publish_json(root,'receipt.json',{})
    (root/'link.json').symlink_to(root/'receipt.json')
    with pytest.raises(OSError): read_json(root,'link.json')
    with pytest.raises(NativeError): read_json(root,'../receipt.json')


def test_wrong_owner_mode_directory_and_file_fail_closed(tmp_path):
    root = directory(tmp_path)
    publish_json(root,'receipt.json',{})
    (root/'receipt.json').chmod(0o644)
    with pytest.raises(NativeError): read_json(root,'receipt.json')
    root.chmod(0o755)
    with pytest.raises(NativeError): publish_json(root,'other.json',{})


@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"n":NaN}',b'{"n":Infinity}',b'{} trailing'])
def test_non_strict_json_rejected(tmp_path,raw):
    root = directory(tmp_path)
    fd = os.open(root/'bad.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as stream: stream.write(raw)
    with pytest.raises((NativeError,ValueError)): read_json(root,'bad.json')


def test_claim_survives_interruption_and_fresh_output_cannot_replace_it(tmp_path):
    root = directory(tmp_path)
    scope = {'stage':'development','task_sha256':'b'*64,'route':'native_control','owner_freeze_sha256':'c'*64}
    slot = digest(scope)
    claim_slot(root,slot,scope)
    (tmp_path/'new-output').mkdir(mode=0o700)
    with pytest.raises(FileExistsError): claim_slot(root,slot,scope)
    assert read_json(root,slot+'.claim.json')['replay_allowed'] is False
    with pytest.raises(NativeError): claim_slot(root,'a'*64,scope)


def test_exact_key_delete_and_absence_without_recursive_cleanup(tmp_path):
    root = directory(tmp_path)
    publish_json(root,'handoff.key',{'synthetic_key_not_live':True})
    publish_json(root,'retain.json',{'evidence':True})
    assert remove_private_key(root,'handoff.key')['actual_absence_checked']
    assert read_json(root,'retain.json')['evidence']
    with pytest.raises(FileNotFoundError): remove_private_key(root,'handoff.key')
