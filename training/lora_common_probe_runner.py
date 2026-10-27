"""CPU preparation and one bounded scripted run on the common controller.

The live caller supplies an admitted host transport. There is no model loader,
SSH, private task reader, retry loop, or final-test execution in this module.
"""
import hashlib
import json
from pathlib import Path

from plugin.rhino_listener.c5_research_native import digest, require
from plugin.rhino_listener.lora_common_probe import prepare as prepare_host
from training.c5_rhino_adapter import invoke_step
from training.c5_formal20_privacy import allowed
from training.lora_common_chain import CommonChain
from training.lora_common_probes import public_probes, diagnostic_probes
from training.lora_comparison_plan import proposal, compile_cases, capacity
from training.lora_development_controller import DevelopmentController
from training.lora_development_scope import DevelopmentJournal
from training.lora_development_wire import model_response

IDENTITY = digest({'provider': 'fixed_public_scripted_probe', 'weights': None})


class ScriptedTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return json.dumps(messages, ensure_ascii=False, sort_keys=True)

    def __call__(self, text, **kwargs):
        # Placeholder solely for deterministic native plumbing. No assertion
        # about actual model context length may be based on this provider.
        return {'input_ids': [0] * 100}


def prepare(root, package):
    ready = prepare_host(root, package)
    diagnostic = package['kind'] == 'public_common_state_diagnostic_v1'
    plan = proposal(native_probe=True, fingerprint_diagnostic=diagnostic)
    cases = diagnostic_probes() if diagnostic else public_probes()
    require(package['plan'] == plan and package['compiled'] == compile_cases(plan, cases)
            and package['capacity'] == capacity(plan), 'exact public probe composition differs')
    return {**ready, 'cases': cases, 'tokenizer': ScriptedTokenizer()}


def controller(root, package, state, secret, host, guard, cleanup_guard):
    ready = prepare(root, package)
    runtime = digest(package)
    journal = DevelopmentJournal(state/'journal', package['plan'], runtime, compiled=package['compiled'])
    contract = CommonChain(package['plan'], package['compiled'], ready['cases'], state/'permission')
    cases = {c['family_id']: c for c in ready['cases']}
    def scripted(sent):
        case = cases[journal.views['model'][sent['slot_id']]['family_id']]
        operation = case['expected_operations'][sent['step_index']]
        rows = []
        def generate(prompt, stage):
            # Explicitly scripted public mechanism evidence, never a real model.
            raw = json.dumps({'tool': operation['name']} if stage == 'selector' else
                             {k: operation[k] for k in ('name', 'arguments')})
            row = {'stage': stage, 'raw': raw, 'tokens': 0, 'seconds': 0.,
                'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                'output_sha256': hashlib.sha256(raw.encode()).hexdigest()}
            rows.append(row); return row
        rendered = contract.wire.user_step(sent)
        observed = invoke_step(ready['tokenizer'], generate, rendered, scene_binding=sent['binding'],
            privacy_guard=lambda text: text == rendered and allowed(sent['task'], sent['scene']))
        return model_response(sent, observed, rows, IDENTITY)
    return DevelopmentController(journal=journal, state=state/'controller', runtime=runtime,
        secret=secret, schemas=ready['schemas'], tokenizer=ready['tokenizer'], identities={'scripted_probe': IDENTITY},
        host=host, model=scripted, guard=guard, cleanup_guard=cleanup_guard, contract=contract)
