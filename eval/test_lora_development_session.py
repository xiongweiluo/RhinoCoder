"""Synthetic UI idle/lifecycle control. No actual Rhino import or callback."""
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_research_channel import publish_json, read_json
from plugin.rhino_listener.lora_development_session import DevelopmentSession


def setup(tmp_path):
    tmp_path.chmod(0o700)
    events = []
    host = SimpleNamespace(current=None, session=None, sequence=1, closed=False, close_attempted=False)
    now = [10]
    allowed = [True]
    def work():
        if now[0] > 1000: raise TimeoutError('synthetic total cutoff')
    value = DevelopmentSession(host, tmp_path, 'a' * 64,
        attach=lambda callback: events.append(('attach', callback)),
        detach=lambda callback: events.append(('detach', callback)),
        work_guard=work, cleanup_guard=lambda: None, idle_allowed=lambda: allowed[0], clock=lambda: now[0])
    return value, host, events, now, allowed


def test_no_ready_until_entry_return_and_unblocked_idle(tmp_path):
    session, host, events, now, allowed = setup(tmp_path)
    session.start(); session.tick()
    assert not (tmp_path / 'host-ready.json').exists()
    session.release(); allowed[0] = False; session.tick()
    assert not (tmp_path / 'host-ready.json').exists()
    allowed[0] = True; session.tick()
    assert read_json(tmp_path, 'host-ready.json')['entry_return_release_observed']
    publish_json(tmp_path, 'shutdown.request.json', {'action': 'shutdown', 'runtime_sha256': 'a' * 64})
    session.tick(); session.tick()
    assert len(events) == 2 and events[0][1] is events[1][1]
    assert read_json(tmp_path, 'host-settlement.json')['status'] == 'host_stopped'


def test_pending_entry_can_be_cancelled_without_exposure(tmp_path):
    session, host, events, now, allowed = setup(tmp_path)
    session.start()
    publish_json(tmp_path, 'shutdown.request.json', {'action': 'shutdown', 'runtime_sha256': 'a' * 64})
    session.tick()
    assert session.stopped and not (tmp_path / 'host-ready.json').exists()


@pytest.mark.parametrize('initial_ready', [False, True])
def test_work_timeout_cancels_queued_open_before_later_idle(tmp_path, initial_ready):
    from plugin.rhino_listener.lora_common_probe import wait_for_host_reply, request_shutdown
    session, host, events, now, allowed = setup(tmp_path)
    calls = []
    host.handle = lambda request: calls.append(request)
    session.start(); session.release()
    if initial_ready:
        session.tick()
        assert (tmp_path/'host-ready.json').exists()
    # A prior ready observation does not guarantee that subsequent Idle runs.
    allowed[0] = False
    publish_json(tmp_path, 'request-0001.json', {'payload': {'request': {'action':'open'}}})
    def pause(seconds):
        now[0] += seconds
        session.tick()
    with pytest.raises(TimeoutError, match='host reply timeout'):
        wait_for_host_reply(tmp_path, 'response-0001.json', 10.1, 'a'*64,
            stop_on_timeout=True, clock=lambda:now[0], pause=pause)
    stop = (tmp_path/'shutdown.request.json').read_bytes()
    request_shutdown(tmp_path, 'a'*64)  # outer cleanup confirms the same record
    assert (tmp_path/'shutdown.request.json').read_bytes() == stop
    allowed[0] = True; session.tick(); session.tick()
    assert calls == [] and host.current is None and session.stopped
    assert not (tmp_path/'response-0001.json').exists()
    assert len(events) == 2 and events[0][1] is events[1][1]
    assert read_json(tmp_path, 'host-settlement.json')['status'] == 'host_stopped'


def test_reply_wait_preserves_response_and_does_not_rebind_shutdown(tmp_path):
    from plugin.rhino_listener.lora_common_probe import wait_for_host_reply, request_shutdown
    from plugin.rhino_listener.c5_research_native import NativeError
    tmp_path.chmod(0o700)
    publish_json(tmp_path,'response-0001.json',{'value':'synthetic'})
    value = wait_for_host_reply(tmp_path,'response-0001.json',1,'a'*64,
        stop_on_timeout=True,clock=lambda:0)
    assert value == {'value':'synthetic'} and not (tmp_path/'shutdown.request.json').exists()
    with pytest.raises(TimeoutError):
        wait_for_host_reply(tmp_path,'host-settlement.json',0,'a'*64,
            stop_on_timeout=False,clock=lambda:0)
    assert not (tmp_path/'shutdown.request.json').exists()
    request_shutdown(tmp_path,'a'*64)
    with pytest.raises(NativeError,match='shutdown binding'):
        request_shutdown(tmp_path,'b'*64)


@pytest.mark.parametrize('fault', ['slot_deadline', 'total_deadline', 'close_unknown'])
def test_timeout_disposes_only_owned_fixture_once_and_detaches(tmp_path, fault):
    session, host, events, now, allowed = setup(tmp_path)
    closes = []
    def close():
        closes.append(True)
        if fault == 'close_unknown': raise TimeoutError('synthetic close failed')
        return {'status': 'closed', 'fixture_registry_absent': True}
    host.current, host.session = 'lora-dev-00', SimpleNamespace(close=close, finish=lambda: {'status': 'stopped'})
    session.start(); session.release(); session.slot_started = 10
    now[0] = 2000 if fault == 'total_deadline' else 161
    session.tick(); session.tick()
    result = read_json(tmp_path, 'host-settlement.json')
    assert len(closes) == 1 and len(events) == 2 and host.close_attempted
    assert result['status'] == ('host_cleanup_unknown' if fault == 'close_unknown' else 'host_stopped')
    assert not result['all_other_host_handlers_absent_claimed']
    if fault != 'close_unknown': assert host.current is None and host.session is None
    assert result['failures'][0]['stage'] == 'host_event'
