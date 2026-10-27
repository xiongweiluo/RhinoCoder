"""Shared-chain preparation, not a grant or a final-test data generator.

The owner supplies final cases only in phase two. Public preparation uses
counts and two explicitly labelled native probes, never private task files.
The original C5 case contract, three-step ceiling and scorer stay unchanged.
"""
from __future__ import annotations

import hashlib
import random
from collections import Counter

from plugin.rhino_listener.c5_research_native import CORE, digest, require
from plugin.rhino_listener.candidate_atomic_gate import CONTROLLED_SNAPSHOT
from training.c5_formal20_plan import NAME, validate_case

FINAL_STUDY = 'lora-common-final-comparison-v1'
PROBE_STUDY = 'lora-common-native-probe-v1'
DIAGNOSTIC_STUDY = 'lora-common-state-diagnostic-v1'
SCOPE_STUDY = 'lora-common-document-scope-probe-v1'
SNAPSHOT_STUDY = 'lora-common-controlled-snapshot-probe-v1'
STUDIES = frozenset({FINAL_STUDY, PROBE_STUDY, DIAGNOSTIC_STUDY, SCOPE_STUDY, SNAPSHOT_STUDY})
STRATA = {'core_tool': 12, 'multistep': 8, 'error_recovery': 8, 'clarification': 6, 'refusal': 6}


def proposal(*, native_probe=False, fingerprint_diagnostic=False, document_scope_probe=False, controlled_snapshot_probe=False):
    """Unapproved parameters; never construct or expose a final task."""
    require(not (fingerprint_diagnostic or document_scope_probe or controlled_snapshot_probe) or native_probe, 'diagnostic must be zero-model')
    require(sum(map(bool, (fingerprint_diagnostic, document_scope_probe, controlled_snapshot_probe))) <= 1, 'one explicit probe scope')
    value = {
        'schema_version': 1,
        'study_id': PROBE_STUDY if native_probe else FINAL_STUDY,
        'execution_authorized': False,
        'routes': ['scripted_probe'] if native_probe else ['base', 'current_lora'],
        'system': 'original', 'tools': sorted(CORE),
        'strata': {'multistep': 1, 'error_recovery': 1} if native_probe else dict(STRATA),
        'schedule_seed': 20261027,
        'limits': {'max_steps': 3, 'host_ready_seconds': 180, 'slot_seconds': 180 if native_probe else 420,
                   'load_seconds': 0 if native_probe else 600, 'cleanup_export_seconds': 900},
        'purpose': 'native_seams_not_model_quality' if native_probe else 'exploratory_paired_comparison',
        'replay_consumed_slots': False,
        'unknown_effect_or_cleanup': 'stop',
        'model_weights_changed': False,
    }
    if fingerprint_diagnostic:
        value.update(study_id=DIAGNOSTIC_STUDY, strata={'multistep': 1},
                     purpose='explain_full_fingerprint_drift_not_repair_or_replace_prior_result')
    if document_scope_probe:
        value.update(study_id=SCOPE_STUDY, strata={'multistep': 1},
                     purpose='document_local_state_guard_and_move_read_not_model_quality')
    if controlled_snapshot_probe:
        value.update(study_id=SNAPSHOT_STUDY, strata={'multistep': 1},
                     purpose='controlled_write_snapshot_and_move_read_not_external_aba_or_model_quality')
    if controlled_snapshot_probe or not native_probe:
        value['state_contract'] = CONTROLLED_SNAPSHOT
    return value


def validate_plan(plan):
    require(type(plan) is dict and plan.get('study_id') in STUDIES, 'new study identity required')
    reference = proposal(native_probe=plan['study_id'] != FINAL_STUDY,
                         fingerprint_diagnostic=plan['study_id'] == DIAGNOSTIC_STUDY,
                         document_scope_probe=plan['study_id'] == SCOPE_STUDY,
                         controlled_snapshot_probe=plan['study_id'] == SNAPSHOT_STUDY)
    require(digest(plan) == digest(reference), 'comparison preparation choices changed; review the complete proposal')
    return plan


def capacity(plan):
    """Bounds from the single plan, not independently raised per-process caps."""
    validate_plan(plan)
    from plugin.rhino_listener.lora_development_runtime import common_capacity
    return common_capacity(plan)


