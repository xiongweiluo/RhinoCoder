"""Standalone stdlib read-only code rehash; no Rhino launch or subscription."""
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import time

PUBLIC_RUNTIME = 'eval/c5/rhino-formal20-runtime-freeze-v4.json'
PUBLIC_RUNTIME_RAW_SHA256 = 'f1a2096064edf49991bc060bd3bb956126552924a2347cdf45acdb84964f5550'
PREFIXES = ('/Applications/Rhino 8.app/Contents/', '/Users/xiongweiluo/.rhinocode/',
 '/Users/xiongweiluo/Library/Application Support/McNeel/', '/Users/xiongweiluo/.codex/worktrees/',
 '/opt/anaconda3/lib/', '/opt/anaconda3/bin/')


def file_sha(path):
    path = Path(path).resolve(strict=True)
    assert any(str(path).startswith(prefix) for prefix in PREFIXES), 'non-code path'
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
    after = path.stat()
    assert all(getattr(before,k)==getattr(after,k) for k in
               ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_mode','st_uid','st_nlink'))
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def inspect(repository):
    raw = (Path(repository)/PUBLIC_RUNTIME).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==PUBLIC_RUNTIME_RAW_SHA256, 'public historical inventory drift'
    old = json.loads(raw)
    p = subprocess.run(['pgrep','-x','Rhinoceros'],capture_output=True,text=True)
    assert p.returncode in (0,1), 'process observation unavailable'
    result={'status':'current_mac_readable_code_bytes_only_not_live_host_acceptance',
            'epoch':time.time(),'python':sys.version,'rhino_process_observed':p.returncode==0,
            'rhino_instance_prepared_or_subscribed':False,'model_or_rhino_calls':0,'private_evidence_reads':0,
            'old_instance_guarantee_transferred':False,'execution_ready':False}
    for label,files in [('host',old['rhino_environment_files']),('mac_python',old['mac_environment']['file_sha256'])]:
        actual,missing,changed={},{},{}
        for name,expected in files.items():
            assert any(name.startswith(prefix) for prefix in PREFIXES), 'non-code path'
            if not Path(name).is_file(): missing[name]=expected; continue
            actual[name]=file_sha(name)
            if actual[name]!=expected: changed[name]=actual[name]
        result[label]={'file_sha256':actual,'inventory_sha256':digest(actual),'files':len(actual),
                       'missing':sorted(missing),'changed':sorted(changed),
                       'population_is_historical_readable_code_inventory_not_complete_closure':True}
    info=plistlib.loads(Path('/Applications/Rhino 8.app/Contents/Info.plist').read_bytes())
    result['rhino_bundle_version']={k:info.get(k) for k in ('CFBundleVersion','CFBundleShortVersionString')}
    return result


if __name__=='__main__':
    assert len(sys.argv)==2, 'one explicit public repository root required'
    print(json.dumps(inspect(sys.argv[1]),sort_keys=True))
