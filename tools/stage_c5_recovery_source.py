#!/usr/bin/env python3
"""Public-only initial staging. No state/grant/history initialization or actor."""
import argparse
import hashlib
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plugin.rhino_listener.c5_recovery_profile import RUNTIME,INSTANCE
from plugin.rhino_listener.c5_recovery_scope import paths
from training.c5_reuse_evidence import require,sha,strict,canonical

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mac',action='store_true',required=True);p.add_argument('--check',action='store_true');p.add_argument('--revision',action='store_true');a=p.parse_args()
    source=Path(paths('mac',1)['source_root']);state=source.parent/(INSTANCE+'-state')
    require(a.revision or not os.path.lexists(state),'recovery_initial_staging_requires_absent_live_state')
    runtime=strict((ROOT/RUNTIME).read_bytes(),limit=2*1024*1024)
    files=dict(runtime['source_files']);files[RUNTIME]=hashlib.sha256((ROOT/RUNTIME).read_bytes()).hexdigest()
    if a.revision:
        require(not a.check and source.exists() and state.exists(),'recovery_revision_requires_existing_known_campaign')
        from training.c5_recovery_storage import EvidenceLog,read_private
        from training.c5_recovery_controller import replay
        from training.c5_recovery_history import history_guard
        from plugin.rhino_listener.c5_recovery_profile import SPEC,HISTORY
        spec=strict((ROOT/SPEC).read_bytes())
        frozen_previous=spec['recovery']['previous_campaign_head_sha256']
        parent=Path(paths('mac',1)['admission_root'])/'engineering-recovery-v3'
        original=strict(read_private(parent/'ledger/manifest.json'))['binding']
        history=strict((ROOT/HISTORY).read_bytes())
        log=EvidenceLog(parent/'ledger',original,history_guard(parent.parent,'mac',history))
        try:
            with log.locked():
                rows=log.rows();status=replay(original,rows)
                require(rows and rows[-1]['record_sha256']==frozen_previous and not status['active']
                    and status['status'] not in ('PAUSED_RECONCILIATION','AWAITING_INDEPENDENT_AUDIT')
                    and status['attempts']<3,'recovery_revision_staging_requires_exact_known_pause')
                for folder in state.glob('attempt-*'):
                    if not folder.is_dir():continue
                    if (folder/'warmup.started.json').exists():require((folder/'warmup.result.json').exists(),'recovery_revision_warmup_unknown')
                    if (folder/'new-hub-started.claim.json').exists():
                        require((folder/'host-continuity-terminal-receipt.json').exists()
                            and not os.path.lexists(folder/'hub.key'),'recovery_revision_native_cleanup_unknown')
                previous=strict((source/RUNTIME).read_bytes(),limit=2*1024*1024)
                previous_files=dict(previous['source_files']);previous_files[RUNTIME]=hashlib.sha256((source/RUNTIME).read_bytes()).hexdigest()
                require(set(files)==set(previous_files),'recovery_revision_population_change_requires_new_staging_review')
                archive=source.parent/'recovery-public-material-archive'
                archive.mkdir(mode=0o700,exist_ok=True);archive=archive/sha(previous);archive.mkdir(mode=0o700)
                for name,h in previous_files.items():
                    raw=(source/name).read_bytes();require(hashlib.sha256(raw).hexdigest()==h,'recovery_prior_deployment_byte_drift')
                    target=archive/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                    with target.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                for name,h in files.items():
                    raw=(ROOT/name).read_bytes();require(hashlib.sha256(raw).hexdigest()==h,'recovery_revision_input_drift')
                    if hashlib.sha256((source/name).read_bytes()).hexdigest()==h:continue
                    target=source/name;temp=target.with_name(target.name+'.revision-new')
                    with temp.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                    os.replace(temp,target)
                require(log.rows()==rows,'recovery_revision_staging_cannot_change_campaign_history')
        finally:log.close()
    elif not a.check:
        # No actor/grant/state exists. A interrupted PUBLIC copy can resume
        # matching bytes; it does not consume an attempt or replace evidence.
        os.umask(0o077)
        if not os.path.lexists(source):source.mkdir(mode=0o700)
        else:require(source.is_dir() and source.resolve()==source,'recovery_stage_root_alias')
        for name,h in files.items():
            raw=(ROOT/name).read_bytes();require(hashlib.sha256(raw).hexdigest()==h,'recovery_stage_input_byte_drift')
            target=source/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            if os.path.lexists(target):
                require(target.resolve()==target and hashlib.sha256(target.read_bytes()).hexdigest()==h,
                        'recovery_partial_stage_drift_requires_incremental_review')
                continue
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
            try:
                offset=0
                while offset<len(raw):
                    count=os.write(fd,raw[offset:]);require(count>0,'recovery_stage_short_write');offset+=count
                os.fsync(fd)
            finally:os.close(fd)
    actual={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() or p.is_symlink()}
    require(actual==set(files),'recovery_stage_closed_public_population')
    require(source.resolve()==source and all((source/n).resolve()==source/n and hashlib.sha256((source/n).read_bytes()).hexdigest()==h
        for n,h in files.items()),'recovery_stage_actual_public_bytes')
    print(canonical({'endpoint':'mac','public_files_verified':len(files),'source_inventory_sha256':sha(runtime['source_files']),
        'candidate_spec_sha256':runtime['spec_sha256'],'candidate_runtime_sha256':sha(runtime),'execution_ready':False,
        'state_or_grants_created':False,'model_or_rhino_calls':0,'old_global_history_writes':0}).decode())
if __name__=='__main__':main()
