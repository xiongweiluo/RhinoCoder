"""Sequential public development orchestration with injected, bounded I/O.

No loader, Rhino access, shell command or authority creation. The approved
entry authenticates sources/resources and owns transport deadlines. This
controller never trusts peer parse labels or a claimed native success.
"""
from __future__ import annotations

import time

from plugin.rhino_listener.c5_research_channel import publish_json
from plugin.rhino_listener.c5_research_native import READS, digest, require
from plugin.rhino_listener.lora_development_host import signed_request
from plugin.rhino_listener.lora_development_runtime import failure_record, lifecycle
from training.c5_formal20_plan import validate_fixture_readback
from training.c5_formal20_scorer import AUDIT_KEYS, score_route
from training.c5_modelbridge_joint_audit import semantic
from training.lora_development_cases import build_cases
from training.lora_development_read_permission import issue_read
from training.lora_development_wire import verify_host
from training import lora_development_wire as default_wire


def audit_read(receipt, envelope, observation, before):
    """Verify actual same-document read and its exact authorized result chain."""
    require(receipt.get('status') == 'done' and receipt.get('payload') == envelope['payload']
            and receipt['payload']['operation'] == observation['name']
            and receipt['payload']['arguments'] == observation['arguments']
            and receipt['before_state'] == receipt['after_state'] == before['state']
            and digest(receipt['before']) == digest(receipt['after']) == digest(before['native'])
            and receipt.get('ledger_row') is None
            and receipt['result_sha256'] == digest(receipt['result']), 'native read chain differs')


def audit_ledger(ledger, receipts):
    expected = [{'request_id': r['payload']['request_id'], 'payload_sha256': digest(r['payload']),
                 'state': 'done', 'result_sha256': r['result_sha256']} for r in receipts]
    require(type(ledger) is dict and set(ledger) == {'candidate_write', 'c5_read'}
            and ledger['candidate_write'] == []
            and len({row['request_id'] for row in expected}) == len(expected)
            and sorted(ledger['c5_read'], key=lambda r: r['request_id']) ==
                sorted(expected, key=lambda r: r['request_id']), 'actual read ledger differs')


