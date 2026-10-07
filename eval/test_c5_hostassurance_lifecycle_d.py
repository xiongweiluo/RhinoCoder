"""CPU synthetic clocks, I/O, SQLite and fake Rhino. No actual field calls."""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

from plugin.rhino_listener.c5_lifecycle_deadlines import PhaseClock
from training.c5_lifecycle_timing_audit import audit_phase, digest
from training.c5_lifecycle_joint_audit import audit_native_timing
from plugin.rhino_listener.c5_hostassurance_development_scope_d import ID, SPEC, TRANSITION, CONSENT, public, authority
from plugin.rhino_listener.c5_host_assurance_session_d import APPROVAL_BASIS
from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.c5_research_native import NativeError

ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):
        self.now = 0
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


def records():
    s = copy.deepcopy(public(ROOT, SPEC))
    f = {"study_id": ID, "probe_id": ID, "execution_ready": True, "spec_sha256": digest(s),
        "host_assurance": s["host_assurance"], "lifecycle_protocol": s["lifecycle_protocol"],
        "model_identities": {"base": "63f7de2f37a997c829ec98eaf617cdc78808586bc9df1139a90c030c4d76ebae",
                             "lora": s["adapter_sha256"]},
        "legacy_byte_closure_verified": False, "formal_execution_ready": False,
        "missing_metadata_files": ["pip:../../../bin/pip3.13"],
        "resource_boundary": {"owner_confirmed": True, "hard_stop_epoch":1791489600,
            "provider_expiry_epoch":1791489600,"export_reserve_seconds":900,
            "development_max_seconds":2470,"prior_cumulative_seconds":8329.012193825008,
            "original_cumulative_max_seconds":57600}}
    a = {"study_id":ID,"actor":"repository_owner","approved":True,
         "spec_sha256":digest(s),"runtime_freeze_sha256":digest(f),"approval_basis":APPROVAL_BASIS}
    return s,f,a,public(ROOT,TRANSITION),public(ROOT,CONSENT)


def rebind(s, f, a):
    f["spec_sha256"] = a["spec_sha256"] = digest(s)
    a["runtime_freeze_sha256"] = digest(f)


def test_inert_D_scope_same_models_and_new_bounded_lifecycle():
    assert authority(*records(), check_time=False)["study_id"] == ID
    import tools.c5_rhino_hostassurance_dev_d as entry
    import tools.c5_hostassurance_dev_client_d as client
    import tools.run_c5_hostassurance_dev_worker_d as worker
    from plugin.rhino_listener.c5_hostassurance_development_scope_d import REMOTE_SOURCE, REMOTE_STATE
    assert callable(entry.start) and not hasattr(entry, "ENTRY_RETURN_BARRIER")
    assert str(REMOTE_SOURCE) == client.REMOTE_SOURCE == str(worker.SOURCE)
    assert str(REMOTE_STATE) == client.REMOTE_STATE == str(worker.STATE)
    assert worker.ID == client.ID == ID


@pytest.mark.parametrize("mutation", ["C_grant","prepare_grant","agent","int_approve","late_cap",
    "settle_cap","no_completion","no_post_decode","cache","changed_model","old_lease",
    "old_dev_budget","bool_budget","nan_prior","bool_tool_policy","bool_holdout"])
def test_rehashed_wrong_scope_or_guarantee_cannot_run(mutation):
    s,f,a,t,c = records()
    if mutation=="C_grant": a["study_id"]="C5DEV-HOSTASSURANCE-20261007-C"
    elif mutation=="prepare_grant":a["approval_basis"]="prepare only"
    elif mutation=="agent":a["actor"]="codex"
    elif mutation=="int_approve":a["approved"]=1
    elif mutation in {"late_cap","settle_cap","no_completion","no_post_decode","cache"}:
        k={"late_cap":"native_ack_seconds","settle_cap":"settle_seconds",
           "no_completion":"post_publication_service_record_required",
           "no_post_decode":"full_decode_validation_in_window","cache":"source_checks_retained_without_cache"}[mutation]
        s["lifecycle_protocol"][k]=121 if mutation=="late_cap" else 61 if mutation=="settle_cap" else False
    elif mutation=="changed_model":s["adapter_sha256"]="f"*64
    elif mutation=="old_lease":f["resource_boundary"]["hard_stop_epoch"]=1791392400
    elif mutation=="old_dev_budget":f["resource_boundary"]["development_max_seconds"]=3104
    elif mutation=="bool_budget":f["resource_boundary"]["development_max_seconds"]=True
    elif mutation=="nan_prior":f["resource_boundary"]["prior_cumulative_seconds"]=float("nan")
    elif mutation=="bool_tool_policy":s["slot_policies"]["write-base"]["max_writes"]=True
    elif mutation=="bool_holdout":s["holdout_calls"]=False
    with pytest.raises((ValueError, TypeError, NativeError)):
        rebind(s,f,a)
        authority(s,f,a,t,c,check_time=False)


