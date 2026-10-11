"""New development peer: durable attempts precede unchanged two-stage contract.

Only injected generation/tokenizer/route providers; no loader or SSH. Formal
tasks are not admitted. The actual frozen worker/host/stop wiring is separate.
"""
import time

from training.c5_reuse_evidence import canonical, exact, raw_sha, require, sha, strict
from training.c5_reuse_field_scope import PROTOCOL, STUDY, validate_binding
from training.c5_reuse_field_journal import FieldJournal, MAX_RECORD
from training.c5_rhino_adapter import invoke_step, step_input
from training.c5_formal20_privacy import allowed
from training.c5_reuse_field_wire import envelope, validate_return



class GenerationPeer:
    def __init__(self, binding, registry, plans, tokenizer, generate, route_context,
                 guard, check_budget, *, clock=time.monotonic):
        validate_binding(binding)
        require(sha(plans) == binding['development_plan_sha256'] and type(plans) is dict
                and 0 < len(plans) <= 40, 'development_plan_binding')
        for slot, p in plans.items():
            exact(p, ('route', 'steps'))
            require(type(slot) is str and p['route'] in ('base','lora') and type(p['steps']) is list
                    and 0 < len(p['steps']) <= 3 and all(type(s) is str for s in p['steps']), 'development_plan_shape')
        guard(); check_budget()
        self.journal = FieldJournal(binding, 'worker', registry)
        self.binding, self.plans, self.tokenizer = strict(canonical(binding)), strict(canonical(plans)), tokenizer
        self.generate, self.context, self.guard, self.check_budget, self.clock = generate, route_context, guard, check_budget, clock
        self.spent, self.completed = set(), {}
        self.stages = 0

    def infer(self, sent):
        require(self.journal.lock.acquire(blocking=False), 'peer_request_already_active')
        try:
            require(not self.journal.blocked, 'peer_retired_no_retry')
            sent = strict(canonical(sent))
            exact(sent, ('protocol', 'scope_sha256', 'request'))
            request = sent['request']
            require(canonical(sent) == canonical(envelope(self.binding, request)), 'peer_envelope_scope')
            slot, step = request['slot_id'], request['step_index']
            p = self.plans.get(slot)
            require(p is not None and request['route'] == p['route'] and 0 <= step < len(p['steps'])
                    and request['task'] == p['steps'][step] and allowed(request['task'], request['scene']),
                    'peer_task_not_in_approved_development_plan')
            key = (slot, step)
            require(key not in self.spent and len(self.spent) < 56
                    and (step == 0 or self.completed.get((slot, step-1)) == 'schema_valid_not_authorized'),
                    'peer_consumed_or_predecessor')
            start = last = self.clock()
            self.guard(); self.check_budget()
            self.journal.blocked = True
            self.spent.add(key)
            self.journal.append('request_intent', {'envelope': sent})
            def guard():
                nonlocal last
                now = self.clock()
                require(last <= now < start + 180, 'peer_complete_generation_deadline')
                last = now
                self.guard(); self.check_budget()
            receipts = []
            def generate(prompt, stage):
                guard()
                require(self.stages < 112, 'peer_generation_capacity')
                intent = {'request_sha256': sha(sent), 'ordinal': self.stages,
                          'stage': stage, 'prompt_raw': prompt, 'prompt_sha256': raw_sha(prompt.encode())}
                self.journal.append('generation_intent', intent)
                self.stages += 1
                try:
                    guard()
                    supplied = self.generate(prompt, stage)
                    if type(supplied) is dict and type(supplied.get('raw')) is str:
                        raw = supplied['raw'].encode()
                        observed = {'request_sha256': sha(sent), 'ordinal': intent['ordinal'],
                                    'raw_hex': raw[:262144].hex(), 'observed_bytes': len(raw),
                                    'truncated': len(raw) > 262144}
                        self.journal.append('generation_raw_observed', observed)
                        require(not observed['truncated'], 'peer_raw_capacity')
                    value = strict(canonical(supplied), limit=MAX_RECORD)
                    validate_return(value, intent['prompt_sha256'], stage)
                    self.journal.append('generation_return', {'request_sha256': sha(sent), 'ordinal': intent['ordinal'], 'raw': value})
                    receipts.append(value)
                    guard()
                    return value
                except BaseException as error:
                    self.journal.append('generation_unknown', {'request_sha256': sha(sent),
                                        'ordinal': intent['ordinal'], 'error_type': type(error).__name__})
                    raise
            with self.context(request['route']):
                user_step = step_input(request['task'], request['scene'])
                observed = invoke_step(self.tokenizer, generate, user_step,
                    privacy_guard=lambda rendered: rendered == user_step and allowed(request['task'], request['scene']))
            guard()
            result = {'protocol': PROTOCOL, 'scope_sha256': sha(self.binding), 'request_sha256': sha(sent),
                      'observation': observed, 'generation_returns': receipts,
                      'status': 'recorded_model_observation_not_native_permission'}
            self.journal.append('model_receipt', {'result': result})
            self.completed[key] = observed['status']
            self.journal.blocked = observed['status'] == 'operational_failure_no_retry'
            return result
        except BaseException:
            self.journal.blocked = True
            raise
        finally:
            self.journal.lock.release()
