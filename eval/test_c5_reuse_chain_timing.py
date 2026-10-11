"""Whole native chain and GPU phase windows; no actual model or host calls."""
import pytest
from training.c5_reuse_gpu_supervisor import Watchdog,PACKET
from plugin.rhino_listener.c5_reuse_field_scope import LIMITS
from eval.test_c5_reuse_native_handoff import setup


def test_native_gap_is_bounded_separately_without_extending_whole_model_request():
    clock=[100.];w=Watchdog(100,3600,clock=lambda:clock[0],limits=LIMITS)
    def feed(kind,now):clock[0]=now;w.feed(PACKET.pack(kind,now))
    assert w.deadline==700
    feed(b'L',200);feed(b'B',201);assert w.deadline==801
    feed(b'R',500);assert w.deadline==680
    feed(b'S',501);feed(b'E',600);feed(b'S',601);feed(b'E',650)
    assert w.deadline==680
    feed(b'D',651);assert w.deadline==3700
    clock[0]=1200;w.check()  # Known native/close/open chain may exceed 180.
    feed(b'R',1300);assert w.deadline==1480
    clock[0]=1480
    with pytest.raises(ValueError,match='watchdog_deadline'):w.check()


@pytest.mark.parametrize('change',['before_begin','double_begin','startup_late','whole_cap'])
def test_phase_evidence_cannot_fake_begin_or_unbound_residency(change):
    clock=[100.];w=Watchdog(100,3600,clock=lambda:clock[0],limits=LIMITS)
    if change=='startup_late':
        clock[0]=700
        with pytest.raises(ValueError):w.feed(PACKET.pack(b'L',700))
        return
    w.feed(PACKET.pack(b'L',100))
    if change=='before_begin':
        with pytest.raises(ValueError):w.feed(PACKET.pack(b'R',100))
        return
    w.feed(PACKET.pack(b'B',100))
    if change=='double_begin':
        with pytest.raises(ValueError):w.feed(PACKET.pack(b'B',100))
        return
    w.feed(PACKET.pack(b'R',100));w.feed(PACKET.pack(b'D',100));clock[0]=3700
    with pytest.raises(ValueError):w.check()


def test_retained_signer_fresh_captures_may_legitimately_exceed_one_native_ack_window(tmp_path):
    h,sent,result,before,capture,gate,backend,atomic,info,mr,gr,directory=setup(tmp_path,'read-lora')
    clock=[0.]
    h.clock=lambda:clock[0];h.epoch=gate.clock=lambda:100+clock[0]
    original=capture
    def capture():clock[0]+=35;return original()
    def execute(signed):clock[0]+=20;return gate.execute(signed)
    try:
        receipt=h.execute(sent,result,before,capture,execute,b'x'*32)
        assert receipt['status']=='done' and 120<clock[0]<LIMITS['handoff_read_seconds']
        assert len(backend.calls)==1
        with pytest.raises(ValueError,match='no_reissue'):h.execute(sent,result,before,capture,execute,b'x'*32)
    finally:mr.close();gr.close()


def test_source_guard_finishing_past_handoff_deadline_is_not_accepted(tmp_path):
    h,sent,result,before,capture,gate,backend,atomic,info,mr,gr,directory=setup(tmp_path,'read-lora')
    clock=[0.];h.clock=lambda:clock[0]
    def late_guard():clock[0]=LIMITS['handoff_read_seconds']
    h.guard=late_guard
    try:
        with pytest.raises(ValueError,match='native_deadline'):h.execute(sent,result,before,capture,gate.execute,b'x'*32)
        assert not backend.calls and h.blocked
    finally:mr.close();gr.close()
