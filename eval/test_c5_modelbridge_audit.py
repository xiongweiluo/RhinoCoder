"""CPU-only fake evidence checks; never claim real Rhino/model execution."""
import copy
import hashlib

import pytest

from plugin.rhino_listener.c5_research_channel import publish_json
from plugin.rhino_listener.c5_research_native import NativeError
from tools.c5_modelbridge_client import ActualAtomic
from training.c5_modelbridge_joint_audit import audit_native_trace, semantic
from training.c5_modelbridge_runtime import Budget


def _scene():
    return {'unit':'Millimeters','objects':[],'groups':{}}


def _capture():
    return {'status':'captured','state':{'document_key':'a'*64,'revision':0,'scene_sha256':'b'*64},
            'native':_scene(),'active_sha256':'c'*64}


class _Channel:
    def __init__(self,captures):self.captures=list(captures)
    def control(self,action):
        assert action=='capture'
        return self.captures.pop(0)


def test_signer_proxy_rechecks_live_native_state_each_time():
    original=_capture()
    record={'signing_captures':[]}
    proxy=ActualAtomic(_Channel([copy.deepcopy(original),copy.deepcopy(original)]),original,record)
    assert proxy.snapshot()==original['state']
    assert proxy.semantic_scene()==semantic(original['native'])
    assert len(record['signing_captures'])==2


def test_signer_proxy_refuses_semantic_drift_even_when_state_digest_is_stale():
    original=_capture(); drift=copy.deepcopy(original)
    drift['native']['groups']={'unexpected':[]}
    proxy=ActualAtomic(_Channel([drift]),original,{'signing_captures':[]})
    with pytest.raises(NativeError):proxy.snapshot()


def _publish_trace(root, *, extra=False):
    root.mkdir(mode=0o700)
    capture=_capture()
    close={'status':'closed'};stop={'status':'stopped'}
    record={'capture':capture,'post_model_capture':capture,'signing_captures':[]}
    for index,(action,value) in enumerate((('capture',capture),('capture',capture),('close',close),('stop',stop)),1):
        publish_json(root,'request-%04d.json'%index,
                     {'kind':'control','envelope':{'payload':{'action':action},'signature':'test'}})
        publish_json(root,'response-%04d.json'%index,value)
    if extra:
        publish_json(root,'execute-0005.json',{'status':'done'})
    return record,close,stop


def test_trace_rejects_extra_unaccounted_native_dispatch(tmp_path):
    root=tmp_path/'trace'
    record,close,stop=_publish_trace(root)
    assert audit_native_trace(root,record,None,close,stop)['native_dispatches']==0
    publish_json(root,'execute-0005.json',{'status':'done'})
    with pytest.raises(NativeError):audit_native_trace(root,record,None,close,stop)


def test_trace_rejects_response_tamper(tmp_path):
    root=tmp_path/'trace'
    record,close,stop=_publish_trace(root)
    record['post_model_capture']={**record['capture'],'active_sha256':'d'*64}
    with pytest.raises(NativeError):audit_native_trace(root,record,None,close,stop)


def test_budget_owner_expiry_requires_export_reserve_and_original_cap():
    boundary={'owner_confirmed':True,'provider_expiry_epoch':4000,'hard_stop_epoch':4000,
              'export_reserve_seconds':900,'development_max_seconds':3600,
              'prior_cumulative_seconds':15*3600,'original_cumulative_max_seconds':16*3600}
    clock=[1000.0];monotonic=[50.0]
    budget=Budget(boundary,wall=lambda:clock[0],mono=lambda:monotonic[0])
    assert budget.cap==2100
    clock[0]=3100
    with pytest.raises(NativeError):budget.check()


def test_draft_has_no_model_execution_authority():
    from tools.c5_modelbridge_common import ROOT,STATE
    assert not (ROOT/'eval/c5/modelbridge-runtime-freeze-20261003.json').exists()
    assert not (STATE/'owner-approval.json').exists()
