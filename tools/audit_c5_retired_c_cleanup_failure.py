"""Read-only CPU audit of the retired cleanup A attempt, not a live probe.

No producer validator, Rhino, model or key contents are imported/read. This
checks a fixed development evidence directory only. An unsealed journal
prefix is NOT an externally anchored completed continuity/safety audit.
"""
import hashlib
import json
import math
from pathlib import Path
import sqlite3

STATE = Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-state-20261007-C')
ROOT = Path(__file__).resolve().parents[1]
ID = 'C5SAFE-HOSTASSURANCE-C-20261007-A'
C_ID = 'C5DEV-HOSTASSURANCE-20261007-C'
SPEC_SHA = '1df5aeb6a2e842eee03b6121028572f8efc6c694b210e870de1a1c389c8971bc'
FREEZE_SHA = '3a58cf7aef648ea1aef929aad5726a1d1e314ce05506b739c5bf06e15d7dfd9b'
SCRIPT_SHA = 'ea358f7cb79465f86b34a6dff649318e026e1a7b1a47a8e0efbcd4ea60f42b42'
C_FREEZE_SHA = 'bbbbca84474d5cd397f2e011775cb17b50f6f4a7328c6cee339a4aedf13090d1'
C_SOURCE_SHA = 'bd9594c703bf953f5638ba4436a78b20164a6440510de25f64d1077e9c849672'
C_RESULT_SHA = '6093aa3ae6e25f31ecaaad551c368a919d499ff2e6c8aa57d674910295b3c3a9'
POLICY = 'c5-frozen-source-trusted-host-visible-continuity-v2'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    require(path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= 4194304,
            'fixed regular bounded development evidence required')
    def pairs(rows):
        value = {}
        for k, v in rows:
            require(k not in value, 'duplicate evidence field')
            value[k] = v
        return value
    return json.loads(path.read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def verify_prefix(rows, genesis):
    """Pure integrity check, no external witness or completion claim."""
    head, elapsed, kinds = genesis, -1, {}
    for n, row in enumerate(rows):
        require(set(row) == {'schema_version', 'study_id', 'policy_id', 'runtime_freeze_sha256',
                'sequence', 'elapsed_seconds', 'previous_sha256', 'kind', 'payload', 'record_sha256'}
                and row['schema_version'] == 1 and row['sequence'] == n and type(row['sequence']) is int
                and row['kind'] in {'subscribe_attempt', 'subscribed', 'baseline', 'checkpoint',
                                    'cleanup_checkpoint', 'detach_attempt', 'detached', 'failure'}
                and row['study_id'] == C_ID and row['policy_id'] == POLICY
                and row['runtime_freeze_sha256'] == C_FREEZE_SHA
                and row['previous_sha256'] == head
                and row['record_sha256'] == digest({k: v for k, v in row.items() if k != 'record_sha256'}),
                'development journal prefix identity/hash differs')
        t = row['elapsed_seconds']
        require(type(t) in (int, float) and math.isfinite(t) and t >= elapsed,
                'journal monotonic evidence differs')
        elapsed, head = t, row['record_sha256']
        kinds[row['kind']] = kinds.get(row['kind'], 0) + 1
    return head, kinds


def audit():
    spec = read(ROOT/'eval/c5/hostassurance-c-cleanup-spec-20261007.json')
    freeze = read(ROOT/'eval/c5/hostassurance-c-cleanup-runtime-20261007.json')
    require(digest(spec) == SPEC_SHA and digest(freeze) == FREEZE_SHA
            and file_sha(ROOT/'tools/c5_hostassurance_retired_c_cleanup.py') == SCRIPT_SHA,
            'approved cleanup immutable artifacts differ')
    observed_path = STATE/'manual-c-cleanup-attempt-observed.json'
    observed = read(observed_path)
    require(observed['study_id'] == ID and observed['run_click_count'] == 1
            and observed['spec_sha256'] == SPEC_SHA and observed['runtime_freeze_sha256'] == FREEZE_SHA
            and observed['script_sha256'] == SCRIPT_SHA and observed['failing_script_line'] == 138
            and observed['error_message'] == 'actual known empty fixture/active binding differs',
            'captured single-attempt observation differs')
    require(file_sha(STATE/'approved-manual-c-cleanup-wrapper.py') == observed['wrapper_sha256']
            and (STATE/'approved-manual-c-cleanup-wrapper.py').read_bytes() == spec['wrapper_code'].encode(),
            'actual executed wrapper differs')
    approval = read(STATE/'manual-c-cleanup-owner-approval.json')
    require(digest(approval) == digest({'study_id': ID, 'actor': 'repository_owner', 'approved': True,
            'spec_sha256': SPEC_SHA, 'runtime_freeze_sha256': FREEZE_SHA,
            'scope': 'retired C only; known empty read-lora closure, seven ephemeral keys, exact two Idle and one AssemblyLoad detach; no replay'}),
            'separate direct cleanup approval differs')
    require(file_sha(STATE/'result.json') == C_RESULT_SHA, 'original C failure bytes changed')
    result = read(STATE/'result.json')
    require(result['status'] == 'modelbridge_fail_retired_no_replay' and len(result['slots']) == 3
            and result['holdout_calls'] == 0 and result.get('hub_stop') is None, 'original failure changed')
    artifacts = [ID+'.claim.json', 'manual-c-cleanup-result.json', 'manual-c-cleanup-failure.json',
                 'host-continuity-seal.json', 'host-continuity-terminal-receipt.json']
    require(not any((STATE/p).exists() for p in artifacts), 'attempt no longer pre-effect/unsealed')
    keys = ['hub.key'] + [s+'/handoff.key' for s in ('read-lora', 'read-base', 'clarify-base',
            'clarify-lora', 'unsupported-lora', 'unsupported-base')]
    require(all((STATE/p).exists() for p in keys), 'seven exact residual keys differ')
    future = ('read-base', 'clarify-base', 'clarify-lora', 'unsupported-lora', 'unsupported-base')
    require(not any((STATE/(s+'.engine-started.claim.json')).exists() for s in future), 'future slot consumed')
    paths = sorted(STATE.glob('host-continuity-[0-9][0-9][0-9][0-9].json'))
    require([p.name for p in paths] == ['host-continuity-%04d.json' % n for n in range(55)], 'raw prefix population differs')
    rows = [read(p) for p in paths]
    genesis = digest({'study_id': C_ID, 'runtime_freeze_sha256': C_FREEZE_SHA,
                      'policy_id': POLICY, 'source_inventory_sha256': C_SOURCE_SHA})
    head, kinds = verify_prefix(rows, genesis)
    bindings = 0
    for directory, prefix, check_prefix in [(STATE, 'hub-request-', 'hub-host-check-')] + [
            (STATE/s, 'request-', 'host-check-') for s in ('write-base', 'write-lora', 'read-lora')]:
        requests = sorted(directory.glob(prefix+'*.json'))
        require({p.name for p in directory.glob(check_prefix+'*.json')} == {
                check_prefix+p.name[len(prefix):] for p in requests}, 'missing/extra request checkpoint')
        for path in requests:
            request = read(path)
            check = read(directory/(check_prefix+path.name[len(prefix):]))
            require(set(check) == {'request_sha256', 'host_record_sha256', 'host_sequence', 'runtime_freeze_sha256'}
                    and type(check['host_sequence']) is int and 0 <= check['host_sequence'] < len(rows)
                    and check['request_sha256'] == digest(request) and check['runtime_freeze_sha256'] == C_FREEZE_SHA,
                    'raw request checkpoint identity differs')
            row = rows[check['host_sequence']]
            envelope = request.get('envelope', request)
            cleanup = request.get('kind', 'control') == 'control' and envelope['payload'].get('action') in {'close', 'stop'}
            require(row['record_sha256'] == check['host_record_sha256']
                    and row['kind'] == ('cleanup_checkpoint' if cleanup else 'checkpoint')
                    and row['payload']['continuity_error_type'] is None, 'request bypassed original guard')
            bindings += 1
    q = STATE/'read-lora'
    request, response = read(q/'request-0009.json'), read(q/'response-0009.json')
    payload = request['envelope']['payload']
    empty = {'groups': {}, 'objects': [], 'unit': 'Millimeters'}
    require(response['status'] == 'done' and response['payload'] == payload and payload['operation'] == 'get_scene_summary'
            and response['before'] == response['after'] == response['immediate_after'] == response['result'] == empty
            and response['stable_idle_samples'] == 3 and response['result_sha256'] == digest(empty), 'late read evidence differs')
    con = sqlite3.connect((q/'fixture.sqlite3').resolve().as_uri()+'?mode=ro', uri=True)
    try:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        reads = [dict(r) for r in con.execute('SELECT * FROM c5_read')]
        writes = con.execute('SELECT COUNT(*) FROM candidate_write').fetchone()[0]
    finally:
        con.close()
    require(writes == 0 and reads == [{'request_id': payload['request_id'], 'payload_sha256': digest(payload),
            'state': 'done', 'result_sha256': digest(empty)}], 'late read ledger differs')
    bundle_path = STATE/'failed-remote-audit-bundle.json'
    bundle = read(bundle_path)
    require(bundle['study_id'] == C_ID and bundle['runtime_freeze_sha256'] == C_FREEZE_SHA
            and bundle['holdout_rows_read'] == 0 and len(bundle['records']) == len(bundle['record_file_sha256']) == 21,
            'retained development remote population differs')
    return {'study_id': ID, 'status': 'pre_effect_failure_evidence_verified_not_safety_pass',
            'observation_file_sha256': file_sha(observed_path), 'original_result_sha256': C_RESULT_SHA,
            'original_failure_preserved': True, 'cleanup_effect_claim_exists': False,
            'remaining_key_paths': 7, 'key_contents_read_by_auditor': 0, 'future_engine_claims': 0,
            'raw_host_prefix_count': 55, 'raw_host_prefix_head_sha256': head,
            'raw_host_prefix_inventory_sha256': digest({p.name: file_sha(p) for p in paths}),
            'raw_host_kinds': kinds, 'raw_request_checkpoint_bindings': bindings,
            'late_read_done_rows': 1, 'late_read_write_rows': 0, 'late_reply_reclassified_as_timely': False,
            'retained_remote_record_count': 21, 'remote_bundle_sha256': file_sha(bundle_path),
            'host_external_seal_available': False, 'complete_host_continuity_audit_pass': False,
            'live_fixture_registry_absence_verified': False, 'live_delegate_detach_verified': False,
            'safety_cleanup_verified': False, 'formal20_rows_read': 0,
            'specific_live_failed_subcondition_known': False, 'retry_allowed': False,
            'whole_host_zero_effects_proven': False, 'execution_authority': False}


if __name__ == '__main__':
    print(json.dumps(audit(), sort_keys=True))