@pytest.mark.parametrize("cap", [True, 0, -1, float("nan"), float("inf"), 181])
def test_nonfinite_or_unbounded_phase_rejected(cap):
    with pytest.raises(ValueError):
        PhaseClock(cap)


def test_expensive_completion_past_deadline_is_not_success_or_retried():
    clock = Clock(); phase = PhaseClock(60, clock=clock); calls=[]
    def once():
        calls.append(1);clock.advance(61);return "done"
    with pytest.raises(ValueError):
        phase.call("capture",once)
    assert calls==[1]
    assert phase.receipt()["completed_in_budget"] is False


def test_many_polls_do_not_exhaust_trace_or_drop_deadline_checks():
    clock=Clock();phase=PhaseClock(120,clock=clock)
    for _ in range(1000):
        clock.advance(.05);phase.check("poll",record=False)
    assert len(phase.events)==1
    clock.advance(71)
    with pytest.raises(ValueError):phase.check("poll",record=False)


def timing(role="native",cap=120):
    clock=Clock();p=PhaseClock(cap,clock=clock);clock.advance(20)
    return p.receipt(role=role,sequence=1,runtime_freeze_sha256="a"*64,
        request_sha256=digest({"x":1}),response_sha256=digest({"status":"done"}))


@pytest.mark.parametrize("key,value", [("completed_in_budget",1),("hard_preemption_proven",True),
    ("execution_success_claimed",True),("request_sha256","f"*64),("sequence",True),
    ("cap_seconds",121),("elapsed_seconds",float("nan"))])
def test_independent_phase_audit_rejects_forged_completion(key,value):
    p=timing();p[key]=value
    with pytest.raises(ValueError):
        audit_phase(p,role="native",sequence=1,freeze_sha="a"*64,request={"x":1},
                    response={"status":"done"},cap=120)


def new_bridge(tmp_path,monkeypatch):
    from eval.test_c5_research_gate import fixture
    from eval.test_c5_research_session import Event
    from plugin.rhino_listener import c5_research_session as old
    from plugin.rhino_listener.c5_hostassurance_lifecycle_hub_d import LifecycleBridgeD
    backend,atomic,gate=fixture(tmp_path)
    backend.serial,backend.active_serial,backend.initial_active_sha,backend.closed=2,1,"e"*64,False
    def close():
        backend.closed=True
        return {"fixture_registry_absent":True}
    backend.close=close
    rhino=SimpleNamespace(RhinoApp=SimpleNamespace(IsOnMainThread=True,Idle=Event()),
        RhinoDoc=SimpleNamespace(ActiveDoc=SimpleNamespace(RuntimeSerialNumber=1)))
    monkeypatch.setitem(sys.modules,"Rhino",rhino)
    monkeypatch.setattr(old,"active_content_digest",lambda _:"e"*64)
    root=tmp_path/"channel";root.mkdir(mode=0o700)
    publish_json(root,"handoff.key",{"key_hex":(b"x"*32).hex()})
    clock=Clock();assurance=SimpleNamespace(head="f"*64,sequence=1)
    def guard():
        clock.advance(6.4);assurance.sequence+=1
        return "f"*64
    bridge=LifecycleBridgeD(gate,root,key_name="handoff.key",source_sha256="f"*64,
        guard_source=guard,cleanup_source=guard,assurance=assurance,
        lifecycle={"native_ack_seconds":120,"settle_seconds":60},clock=lambda:100,monotonic=clock)
    bridge.attach()
    return backend,atomic,bridge,clock


