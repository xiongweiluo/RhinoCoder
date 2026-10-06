"""Closed aggregate progress only. Never opens task/cipher/key/raw evidence.

History is immutable; current pointer is atomically replaced. Missing progress
after permanent started means UNKNOWN, never permission to restart a study.
"""
from __future__ import annotations

import math
import os
import secrets
import stat

from plugin.rhino_listener.c5_formal20_scope import STUDY_ID
from plugin.rhino_listener.c5_research_channel import private_directory,publish_json,read_json
from plugin.rhino_listener.c5_research_native import canonical,require

PHASES={'started_before_private_loader','owner_private_loader_started','preparing_adapters',
    'route_slot_finished','execution_complete_awaiting_owner_audit','stopped_incomplete_no_replay'}
KEYS={'schema_version','study_id','phase','sequence','started_claim_present','route_slots_required',
    'slots_attempted','slots_finished','confirmed_generation_stages','counters_complete',
    'elapsed_seconds','runtime_freeze_sha256','public_commitment_sha256','formal_execution_authority',
    'private_content_included','replay_allowed','independent_audit_complete'}


def validate_progress(value):
    require(isinstance(value,dict) and set(value)==KEYS and value['schema_version']==1
        and value['study_id']==STUDY_ID and value['phase'] in PHASES
        and value['started_claim_present'] is True and value['route_slots_required']==40,
        'closed public progress schema differs')
    for name,maximum in (('sequence',256),('slots_attempted',40),('slots_finished',40),('confirmed_generation_stages',240)):
        require(type(value[name]) is int and 0<=value[name]<=maximum,'public progress integer bound')
    require(value['slots_finished']<=value['slots_attempted'] and type(value['counters_complete']) is bool
        and type(value['elapsed_seconds']) in (int,float) and math.isfinite(value['elapsed_seconds'])
        and value['elapsed_seconds']>=0,'public progress counters/elapsed differ')
    for name in ('runtime_freeze_sha256','public_commitment_sha256'):
        sha=value[name]
        require(isinstance(sha,str) and len(sha)==64 and all(c in '0123456789abcdef' for c in sha),'public hash required')
    require(all(value[k] is False for k in ('formal_execution_authority','private_content_included',
        'replay_allowed','independent_audit_complete')),'progress is not authority, audit or private disclosure')
    require(len(canonical(value).encode())<=8192,'bounded public progress required')
    return value


def publish_progress(state, *, phase, sequence, slots_attempted, slots_finished, confirmed_generation_stages,
    counters_complete, elapsed_seconds, runtime_freeze_sha256, public_commitment_sha256):
    require((state/'formal20.started.json').is_file(),'progress cannot create or precede formal consumption')
    value=validate_progress({'schema_version':1,'study_id':STUDY_ID,'phase':phase,'sequence':sequence,
        'started_claim_present':True,'route_slots_required':40,'slots_attempted':slots_attempted,
        'slots_finished':slots_finished,'confirmed_generation_stages':confirmed_generation_stages,
        'counters_complete':counters_complete,'elapsed_seconds':elapsed_seconds,
        'runtime_freeze_sha256':runtime_freeze_sha256,'public_commitment_sha256':public_commitment_sha256,
        'formal_execution_authority':False,'private_content_included':False,'replay_allowed':False,
        'independent_audit_complete':False})
    publish_json(state,'formal20.public-%04d.json'%sequence,value)
    fd=private_directory(state);temporary='public-progress-'+secrets.token_hex(12)+'.tmp'
    try:
        try:
            current=os.stat('public-progress.json',dir_fd=fd,follow_symlinks=False)
            require(stat.S_ISREG(current.st_mode) and current.st_uid==os.getuid()
                and stat.S_IMODE(current.st_mode)==0o600,'current public metadata identity differs')
        except FileNotFoundError:pass
        out=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        with os.fdopen(out,'wb') as stream:stream.write((canonical(value)+'\n').encode());stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,'public-progress.json',src_dir_fd=fd,dst_dir_fd=fd);os.fsync(fd)
    finally:
        try:os.unlink(temporary,dir_fd=fd)
        except FileNotFoundError:pass
        os.close(fd)
    return value


def read_public_progress(state):
    if (state/'public-progress.json').exists():
        return validate_progress(read_json(state,'public-progress.json'))
    started=(state/'formal20.started.json').exists()
    return {'study_id':STUDY_ID,'status':'progress_missing_after_started_unknown_no_replay' if started
        else 'formal20_not_started_no_execution_authority','started_claim_present':started,
        'slots_attempted':None if started else 0,'confirmed_generation_stages':None if started else 0,
        'formal_execution_authority':False,'private_content_included':False,'replay_allowed':False}
