"""CPU-only formal capacity characterization; no private or live entry.

Uses only checked-in synthetic test families, real signer/SQLite/channels,
and fake model/Rhino. Deliberately wrong model choices in some core cases
stress write traffic, not quality. This is not a geometric coverage proof.
"""
import json
import tempfile
from pathlib import Path


def characterize():
    from pytest import MonkeyPatch
    from eval.test_c5_formal20_field_adapters import setup_field, assertions
    from eval.test_c5_formal20_preparation import EMPTY_ASSERTIONS
    from training.c5_formal20_plan import READS, family_merkle_root, slot_order, slot_order_sha256
    from plugin.rhino_listener.c5_research_native import digest
    from plugin.rhino_listener import c5_formal20_hub as hubs
    patch = MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory(prefix='c5-formal-capacity-cpu-') as directory:
            state, cases, spec, freeze, runner, _, _ = setup_field(Path(directory).resolve(), patch)
            wire = runner.model.pipe_factory(None)
            for case in cases:
                case['fixture_recipe'] = []
                case['initial_assertions'] = EMPTY_ASSERTIONS.copy()
                if case['primary_tool'] in READS:
                    wire.policy[case['task_text']] = [('get_scene_summary', {})]
                elif case['stratum'] in ('clarification', 'refusal'):
                    wire.policy[case['task_text']] = []
                elif case['stratum'] == 'core_tool':
                    wire.policy[case['task_text']] = [('create_box', {'width': 2, 'depth': 3, 'height': 4})]
                else:
                    operations = [('create_box', {'width': 2, 'depth': 3, 'height': 4}),
                        ('move_object', {'object_id': 'box-1', 'translate_x': 1, 'translate_y': 2, 'translate_z': 3}),
                        ('scale_object', {'object_id': 'box-1', 'scale_factor': [2, 2, 2]})]
                    case['max_steps'] = case['max_writes'] = 3
                    case['max_reads'] = 0
                    case['expected_operations'] = [{'name': name, 'arguments': args, 'read_result': None}
                        for name, args in operations]
                    case['final_assertions'] = assertions([0, 0.5, 1], [4, 6.5, 9], 192)
                    wire.policy[case['task_text']] = operations
            spec['family_merkle_root_sha256'] = family_merkle_root(cases)
            spec['slot_order_sha256'] = slot_order_sha256(slot_order(cases, seed=spec['slot_seed']))
            freeze['spec_sha256'] = digest(spec)
            runner.approval['spec_sha256'] = digest(spec)
            runner.approval['runtime_freeze_sha256'] = digest(freeze)
            count, original = [0], hubs.FormalHub
            def make(*args, **kwargs):
                hub = original(*args, **kwargs)
                source = hub.source
                def observed():
                    count[0] += 1
                    return source()
                hub.source = observed
                return hub
            patch.setattr(hubs, 'FormalHub', make)
            value = runner.run(lambda: cases)
            slots = [state / slot['slot_id'] for slot in slot_order(cases, seed=spec['slot_seed'])]
            counts = [len(list(path.glob('request-*.json'))) for path in slots]
            return {'status': value['status'], 'slots': value['slots_attempted'],
                'model_requests': len(wire.keys), 'generation_stages': wire.stages,
                'source_guard_calls': count[0], 'native_request_count': sum(counts),
                'maximum_child_request_count': max(counts), 'synthetic_only': True,
                'real_model_Rhino_GPU_holdout_calls': 0, 'formal_quality_claim': False,
                'owner_private_cases_or_keys_read': False}
    finally:
        patch.undo()


if __name__ == '__main__':
    print(json.dumps(characterize(), sort_keys=True))