def test_expensive_source_and_three_settles_one_write_with_raw_completion(tmp_path,monkeypatch):
    from eval.test_c5_research_gate import envelope
    backend,atomic,bridge,clock=new_bridge(tmp_path,monkeypatch)
    req={"kind":"execute","envelope":envelope(atomic)}
    publish_json(bridge.directory,"request-0001.json",req);bridge.tick()
    for _ in range(3):bridge.tick()
    reply=read_json(bridge.directory,"response-0001.json")
    assert reply["stable_idle_samples"]==3 and backend.calls==["create_box"]
    service=read_json(bridge.directory,"service-time-0001.json")
    settled=read_json(bridge.directory,"settle-time-0001.json")
    audit_phase(service,role="native",sequence=1,freeze_sha="a"*64,request=req,response=reply,cap=120)
    audit_phase(settled,role="settle",sequence=1,freeze_sha="a"*64,request=req,response=reply,cap=60)
    assert settled["elapsed_seconds"] > 15 and not service["hard_preemption_proven"]


def test_post_publication_settle_timeout_never_promotes_written_done(tmp_path,monkeypatch):
    from eval.test_c5_research_gate import envelope
    import plugin.rhino_listener.c5_hostassurance_lifecycle_hub_d as d
    backend,atomic,bridge,clock=new_bridge(tmp_path,monkeypatch)
    original=d.publish_json
    def slow(directory,name,value):
        original(directory,name,value)
        if name=="response-0001.json":clock.advance(61)
    monkeypatch.setattr(d,"publish_json",slow)
    publish_json(bridge.directory,"request-0001.json",{"kind":"execute","envelope":envelope(atomic)})
    bridge.tick();bridge.tick();bridge.tick()
    with pytest.raises(Exception):bridge.tick()
    assert backend.calls==["create_box"] and bridge.blocked
    assert read_json(bridge.directory,"response-0001.json")["status"]=="done"
    assert read_json(bridge.directory,"service-time-0001.json")["completed_in_budget"] is False


def test_native_client_requires_both_reply_and_complete_peer_timing(tmp_path,monkeypatch):
    import tools.c5_hostassurance_dev_client_d as client
    root=tmp_path/"wire";root.mkdir(mode=0o700);clock=Clock();req={"payload":"synthetic"};reply={"status":"captured"}
    original=client.publish_json
    def peer(directory,name,value):
        original(directory,name,value)
        if name=="request-0001.json":
            publish_json(root,"response-0001.json",reply)
            # This raw reply exists, but no peer completion proof. It must
            # expire once, never be consumed or trigger another send.
    monkeypatch.setattr(client,"publish_json",peer)
    c=client.Channel(root,b"x"*32,"a"*64,clock=clock,sleep=lambda _:clock.advance(121))
    with pytest.raises(ValueError):c.exchange(req)
    assert c.unresolved and c.seq==1
    with pytest.raises(Exception):c.exchange(req)
    assert len(list(root.glob("request-*.json")))==1


def test_client_fake_native_joint_chain_executes_once_closes_and_stops(tmp_path,monkeypatch):
    from eval.test_c5_research_gate import envelope
    from eval.test_c5_research_session import control
    import tools.c5_hostassurance_dev_client_d as client
    backend,atomic,bridge,clock=new_bridge(tmp_path,monkeypatch)
    original=client.publish_json
    def peer(directory,name,value):
        original(directory,name,value)
        if name.startswith("request-"):
            bridge.tick()
            while bridge.pending is not None:
                bridge.tick()
    monkeypatch.setattr(client,"publish_json",peer)
    channel=client.Channel(bridge.directory,b"x"*32,"a"*64,clock=clock,sleep=clock.advance)
    req={"kind":"execute","envelope":envelope(atomic)}
    assert channel.exchange(req)["status"]=="done"
    assert channel.exchange(control("close"))["status"]=="closed"
    assert channel.exchange(control("stop"))["status"]=="stopped"
    assert backend.calls==["create_box"] and backend.closed and bridge.stopped
    assert not (bridge.directory/"handoff.key").exists()
    assert audit_native_timing(bridge.directory,"a"*64)["native_requests_with_complete_timing"]==3


