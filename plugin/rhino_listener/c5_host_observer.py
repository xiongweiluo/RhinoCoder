"""Bounded one-use observation journal, injected backend, Python 3.9.

No CLR/Rhino/model import. Entry owns exact human authority and started claim.
This measures observable surfaces/events, never causal or emitted-byte proof.
"""
from __future__ import annotations

import threading
import time

from .c5_research_channel import publish_json
from .c5_research_native import canonical, digest, require

PROBE_ID = 'C5OBS-HOSTPROV-20261006-A'
SNAPSHOT_KEYS = {'process_identity', 'python_origins', 'assemblies', 'native_images',
    'active_sha256', 'active_serial', 'active_object_count', 'inspection_limits'}


class ObservationJournal:
    def __init__(self, state, freeze_sha, *, clock=time.monotonic):
        self.state, self.freeze, self.clock = state, freeze_sha, clock
        self.genesis = digest({'probe_id':PROBE_ID,'runtime_freeze_sha256':freeze_sha})
        self.head, self.sequence, self.start = self.genesis, 0, clock()
        self.lock, self.sealed = threading.RLock(), False

    def append(self, kind, payload):
        with self.lock:
            require(not self.sealed and self.sequence < 128, 'observer journal exhausted or sealed')
            require(kind in {'begin','subscribe_attempt','subscribed','snapshot','events','canary_action',
                'detach_attempt','detached','failure','finished'}, 'observer record kind differs')
            elapsed = self.clock()-self.start
            require(elapsed >= 0 and isinstance(payload,dict), 'invalid observer payload/clock')
            record = {'schema_version':1,'probe_id':PROBE_ID,'runtime_freeze_sha256':self.freeze,
                'sequence':self.sequence,'elapsed_seconds':elapsed,'previous_sha256':self.head,
                'kind':kind,'payload':payload}
            record['record_sha256'] = digest(record)
            publish_json(self.state,'observer-%04d.json'%self.sequence,record)
            self.head, self.sequence = record['record_sha256'], self.sequence+1

    def seal(self):
        with self.lock:
            require(not self.sealed, 'observer cannot reseal')
            value = {'schema_version':1,'probe_id':PROBE_ID,'runtime_freeze_sha256':self.freeze,
                'genesis_sha256':self.genesis,'journal_head_sha256':self.head,'record_count':self.sequence,
                'execution_admission_granted':False,'code_bytes_or_causal_origin_proven':False}
            publish_json(self.state,'observer-seal.json',value)
            self.sealed=True
            return {'probe_id':PROBE_ID,'seal_sha256':digest(value),'record_count':self.sequence,
                'journal_head_sha256':self.head,'formal_execution_ready':False}


def validate_snapshot(value):
    require(isinstance(value,dict) and set(value)==SNAPSHOT_KEYS, 'observer snapshot shape differs')
    require(isinstance(value['process_identity'],str) and len(value['process_identity'])==64
        and isinstance(value['active_sha256'],str) and len(value['active_sha256'])==64
        and type(value['active_serial']) is int and type(value['active_object_count']) is int
        and value['active_object_count']==0, 'observer requires empty unchanged active document')
    for name, maximum in (('assemblies',1024),('native_images',4096),('python_origins',4096)):
        require(isinstance(value[name],list) and len(value[name])<=maximum, 'observer snapshot inventory bound')
    require(isinstance(value['inspection_limits'],list) and len(value['inspection_limits'])<=256,
        'bounded explicit reflection limitations required')
    require(len(canonical(value).encode())<=900000, 'observer snapshot exceeds record budget')
    return value


def run_probe(journal, backend, *, guard, clock=time.monotonic, max_seconds=180):
    """One passive subscription, two empty canaries, one empty type; no retry.

    Positive AssemblyLoad plus same-assembly type mutation and a post-detach
    negative sentinel test different mechanisms. None invokes emitted code.
    Backend must mark uncertainty if event removal/inspection is unverifiable.
    """
    start, attempted, detached = clock(), False, False
    failures, baseline = [], None
    def check():
        require(clock()-start < max_seconds, 'observer elapsed cap reached')
        guard()
    def snapshot(phase):
        check()
        value=validate_snapshot(backend.snapshot())
        if baseline is not None:
            require((value['process_identity'],value['active_sha256'],value['active_serial']) ==
                (baseline['process_identity'],baseline['active_sha256'],baseline['active_serial']),
                'observer process or active document changed')
        journal.append('snapshot',{'phase':phase,'value':value})
        return value
    def events(phase):
        batch=backend.drain_events()
        require(isinstance(batch,dict) and set(batch)=={'events','dropped','errors'}
            and isinstance(batch['events'],list) and len(batch['events'])<=256
            and type(batch['dropped']) is int, 'observer event capture shape/bound')
        journal.append('events',{'phase':phase,**batch})
        require(batch['dropped']==0 and batch['errors']==[], 'observer event capture overflow/error')
    journal.append('begin',{'scope':'existing_host_capability_only_not_clean_baseline',
        'no_fixture_model_holdout_or_tool_dispatch':True})
    try:
        check()
        attempted=True
        journal.append('subscribe_attempt',{})
        backend.subscribe()
        journal.append('subscribed',{'handler_installed':True})
        baseline=snapshot('baseline')
        events('baseline')
        check()
        journal.append('canary_action',{'action':'create_subscribed_empty_assembly'})
        backend.create_canary('subscribed')
        snapshot('subscribed_empty')
        events('subscribed_empty')
        check()
        journal.append('canary_action',{'action':'add_one_empty_type_no_method_invocation'})
        backend.add_empty_type()
        snapshot('subscribed_with_type')
        events('subscribed_with_type')
    except BaseException as exc:
        failures.append(type(exc).__name__)
        journal.append('failure',{'error_type':type(exc).__name__,'phase':'observation'})
    finally:
        if attempted:
            journal.append('detach_attempt',{})
            try:
                backend.unsubscribe()
                detached=True
                journal.append('detached',{'remove_call_completed':True})
                # This approved sentinel checks actual callback silence; no
                # self-reported handler flag is promoted to removal proof.
                journal.append('canary_action',{'action':'create_detached_empty_assembly'})
                backend.create_canary('detached')
                snapshot('after_detach_sentinel')
                events('after_detach_sentinel')
            except BaseException as exc:
                failures.append(type(exc).__name__)
                journal.append('failure',{'error_type':type(exc).__name__,'phase':'detach_or_sentinel'})
        journal.append('finished',{'failures':failures,'unsubscribe_call_completed':detached,
            'clean_baseline_claimed':False,'formal_execution_ready':False})
    return journal.seal()
