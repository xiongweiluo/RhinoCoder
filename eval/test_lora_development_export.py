"""Private synthetic export custody; never touches real/new/old run material."""
import io
import tarfile

import pytest

from plugin.rhino_listener.c5_research_channel import publish_json
from plugin.rhino_listener.c5_research_native import NativeError, digest
from training.lora_development_export import export_gpu, verify_archive


def fixture(tmp_path):
    tmp_path.chmod(0o700)
    package = {'synthetic': True}
    publish_json(tmp_path, 'gpu-settlement.json', {'package_sha256': digest(package), 'status': 'gpu_stopped'})
    publish_json(tmp_path, 'owner-approval.json', {'synthetic_private_grant': True})
    attempt = tmp_path / 'load-0'; attempt.mkdir(mode=0o700)
    publish_json(attempt, 'attempt.claim.json', {'synthetic': True})
    cache = attempt / 'cache'; cache.mkdir(mode=0o700); (cache / 'not-evidence').write_text('cache')
    return package


def test_stopped_export_has_exact_member_manifest_without_grant_or_cache(tmp_path):
    package = fixture(tmp_path)
    output = io.BytesIO(); export_gpu(tmp_path, package, output)
    path = tmp_path / 'export.tar'; path.write_bytes(output.getvalue())
    result = verify_archive(path, package)
    assert result['verified'] and result['files'] == 2
    with tarfile.open(path) as archive:
        assert sorted(archive.getnames()) == ['export-manifest.json', 'gpu-settlement.json', 'load-0/attempt.claim.json']


def test_wrong_package_and_symlink_evidence_refused(tmp_path):
    package = fixture(tmp_path)
    with pytest.raises(NativeError): export_gpu(tmp_path, {'other': True}, io.BytesIO())
    (tmp_path / 'load-0' / 'alias.json').symlink_to(tmp_path / 'owner-approval.json')
    with pytest.raises(NativeError): export_gpu(tmp_path, package, io.BytesIO())


def test_untrusted_archive_path_is_not_extracted_or_accepted(tmp_path):
    path = tmp_path / 'bad.tar'
    with tarfile.open(path, 'w') as archive:
        info = tarfile.TarInfo('../escape'); info.size = 1
        archive.addfile(info, io.BytesIO(b'x'))
    with pytest.raises(NativeError): verify_archive(path, {'synthetic': True})
    assert not (tmp_path.parent / 'escape').exists()