def test_client_rejects_decode_overrun_before_consumption(tmp_path,monkeypatch):
    import tools.c5_hostassurance_dev_client_d as client
    root=tmp_path/"decode";root.mkdir(mode=0o700);clock=Clock();req={"x":1};reply={"status":"captured"}
    original=client.publish_json
    def peer(directory,name,value):
        original(directory,name,value)
        if name=="request-0001.json":
            publish_json(root,"response-0001.json",reply)
            p=PhaseClock(120,clock=clock)
            publish_json(root,"service-time-0001.json",p.receipt(role="native",sequence=1,
                runtime_freeze_sha256="a"*64,request_sha256=digest(req),response_sha256=digest(reply)))
    monkeypatch.setattr(client,"publish_json",peer)
    read=client.read_json
    def slow(directory,name):
        value=read(directory,name)
        if name=="response-0001.json":clock.advance(121)
        return value
    monkeypatch.setattr(client,"read_json",slow)
    c=client.Channel(root,b"x"*32,"a"*64,clock=clock,sleep=clock.advance)
    with pytest.raises(ValueError):c.exchange(req)
    assert c.unresolved and c.seq==1 and not (root/"client-time-0001.json").exists()


@pytest.mark.parametrize("stage",["startup","model"])
def test_model_or_startup_validation_overrun_blocks_without_second_send(monkeypatch,stage):
    import training.c5_lifecycle_model_transport as module
    from training.c5_startup_transport import startup_receipt,StartupReadyPipe
    clock=Clock();ready=startup_receipt("DEV","c"*64,"a"*64,"b"*64,{"base":"d"*64,"lora":"e"*64})
    wire=module.LifecycleReadyPipe(None,ready,model_identities=ready["model_identities"],clock=clock)
    calls=[]
    if stage=="startup":
        def fake(self):
            calls.append(1);clock.advance(181);self.ready=True;return ready
        monkeypatch.setattr(StartupReadyPipe,"wait_ready",fake)
        with pytest.raises(ValueError):wire.wait_ready()
    else:
        wire.ready=True
        def fake(self,sent):
            calls.append(1);return {"synthetic":"raw"}
        def slow(value,sent,identity):
            clock.advance(181);return value
        monkeypatch.setattr(StartupReadyPipe,"exchange",fake)
        monkeypatch.setattr(module,"validate_response",slow)
        with pytest.raises(ValueError):wire.exchange({"route":"base","runtime_freeze_sha256":"c"*64})
    assert wire.blocked and calls==[1]
    with pytest.raises(Exception):
        if stage=="startup":wire.wait_ready()
        else:wire.exchange({"route":"base","runtime_freeze_sha256":"c"*64})
    assert calls==[1]


def test_CPU_real_framed_model_ready_and_full_validation_timing(tmp_path):
    import json,subprocess
    from eval.test_c5_model_transport import session,sent
    from training.c5_startup_transport import startup_receipt
    from training.c5_lifecycle_model_transport import LifecycleReadyPipe
    s,_=session(tmp_path);request=sent();response=s.infer(request)
    ready=startup_receipt("DEV","c"*64,"a"*64,"b"*64,{"base":"d"*64,"lora":"e"*64})
    body="import sys,json; print(sys.argv[1],flush=True); sys.stdin.buffer.readline(); print(sys.argv[2],flush=True)"
    p=subprocess.Popen([sys.executable,"-u","-c",body,json.dumps(ready),json.dumps(response)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        wire=LifecycleReadyPipe(p,ready,model_identities=ready["model_identities"])
        assert wire.wait_ready()==ready
        audit_phase(wire.last_phase,role="startup",sequence=0,freeze_sha="c"*64,request=None,response=ready,cap=180)
        assert wire.exchange(request)==response
        audit_phase(wire.last_phase,role="model",sequence=1,freeze_sha="c"*64,
                    request=request,response=response,cap=180)
        assert wire.last_phase["execution_success_claimed"] is False
    finally:
        p.stdin.close();p.stdout.close();p.stderr.close()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=3)
