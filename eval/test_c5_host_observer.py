"""Actual journal/auditor and authority, fake CLR/backend only."""
import copy
import json
from pathlib import Path

import pytest

from plugin.rhino_listener.c5_host_observer import ObservationJournal,run_probe,PROBE_ID
from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_research_native import digest,NativeError
from training.c5_host_observer_audit import audit_observer
from plugin.rhino_listener.c5_host_observer_scope import validate_authority,STATE,BASIS


class Backend:
    def __init__(self):
        self.active=False;self.queue=[];self.assemblies=[];self.types=0
        self.fail_at=None;self.leak=False;self.calls=[];self.snapshots=0;self.dropped=0
    def subscribe(self):self.active=True;self.calls.append('subscribe')
    def unsubscribe(self):
        self.calls.append('unsubscribe')
        if self.fail_at=='unsubscribe':raise RuntimeError('synthetic detach')
        if not self.leak:self.active=False
    def drain_events(self):
        value={'events':copy.deepcopy(self.queue),'dropped':self.dropped,'errors':[]}
        self.queue=[];self.dropped=0;return value
    def create_canary(self,role):
        self.calls.append(role)
        row={'instance_id':role,'name':'synthetic-'+role,'dynamic':True,
            'probe_canary_role':role,'visible_type_count':0,'visible_types':[]}
        row['surface_sha256']=digest(row);self.assemblies.append(row)
        if self.active:self.queue.append({'event':'AssemblyLoad','instance_id':role,'name':'synthetic-'+role,'dynamic':True})
    def add_empty_type(self):
        self.calls.append('type')
        self.assemblies[0]['visible_type_count']=1
        self.assemblies[0]['visible_types']=[{'name':'C5ObserverEmptyType','methods':[]}]
        self.assemblies[0]['surface_sha256']=digest({k:v for k,v in self.assemblies[0].items() if k!='surface_sha256'})
    def snapshot(self):
        self.snapshots+=1
        if self.fail_at=='snapshot':raise RuntimeError('synthetic snapshot')
        return {'process_identity':'1'*64,'python_origins':[{'module':'clr','origin':'unknown'}],
            'assemblies':copy.deepcopy(self.assemblies),'native_images':[],
            'active_sha256':'2'*64,'active_serial':1,'active_object_count':0,
            'inspection_limits':['opaque and DynamicMethods not byte proven']}


def setup(tmp_path, backend=None):
    state=tmp_path/'state';state.mkdir(mode=0o700)
    sha='a'*64
    publish_json(state,'observer.started.json',{'probe_id':PROBE_ID,'runtime_freeze_sha256':sha,'replay_allowed':False})
    backend=backend or Backend()
    receipt=run_probe(ObservationJournal(state,sha),backend,guard=lambda:None)
    return state,sha,receipt,backend


def test_positive_raw_replay_checks_event_type_change_and_detach(tmp_path):
    state,sha,receipt,backend=setup(tmp_path)
    result=audit_observer(state,sha,receipt['seal_sha256'])
    assert result['capability_control_verified']
    assert backend.calls==['subscribe','subscribed','type','unsubscribe','detached']
    assert not backend.active
    for field in ('clean_host_baseline_verified','complete_event_coverage_proven','code_bytes_or_causal_origin_proven',
        'legacy_byte_closure_verified','formal_execution_ready'):
        assert result[field] is False


def test_observer_removal_is_not_self_reported_pass(tmp_path):
    backend=Backend();backend.leak=True
    state,sha,receipt,_=setup(tmp_path,backend)
    with pytest.raises(NativeError,match='callback still active'):audit_observer(state,sha,receipt['seal_sha256'])


@pytest.mark.parametrize('phase',['snapshot','unsubscribe'])
def test_failure_is_retained_detach_attempted_no_replay(tmp_path,phase):
    backend=Backend();backend.fail_at=phase
    state,sha,receipt,_=setup(tmp_path,backend)
    result=audit_observer(state,sha,receipt['seal_sha256'])
    assert result['status']=='observer_incomplete_or_failed_no_replay'
    assert 'unsubscribe' in backend.calls
    with pytest.raises(FileExistsError):run_probe(ObservationJournal(state,sha),Backend(),guard=lambda:None)


