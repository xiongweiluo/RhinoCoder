"""Two isolated CPU endpoint namespaces, same master freeze/message identity."""
import copy
from pathlib import Path
import pytest

from eval.test_c5_reuse_field_preparation import records, binding, peer, Tokenizer
from training.c5_reuse_evidence import sha
from training.c5_reuse_field_scope import bind, common_scope
from training.c5_reuse_field_wire import envelope
from training.c5_reuse_admission import AdmissionRegistry
from training.c5_reuse_generation_audit import audit_generation


def test_one_master_freeze_binds_distinct_local_paths_and_cross_endpoint_message(tmp_path):
    p,registry,sent,calls=peer(tmp_path)
    mac=binding(tmp_path,endpoint='mac')
    try:
        assert p.binding['paths'] != mac['paths']
        assert p.binding['runtime_sha256']==mac['runtime_sha256']
        assert common_scope(p.binding)==common_scope(mac)
        cross=envelope(mac,sent['request'])
        assert cross==sent
        returned=p.infer(cross)
        assert returned['scope_sha256']==sha(common_scope(mac))
        audit=audit_generation(p.journal.records,p.binding,p.journal.head,plans=p.plans,tokenizer=Tokenizer())
        assert audit['coverage_complete'] and calls==['selector','invocation']
        with AdmissionRegistry(mac,create=True) as local:
            local.claim('controller')
            assert len(local.audit()['rows'])==1
        assert len(registry.audit()['rows'])==1
    finally: registry.close()


@pytest.mark.parametrize('endpoint,role',[('mac','worker'),('mac','stop'),('gpu','controller'),('gpu','host')])
def test_wrong_endpoint_role_is_rejected_before_consumption(tmp_path,endpoint,role):
    b=binding(tmp_path,endpoint=endpoint)
    with AdmissionRegistry(b,create=True) as registry:
        with pytest.raises(ValueError,match='admission_role'): registry.claim(role)
        assert registry.audit()['rows']==[]


def test_stop_role_can_enter_while_worker_registry_remains_live(tmp_path):
    b=binding(tmp_path)
    with AdmissionRegistry(b,create=True) as worker:
        worker.claim('worker')
        with AdmissionRegistry(b) as stop:
            stop.claim('stop')
        assert {row[1] for row in worker.audit()['rows']}=={'worker','stop'}


@pytest.mark.parametrize('kind',['legacy','missing','source_alias','state_alias','endpoint','local_rebind'])
def test_two_endpoint_paths_cannot_be_missing_legacy_or_cross_rebound(tmp_path,kind):
    spec,runtime,grant,_=records(tmp_path)
    if kind=='legacy': runtime['paths']=runtime.pop('endpoints')['gpu']
    elif kind=='missing': del runtime['endpoints']['mac']
    elif kind=='source_alias': runtime['endpoints']['gpu']['source_root']=runtime['endpoints']['gpu']['state_root']
    elif kind=='state_alias': runtime['endpoints']['mac']['state_root']=runtime['endpoints']['mac']['admission_root']
    elif kind=='local_rebind':
        b=bind(spec,runtime,grant,now=100,endpoint='gpu')
        b['paths']=copy.deepcopy(b['endpoints']['mac'])
        from training.c5_reuse_field_scope import validate_binding
        with pytest.raises(ValueError,match='local_endpoint'): validate_binding(b)
        return
    grant['runtime_sha256']=sha(runtime)
    with pytest.raises(ValueError): bind(spec,runtime,grant,now=100,endpoint='bad' if kind=='endpoint' else 'gpu')
    assert not any(Path(paths['state_root']).exists() for paths in runtime.get('endpoints',{}).values())
