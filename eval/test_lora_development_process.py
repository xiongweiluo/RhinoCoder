"""CPU pipe boundary tests, with no model, SSH or Rhino execution."""
import os
import time
from types import SimpleNamespace

import pytest

from plugin.rhino_listener.c5_research_native import NativeError
from training.lora_development_process import JsonPipe
from training import lora_development_process as module


@pytest.fixture
def pair():
    ar, aw = os.pipe(); br, bw = os.pipe()
    try: yield JsonPipe(ar, bw), JsonPipe(br, aw)
    finally:
        for fd in (ar, aw, br, bw): os.close(fd)


def test_pipe_round_trip_and_multiple_frames(pair):
    first, second = pair
    for n in range(2): first.send({'n': n, 'text': '公开'}, time.monotonic() + 1)
    assert second.receive(time.monotonic() + 1) == {'n': 0, 'text': '公开'}
    assert second.receive(time.monotonic() + 1)['n'] == 1


@pytest.mark.parametrize('raw', [b'{"x":1,"x":2}\n', b'{"x":NaN}\n'])
def test_ambiguous_json_is_refused(pair, raw):
    first, second = pair
    os.write(first.write_fd, raw)
    with pytest.raises((ValueError, NativeError)): second.receive(time.monotonic() + 1)


def test_empty_pipe_does_not_wait_past_deadline(pair):
    with pytest.raises(TimeoutError): pair[0].receive(time.monotonic() + .01)


def test_oversized_send_fails_before_writing(pair):
    with pytest.raises(NativeError): pair[0].send({'x': 'a' * (1024 * 1024)}, time.monotonic() + 1)
    with pytest.raises(TimeoutError): pair[1].receive(time.monotonic() + .01)


def test_pidfd_admission_failure_closes_unreleased_child_without_signalling(monkeypatch):
    events = []
    fake = SimpleNamespace(pid=1234, stdin=SimpleNamespace(close=lambda: events.append('stdin_closed')),
        stdout=SimpleNamespace(close=lambda: events.append('stdout_closed')),
        wait=lambda timeout: events.append(('wait', timeout)))
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: fake)
    def fail(*a): raise OSError('synthetic pidfd unavailable')
    monkeypatch.setattr(module.os, 'pidfd_open', fail, raising=False)
    monkeypatch.setattr(module.signal, 'pidfd_send_signal', lambda *a: pytest.fail('unqualified signal'), raising=False)
    with pytest.raises(OSError):
        module.OwnedChild(['/synthetic/python'], cwd='/tmp', env={}, stderr=None,
                          journal=lambda *a: pytest.fail('child not qualified'))
    assert events == ['stdin_closed', ('wait', 15), 'stdout_closed']
