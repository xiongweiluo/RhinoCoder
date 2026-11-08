"""Fixed-output provider tests; no model/native calls or historical state."""
import contextlib
import hashlib
import json

import pytest

from plugin.rhino_listener.c5_research_native import NativeError
from training.lora_development_peer import DevelopmentPeer
from training.lora_development_read_permission import issue_read
from training.c5_formal20_plan import _schemas
from training.lora_development_wire import reparse_response, request_from_host
from eval.test_lora_development_wire import (BINDING, IDENTITY, RUNTIME, SECRET, VIEWS,
    TextTokenizer, first, second)


def setup_peer(tmp_path, *, invalid=False, fail_after_raw=False):
    tmp_path.chmod(0o700)
    calls = []
    routes = []
    def generate(prompt, stage):
        calls.append(stage)
        raw = ('invalid' if invalid else '{"tool":null}')
        return {'raw': raw, 'tokens': 5, 'seconds': .01,
                'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                'output_sha256': hashlib.sha256(raw.encode()).hexdigest()}
    @contextlib.contextmanager
    def route(name):
        routes.append(('enter', name))
        try: yield
        finally: routes.append(('exit', name))
    def guard():
        if fail_after_raw and calls: raise TimeoutError('synthetic post-generation deadline')
    def factory():
        return DevelopmentPeer(state=tmp_path, runtime=RUNTIME, views=VIEWS,
            identities={'base': IDENTITY, 'current_lora': IDENTITY}, tokenizer=TextTokenizer(),
            generate=generate, route_context=route, guard=guard)
    return factory, calls, routes


def test_response_raw_evidence_and_reopened_replay_refusal(tmp_path):
    factory, calls, routes = setup_peer(tmp_path)
    sent = first()
    result = factory().infer(sent)
    observed = reparse_response(result, sent, model_views=VIEWS, runtime=RUNTIME,
                                 identity=IDENTITY, tokenizer=TextTokenizer())
    assert observed['status'] == 'abstained_no_dispatch'
    assert calls == ['selector'] and routes == [('enter', 'base'), ('exit', 'base')]
    assert len(list(tmp_path.glob('*.intent.json'))) == len(list(tmp_path.glob('*.raw.json'))) == 1
    with pytest.raises(FileExistsError): factory().infer(sent)
    assert calls == ['selector']


def test_ordinary_parse_failure_retained_and_other_cell_can_continue(tmp_path):
    factory, calls, routes = setup_peer(tmp_path, invalid=True)
    peer = factory()
    assert peer.infer(first('lora-dev-00'))['observation']['status'] == 'selector_contract_failure_no_dispatch'
    assert peer.infer(first('lora-dev-01'))['observation']['status'] == 'selector_contract_failure_no_dispatch'
    assert calls == ['selector', 'selector']
    assert routes[-2:] == [('enter', 'current_lora'), ('exit', 'current_lora')]


def test_post_generation_failure_preserves_raw_and_blocks_further_work(tmp_path):
    factory, calls, routes = setup_peer(tmp_path, fail_after_raw=True)
    peer = factory()
    with pytest.raises(TimeoutError): peer.infer(first())
    assert len(list(tmp_path.glob('*.raw.json'))) == 1
    failure = json.loads(next(tmp_path.glob('*.failure.json')).read_text())
    assert failure == {'error_type': 'TimeoutError', 'raw_return_retained': True}
    assert routes == [('enter', 'base'), ('exit', 'base')]
    with pytest.raises(NativeError): peer.infer(first('lora-dev-03'))
    assert calls == ['selector']


def test_worker_rejects_second_step_without_its_own_prior_evidence(tmp_path):
    factory, calls, _ = setup_peer(tmp_path)
    _, _, args = second()
    with pytest.raises(FileNotFoundError): factory().infer(request_from_host(**args))
    assert not calls


def test_new_read_handoff_binds_candidate_input_and_late_ttl_without_repair(tmp_path):
    tmp_path.chmod(0o700)
    sent, observation, args = second()
    current = args['capture']['payload']['value']
    envelope = issue_read(sent=sent, observation=observation, current=current, secret=SECRET,
        schemas=_schemas(), max_reads=2, used_reads=0, state=tmp_path, clock=lambda: 12345)
    assert envelope['payload']['expires_at'] == 12465
    assert envelope['payload']['operation'] == observation['name']
    assert envelope['payload']['consent_row_sha256'] is None
    with pytest.raises(FileExistsError):
        issue_read(sent=sent, observation=observation, current=current, secret=SECRET,
            schemas=_schemas(), max_reads=2, used_reads=0, state=tmp_path, clock=lambda: 12346)


def test_zero_read_permission_refuses_before_handoff(tmp_path):
    tmp_path.chmod(0o700)
    sent, observation, args = second()
    with pytest.raises(NativeError):
        issue_read(sent=sent, observation=observation, current=args['capture']['payload']['value'], secret=SECRET,
            schemas=_schemas(), max_reads=0, used_reads=0, state=tmp_path)
    assert not list(tmp_path.iterdir())
