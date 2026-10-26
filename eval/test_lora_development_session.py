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
