"""Public-only deployment regression; never reads either private holdout."""
import shutil
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
DEPENDENCIES=('eval/c5/final-holdout-commitment.json',
    'eval/c5/dataset-v2-freeze-manifest.json','eval/c5/historical-exclusions.json')
COMMITMENT='eval/c5/rhino-formal20-public-commitment-v1.json'


def deployed_public_root(tmp_path,monkeypatch):
    from tools import c5_formal20_public_preflight as validator
    for name in (*DEPENDENCIES,COMMITMENT):
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    monkeypatch.setattr(validator,'ROOT',tmp_path)
    return validator


def test_all_transitive_public_dependencies_are_in_frozen_transport():
    from tools.run_c5_formal20_worker_v2 import PUBLIC_FILES
    assert set(DEPENDENCIES)<=set(PUBLIC_FILES)


def test_public_preflight_works_in_isolated_deployed_root(tmp_path,monkeypatch):
    validator=deployed_public_root(tmp_path,monkeypatch)
    result=validator.preflight(tmp_path/COMMITMENT)
    assert result['public_commitment_sha256']=='41c92c723df663782000a4e34934a371a2a552e5ef27d6052b7c6d07656ebaf4'


@pytest.mark.parametrize('missing',DEPENDENCIES)
def test_missing_public_dependency_rejected_before_any_admission(tmp_path,monkeypatch,missing):
    validator=deployed_public_root(tmp_path,monkeypatch)
    (tmp_path/missing).unlink()
    with pytest.raises(FileNotFoundError):validator.preflight(tmp_path/COMMITMENT)
    assert not list(tmp_path.glob('*.claim.json'))


def test_builder_checks_deployed_root_not_original_git_root(monkeypatch,tmp_path):
    from tools import prepare_c5_formal20_freeze_v2 as builder
    monkeypatch.setattr(builder,'MAC_SOURCE',tmp_path)
    called=[]
    def run(args,**kwargs):
        called.append((args,kwargs))
        return b'{"public_commitment_sha256":"41c92c723df663782000a4e34934a371a2a552e5ef27d6052b7c6d07656ebaf4"}'
    monkeypatch.setattr(builder.subprocess,'check_output',run)
    builder.verify_deployed_public_commitment()
    assert called[0][1]['cwd']==tmp_path
    assert str(tmp_path/COMMITMENT) in called[0][0]
    assert '-B' in called[0][0]