@pytest.mark.parametrize('mutation',['event','type','clock','head','extra_record','external_seal','claim'])
def test_independent_raw_tamper_controls(tmp_path,mutation):
    state,sha,receipt,_=setup(tmp_path)
    if mutation=='extra_record':publish_json(state,'observer-0999.json',{'fake':True})
    elif mutation=='external_seal':receipt['seal_sha256']='0'*64
    elif mutation=='claim':
        path=state/'observer.started.json';value=json.loads(path.read_text());value['probe_id']='old-B';path.write_text(json.dumps(value))
    else:
        for path in sorted(state.glob('observer-0*.json')):
            value=json.loads(path.read_text())
            if mutation=='event' and value['kind']=='events' and value['payload']['events']:
                value['payload']['events']=[]
            elif mutation=='type' and value['kind']=='snapshot' and value['payload']['phase']=='subscribed_with_type':
                value['payload']['value']['assemblies'][0]['visible_type_count']=0
            elif mutation=='clock':value['elapsed_seconds']=-1
            elif mutation=='head':value['previous_sha256']='0'*64
            else:continue
            path.write_text(json.dumps(value));break
    with pytest.raises((NativeError,KeyError)):audit_observer(state,sha,receipt['seal_sha256'])


def authority():
    spec={'probe_id':PROBE_ID,'purpose':'existing_host_capability_only_not_clean_baseline','state_root':str(STATE),
        'max_seconds':180,'max_subscriptions':1,'max_canary_assemblies':2,'max_empty_types':1,
        'canary_names':{'subscribed':'C5OBS_20261006_A_SUBSCRIBED','detached':'C5OBS_20261006_A_DETACHED'},
        'canary_access':'Run_noncollectible_until_host_exit','observer_prepared':True,
        **{k:False for k in ('model_allowed','tool_dispatch_allowed','fixture_allowed','holdout_allowed',
            'default_route_change_allowed','legacy_guard_relaxation_allowed','automatic_retry_allowed')}}
    freeze={'probe_id':PROBE_ID,'spec_sha256':digest(spec),'formal_execution_ready':False,
        'complete_runtime_closure_claimed':False}
    grant={'probe_id':PROBE_ID,'actor':'repository_owner','approved':True,'spec_sha256':digest(spec),
        'runtime_freeze_sha256':digest(freeze),'approval_basis':BASIS}
    return spec,freeze,grant


def test_exact_authority_is_required_not_design_permission():
    spec,freeze,grant=authority()
    assert validate_authority(spec,freeze,grant)==digest(freeze)
    with pytest.raises(NativeError):validate_authority(spec,freeze,{'approved':True,'actor':'repository_owner'})


@pytest.mark.parametrize('field,value',[('max_subscriptions',2),('max_canary_assemblies',3),
    ('max_seconds',3600),('max_empty_types',2),('model_allowed',True),('fixture_allowed',True),
    ('holdout_allowed',True),('legacy_guard_relaxation_allowed',True),('state_root','/tmp/fresh'),
    ('purpose','formal20')])
def test_no_scope_expansion_even_with_rehashed_fake_grant(field,value):
    spec,freeze,grant=authority();spec[field]=value
    freeze['spec_sha256']=digest(spec);grant['spec_sha256']=digest(spec);grant['runtime_freeze_sha256']=digest(freeze)
    with pytest.raises(NativeError):validate_authority(spec,freeze,grant)


def test_all_imports_are_lazy_no_installed_rhino_or_clr_required():
    import tools.c5_rhino_host_observer_probe
    import plugin.rhino_listener.c5_host_observer_clr
    assert callable(tools.c5_rhino_host_observer_probe.run)
