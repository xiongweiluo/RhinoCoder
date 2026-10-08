"""CPU-only injected process-handle controls. Never opens/signals a process."""
import copy
import ast
import json
from pathlib import Path

import pytest

from tools import c5_formal20_worker_safe_stop as stop


def spec():
    return {'cleanup_id': stop.ID, 'study_id': stop.STUDY, 'retired_runtime_sha256': stop.SHA,
        'source_root': str(stop.SOURCE), 'state_root': str(stop.STATE), 'not_after_epoch': 1791504000,
        'signal': 'SIGTERM', 'signals_max': 1, 'exit_wait_seconds': 30,
        'model_or_holdout_calls_max': 0, 'disk_evidence_modified': False,
        'retry_allowed': False, 'sigkill_allowed': False, 'kernel_trusted_not_byte_proven': True,
        'target': {'pid': 43776, 'uid': 1000, 'start_ticks': 451535,
            'boot_id': 'c8ec6a1e-7d0b-4ef1-bfd3-1e4ed0fe5777',
            'cwd': '/data/RhinoCoder-c5-formal20-v4',
            'argv': ['/data/conda-envs/rhinocoder/bin/python', '-B', '-m',
                     'tools.run_c5_formal20_worker_v2', 'serve'],
            'executable_path': '/data/conda-envs/rhinocoder/bin/python3.11',
            'executable_sha256': '1b473ff72cfa63de341095fa5192c0d030ac06a56c995d77de3626098f81e055'}}


class Fake:
    def __init__(self):
        self.events = []
        self.target = copy.deepcopy(spec()['target'])
        self.guard_count = 0
        self.fail_guard_at = None
        self.already_exited = False
        self.wait_result = True
        self.fail_send = False

    def guard(self):
        self.guard_count += 1
        self.events.append('guard')
        if self.guard_count == self.fail_guard_at:
            raise stop.Refusal()

    def pin(self, pid):
        assert pid == 43776
        self.events.append('pin')
        return 7

    def identity(self, pid):
        self.events.append('identity')
        return self.target

    def exited(self, fd):
        assert fd == 7
        self.events.append('exited')
        return self.already_exited

    def send(self, fd):
        assert fd == 7
        self.events.append('send')
        if self.fail_send:
            raise OSError('private sentinel must never be printed')

    def wait(self, fd, seconds):
        assert (fd, seconds) == (7, 30)
        self.events.append('wait')
        return self.wait_result

    def close(self, fd):
        assert fd == 7
        self.events.append('close')


def journal():
    rows = {}
    def write(name, value):
        if name in rows:
            raise FileExistsError(name)
        rows[name] = copy.deepcopy(value)
    return rows, write


def test_one_signal_pinned_before_identity_and_no_gpu_claim():
    ops = Fake(); rows, write = journal()
    result = stop.stop_once(spec(), ops, write)
    assert ops.events == ['guard', 'pin', 'identity', 'exited', 'guard', 'send', 'wait', 'close']
    assert list(rows) == ['admission.json', 'signal-attempt.json', 'result.json']
    assert result['signals_attempted'] == 1 and result['pidfd_exit_observed'] is True
    assert result['target_absent_from_gpu'] is None and result['model_or_holdout_calls'] == 0
    assert result['status'] == 'target_exit_observed_pending_independent_gpu_check'


@pytest.mark.parametrize('field', ['pid','uid','start_ticks','boot_id','cwd','argv',
                                  'executable_path','executable_sha256'])
def test_identity_drift_or_reused_pid_never_signalled(field):
    ops = Fake(); rows, write = journal()
    ops.target[field] = 'different'
    result = stop.stop_once(spec(), ops, write)
    assert result['signals_attempted'] == 0 and 'send' not in ops.events
    assert 'signal-attempt.json' not in rows and ops.events[-1] == 'close'


@pytest.mark.parametrize('field,value', [('signal','SIGKILL'),('signals_max',2),
    ('signals_max',True),('exit_wait_seconds',31),('model_or_holdout_calls_max',1),
    ('retry_allowed',True),('sigkill_allowed',True),('disk_evidence_modified',True),
    ('state_root','/data/other'),('retired_runtime_sha256','0'*64),('not_after_epoch',1791504001)])
def test_scope_expansion_rejected_before_effects(field, value):
    s=spec();s[field]=value;ops=Fake();rows,write=journal()
    with pytest.raises(stop.Refusal):stop.stop_once(s,ops,write)
    assert not rows and not ops.events


def test_duplicate_admission_cannot_create_result_or_signal():
    ops=Fake();rows,write=journal();write('admission.json',{'old_unknown':True})
    with pytest.raises(FileExistsError):stop.stop_once(spec(),ops,write)
    assert list(rows)==['admission.json'] and ops.events==['guard']


@pytest.mark.parametrize('after_pin', [False,True])
def test_guard_failure_before_signal(after_pin):
    ops=Fake();ops.fail_guard_at=2 if after_pin else 1;rows,write=journal()
    if after_pin:
        result=stop.stop_once(spec(),ops,write)
        assert result['signals_attempted']==0 and ops.events[-1]=='close'
    else:
        with pytest.raises(stop.Refusal):stop.stop_once(spec(),ops,write)
        assert not rows
    assert 'send' not in ops.events


def test_already_exited_no_signal_and_unknown_send_never_retried():
    ops=Fake();ops.already_exited=True;rows,write=journal()
    assert stop.stop_once(spec(),ops,write)['signals_attempted']==0
    assert 'send' not in ops.events
    ops=Fake();ops.fail_send=True;rows,write=journal()
    result=stop.stop_once(spec(),ops,write)
    assert result['signals_attempted']==1 and ops.events.count('send')==1
    assert result['status']=='refused_or_unknown_no_retry'
    assert 'private sentinel' not in json.dumps(result) and 'wait' not in ops.events


def test_timeout_no_second_signal_no_kill_and_no_exit_claim():
    ops=Fake();ops.wait_result=False;rows,write=journal()
    result=stop.stop_once(spec(),ops,write)
    assert result['status']=='termination_unconfirmed_no_retry'
    assert result['signals_attempted']==1 and result['pidfd_exit_observed'] is False
    assert ops.events.count('send')==1 and result['target_absent_from_gpu'] is None


def test_publish_never_overwrites_or_follows_symlink(tmp_path):
    tmp_path.chmod(0o700);stop.publish(tmp_path,'record.json',{'first':True})
    with pytest.raises(FileExistsError):stop.publish(tmp_path,'record.json',{'second':True})
    assert json.loads((tmp_path/'record.json').read_bytes())=={'first':True}
    (tmp_path/'link.json').symlink_to(tmp_path/'record.json')
    with pytest.raises(FileExistsError):stop.publish(tmp_path,'link.json',{})
    with pytest.raises(stop.Refusal):stop.publish(tmp_path,'../escape.json',{})


def test_source_has_no_bare_pid_or_group_signal_or_child_killer():
    source=Path(stop.__file__).read_text()
    tree=ast.parse(source)
    attrs={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not {'kill','killpg','SIGKILL','Popen'} & attrs
    imports={node.name for node in ast.walk(tree) if isinstance(node,ast.alias)}
    assert not {'ctypes','subprocess','torch','transformers','Rhino'} & imports
    assert 'signal.pidfd_send_signal(fd, signal.SIGTERM, None, 0)' in source
