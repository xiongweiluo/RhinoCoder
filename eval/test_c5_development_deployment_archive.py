"""Synthetic archive populations; no remote/data/authentication access."""
import io
import tarfile

import pytest

from plugin.rhino_listener.c5_research_native import NativeError
from tools.prepare_c5_hostassurance_development_freeze import verify_archive_population


def archive(names):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as stream:
        for name in names:
            row=tarfile.TarInfo(name);row.size=1
            stream.addfile(row,io.BytesIO(b'#'))
    return output.getvalue()


def test_only_explicit_file_population_passes():
    verify_archive_population(archive(['tools/approved.py']),['tools/approved.py'])


@pytest.mark.parametrize('actual',[['tools/approved.py','tools/._approved.py'],
    ['tools/approved.py','authentication.key'],['tools/approved.py','tools/approved.py'],[]])
def test_extra_metadata_keys_duplicates_and_missing_files_refused_before_transfer(actual):
    with pytest.raises(NativeError):verify_archive_population(archive(actual),['tools/approved.py'])