class DevelopmentController:
    def __init__(self, *, journal, state, runtime, secret, schemas, tokenizer, identities,
                 host, model, guard, cleanup_guard, monotonic=time.monotonic, contract=None):
        self.journal, self.state, self.runtime = journal, state, runtime
        self.secret, self.schemas, self.tokenizer, self.identities = secret, schemas, tokenizer, identities
        self.host, self.model, self.guard, self.cleanup_guard, self.clock = host, model, guard, cleanup_guard, monotonic
        self.sequence = 1
        self.results = []
        self.contract = contract
        require((contract is not None) == journal.common_chain, 'controller/journal contract differs')
        if contract is not None:
            require(contract.directory.parent == self.state.parent == journal.root.parent,
                    'one common evidence root required')
        self.wire = contract.wire if contract is not None else default_wire
        self.cases = contract.cases if contract is not None else {r['case']['family_id']: r['case'] for r in build_cases()}
        if contract is not None: contract.bind_schedule(journal.views['schedule'])

    def exchange(self, slot, action, *, envelope=None):
        if action in {'close', 'stop'}: self.cleanup_guard()
        else:
            self.guard()
            if self.contract is not None: self.contract.work_guard()
        request = {'action': action}
        if envelope is not None: request['envelope'] = envelope
        seq = self.sequence
        self.sequence += 1
        signed = signed_request(self.secret, self.runtime, slot, seq, request)
        publish_json(self.state, 'controller-host-%04d.request.json' % seq, signed)
        returned = self.host(signed)
        publish_json(self.state, 'controller-host-%04d.response.json' % seq, returned)
        value = verify_host(returned, secret=self.secret, runtime=self.runtime, slot=slot, sequence=seq,
                            request=request, study=self.journal.scope['study_id'])
        require(value.get('status') != 'host_failure_no_retry', 'host effect unknown; stop batch')
        return value, {'envelope': returned, 'request': request, 'sequence': seq}

    def run_slot(self, cell):
        slot, case = cell['slot_id'], self.cases[cell['family_id']]
        self.guard()  # Preflight precedes permanent task consumption.
        if self.contract is not None: self.contract.work_guard()
        self.journal.start_slot(slot)
        started = self.clock()
        initial = final = close = stop = None
        steps, receipts = [], []
        error, opened, active_step = None, False, None
        phase, failures = 'slot_preflight', []
        model_requested = model_returned = False
        native_requests = 0
        recovering = self.journal.recovery is not None or self.contract is not None
        def failed(exc, stage):
            nonlocal error
            failures.append(failure_record(exc, stage))
            error = error or type(exc).__name__
        def work():
            self.guard()
            require(self.clock() - started < self.journal.limits['slot_seconds'], 'slot deadline reached')
        try:
            work()
            if self.contract is not None: self.contract.start(slot)
            phase = 'fixture_open'
            opened = True  # Opening may partially create a document before returning.
            value, _ = self.exchange(slot, 'open')
            require(value.get('status') == 'opened', 'new fixture not opened')
            phase = 'initial_capture'
            captured, _ = self.exchange(slot, 'capture')
            require(captured.get('status') == 'captured', 'initial capture missing')
            initial = captured['native']
            phase = 'fixture_validation'
            validate_fixture_readback(case, initial)
            previous = None
            for index in range(case['max_steps']):
                phase = 'step_preflight'
                work()
                current, exchange = self.exchange(slot, 'capture')
                sent = self.wire.request_from_host(model_views=self.journal.views['model'], runtime=self.runtime,
                    slot=slot, step_index=index, secret=self.secret, capture=exchange['envelope'],
                    capture_request=exchange['request'], capture_sequence=exchange['sequence'], previous=previous)
                self.journal.start_step(slot, index)
                active_step = index
                phase = 'model_request'
                model_requested = True; model_returned = False
                returned = self.model(sent)
                model_returned = True
                publish_json(self.state, slot + '-step-%d.model.json' % index, {'request': sent, 'response': returned})
                phase = 'model_verification'
                observed = self.wire.reparse_response(returned, sent, model_views=self.journal.views['model'],
                    runtime=self.runtime, identity=self.identities[cell['route']], tokenizer=self.tokenizer)
                work()
                row = {'observation': observed, 'receipt': None, 'policy_denied': False}
                steps.append(row)
                status = observed['status']
                if status == 'schema_valid_not_authorized':
                    # A legal parse can still violate this task's read-only policy.
                    allowed = (observed['name'] in READS and len(receipts) < case['max_reads']
                        and (observed['name'] != 'get_bounding_box' or observed['arguments']['object_id'] in
                             {o['alias'] for o in sent['scene']['objects']}))
                    if self.contract is not None:
                        allowed = self.contract.allowed(observed, case, receipts, current, self.schemas)
                    if not allowed:
                        row['policy_denied'] = True
                        outcome = 'task_failure'
                    else:
                        before, _ = self.exchange(slot, 'capture')
                        phase = 'permission_issue'
                        handoff = (self.contract.issue(self, slot, sent, observed, case) if self.contract is not None else
                            issue_read(sent=sent, observation=observed, current=before, secret=self.secret,
                            schemas=self.schemas, max_reads=case['max_reads'], used_reads=len(receipts), state=self.state))
                        phase = 'native_dispatch'
                        native_requests += 1  # Intent before dispatch; unknown replies never replay.
                        receipt, executed = self.exchange(slot, 'execute', envelope=handoff)
                        if self.contract is not None: self.contract.audit_receipt(receipt, handoff, observed, before)
                        else: audit_read(receipt, handoff, observed, before)
                        row['receipt'] = receipt
                        receipts.append(receipt)
                        previous = {**executed, 'step_index': index, 'observation': observed}
                        outcome = 'completed_read' if observed['name'] in READS else 'completed_write'
                elif status in {'abstained_no_dispatch', 'unsupported_for_c5_no_dispatch'}:
                    outcome = 'abstained'
                else: outcome = 'task_failure'
                phase = 'step_terminal_record'
                self.journal.finish_step(slot, index, outcome=outcome, evidence_sha256=digest(row))
                active_step = None
                if outcome not in {'completed_read', 'completed_write'}: break
            phase = 'final_capture'
            final_capture, _ = self.exchange(slot, 'capture')
            final = final_capture['native']
            work()
        except BaseException as exc:
            failed(exc, phase)
            if active_step is not None:
                try:
                    self.journal.finish_step(slot, active_step, outcome='unknown',
                        evidence_sha256=digest({'failure': failures[0], 'partial_steps': steps}))
                except BaseException as terminal_error: failed(terminal_error, 'step_terminal_record')
        finally:
            if opened:
                try: close, _ = self.exchange(slot, 'close')
                except BaseException as exc: failed(exc, 'fixture_close')
                if close is not None:
                    try: stop, _ = self.exchange(slot, 'stop')
                    except BaseException as exc: failed(exc, 'fixture_stop')
        closed = bool(close and close.get('status') == 'closed' and close.get('fixture_registry_absent') is True)
        stopped = bool(stop and stop.get('status') == 'stopped' and stop.get('fixture_registry_absent') is True)
        scored, integrity = None, False
        # Cleanup and receipt verification run even when the task failed.
        # They do not convert a failed task into a scored success.
        if error is None or recovering and closed and stopped:
            try:
                require(closed and stopped and stop.get('host_blocked') is False
                        and close.get('readback_error') is None, 'fixture lifecycle differs')
                if self.contract is not None: self.contract.audit_ledger(slot, stop['ledger'], receipts, self.runtime)
                else: audit_ledger(stop['ledger'], receipts)
                self.guard()
                integrity = True
                if error is None:
                    require(digest(close['fixture_before_close_native']) == digest(final), 'fixture final state differs')
                    proof = {k: (0 if k in {'critical_safety_errors', 'duplicate_writes', 'unverified_cleanup'} else True)
                             for k in AUDIT_KEYS}
                    result = {'family_id': cell['family_id'], 'slot_id': slot,
                        'route': 'base' if cell['route'] == 'base' else 'lora', 'steps': steps,
                        'initial_native': initial, 'final_native': final, 'close': 'closed', 'stop': 'stopped'}
                    scored = score_route(case, result, proof)
            except BaseException as exc:
                integrity = False; failed(exc, 'evidence_verification')
        execution = lifecycle(model_requested=model_requested, model_returned=model_returned,
            native_requested=native_requests > 0, native_verified=native_requests == len(receipts) and integrity,
            native_writes=any(r['payload']['operation'] not in READS for r in receipts),
            fixture_attempted=opened, fixture_closed=closed, listener_stopped=stopped, integrity_verified=integrity)
        # Only a local, known pre-model fixture mismatch may continue in this
        # same healthy run. Transport, source and protocol errors stop it.
        local_failure = (recovering and len(failures) == 1 and failures[0]['stage'] == 'fixture_validation'
                         and not model_requested and execution['resume_eligible'])
        stop_requested = error is not None and not local_failure
        evidence = {'cell': cell, 'initial_native': initial, 'final_native': final, 'steps': steps,
            'close': close, 'stop': stop, 'score': scored, 'error_type': error,
            'failures': failures, 'execution': execution, 'stop_current_run': stop_requested,
            'synthetic_or_field_provenance_supplied_by_entry': True}
        if self.contract is not None:
            evidence['slot_elapsed_seconds_including_cleanup'] = self.clock() - started
            evidence['provider_kind'] = 'scripted_probe' if cell['route'] == 'scripted_probe' else 'model'
        publish_json(self.state, slot + '.evidence.json', evidence)
        # A failed execution/evidence channel is an engineering failure, while
        # its effect/cause can remain unknown. It is never relabelled model error.
        outcome = ('engineering_failure' if error else ('success' if scored['outcome_correct'] else 'task_failure'))
        return self.journal.finish_slot(slot, outcome=outcome, fixture_closed=closed, listener_stopped=stopped,
            effect_known=(execution['resume_eligible'] if recovering else error is None),
            stop_requested=stop_requested, evidence_sha256=digest(evidence),
            execution=execution if recovering else None)

    def run(self):
        # Keep the completed prefix visible even if a subsequent journal write
        # or selection seal raises before run() can return.
        rows = self.results
        for index, cell in enumerate(self.journal.views['schedule']):
            if cell['slot_id'] in self.journal.history: continue
            if index == self.journal.selection_boundary: self.journal.seal_selection()
            result = self.run_slot(cell)
            rows.append(result)
            if not result['may_advance']: break
        return rows