def compile_cases(plan, cases):
    """Owner-side binding later; only public probe cases are used in preparation."""
    validate_plan(plan)
    cases = [validate_case(case) for case in cases]
    require(Counter(case['stratum'] for case in cases) == plan['strata'], 'fixed stratum population differs')
    require(all(len({case[key] for case in cases}) == len(cases)
                for key in ('family_id', 'template_family', 'task_text')), 'family/template/task reuse')
    if plan['study_id'] == FINAL_STUDY:
        require({case['primary_tool'] for case in cases if case['stratum'] == 'core_tool'} == CORE,
                'original twelve-tool coverage required')
    families = sorted(cases, key=lambda c: c['family_id'])
    rng = random.Random(plan['schedule_seed'])
    rng.shuffle(families)
    # Equal route order within every even-sized frozen stratum, not score-based.
    route_first = {}
    for layer in sorted(plan['strata']):
        ids = [case['family_id'] for case in families if case['stratum'] == layer]
        for i, family in enumerate(ids): route_first[family] = i % len(plan['routes'])
    schedule, model, native = [], {}, {}
    for case in families:
        start = route_first[case['family_id']]
        routes = plan['routes'][start:] + plan['routes'][:start]
        for route in routes:
            slot = 'common-%03d' % len(schedule)
            cell = {'slot_id': slot, 'family_id': case['family_id'], 'route': route,
                    'system': 'original', 'role': 'native_probe' if len(routes) == 1 else 'comparison'}
            schedule.append(cell)
            model[slot] = {**cell, 'study_id': plan['study_id'], 'task': case['task_text'], 'max_steps': case['max_steps']}
            native[slot] = {**cell, 'task_sha256': hashlib.sha256(case['task_text'].encode()).hexdigest(),
                'fixture_recipe': case['fixture_recipe'], 'max_reads': case['max_reads'], 'max_writes': case['max_writes']}
    compiled = {'study_id': plan['study_id'], 'plan_sha256': digest(plan),
                'cases_sha256': digest(cases), 'views': {'schedule': schedule, 'model': model, 'native': native}}
    validate_compiled(plan, compiled)
    return compiled


def validate_compiled(plan, compiled):
    validate_plan(plan)
    require(set(compiled) == {'study_id', 'plan_sha256', 'cases_sha256', 'views'}
            and compiled['study_id'] == plan['study_id'] and compiled['plan_sha256'] == digest(plan),
            'compiled study differs')
    views = compiled['views']; schedule = views['schedule']
    require(set(views) == {'schedule', 'model', 'native'} and len(schedule) == capacity(plan)['slots'],
            'compiled population differs')
    ids = [row['slot_id'] for row in schedule]
    require(type(compiled['cases_sha256']) is str and len(compiled['cases_sha256']) == 64
            and all(c in '0123456789abcdef' for c in compiled['cases_sha256']), 'case commitment required')
    require(ids == ['common-%03d' % i for i in range(len(ids))]
            and set(ids) == set(views['model']) == set(views['native']), 'fixed slot identities required')
    for cell in schedule:
        require(set(cell) == {'slot_id', 'family_id', 'route', 'system', 'role'}
                and cell['role'] == ('comparison' if plan['study_id'] == FINAL_STUDY else 'native_probe'),
                'exact fixed schedule fields required')
        model, native = views['model'][cell['slot_id']], views['native'][cell['slot_id']]
        require(all(model[k] == native[k] == v for k, v in cell.items())
                and NAME.fullmatch(cell['family_id']) and cell['route'] in plan['routes']
                and model['study_id'] == plan['study_id'] and cell['system'] == 'original'
                and type(model['max_steps']) is int and 1 <= model['max_steps'] <= 3,
                'common input scope differs')
        require(set(model) == set(cell) | {'study_id', 'task', 'max_steps'}
                and set(native) == set(cell) | {'task_sha256', 'fixture_recipe', 'max_reads', 'max_writes'}
                and native['task_sha256'] == hashlib.sha256(model['task'].encode()).hexdigest(),
                'scorer fields must not cross provider boundaries')
        require(all(type(native[k]) is int and 0 <= native[k] <= 3 for k in ('max_reads', 'max_writes'))
                and native['max_reads'] + native['max_writes'] <= model['max_steps']
                and type(native['fixture_recipe']) is list and len(native['fixture_recipe']) <= 8,
                'native policy beyond original contract')
    pairs = Counter((c['family_id'], c['route']) for c in schedule)
    families = {c['family_id'] for c in schedule}
    require(len(families) == sum(plan['strata'].values())
            and pairs == Counter({(f, route): 1 for f in families for route in plan['routes']}),
            'every family must appear exactly once per route')
    tasks = set()
    for family in families:
        cells = [c for c in schedule if c['family_id'] == family]
        models = [{k: v for k, v in views['model'][c['slot_id']].items() if k not in {'route', 'slot_id'}} for c in cells]
        natives = [{k: v for k, v in views['native'][c['slot_id']].items() if k not in {'route', 'slot_id'}} for c in cells]
        require(all(m == models[0] for m in models) and all(n == natives[0] for n in natives),
                'paired routes must start with identical task, fixture and budgets')
        tasks.add(models[0]['task'])
    require(len(tasks) == len(families), 'duplicate family task')
    return compiled
