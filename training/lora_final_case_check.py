"""Owner-only formatting aid. Reuse the scorer contract; never repair cases.

Pure CPU, no file I/O, model, Rhino, seal or execution authority. Only public
synthetic fixtures may be passed by agents. Error output is an explicit
allowlist: private exception messages/IDs/values are never returned.
"""
from collections import Counter

from training.c5_formal20_plan import FormalPlanError, validate_case
from training.lora_comparison_plan import compile_cases
from training.lora_final_preparation import validate_spec


CASE_ERRORS = frozenset('''case_version_or_fields family_id_invalid template_family_invalid
stratum_invalid task_text_invalid task_text_not_alias_safe fixture_recipe_budget
fixture_seed_operation_invalid fixture_seed_arguments_invalid
initial_assertion_fields final_assertion_fields initial_object_count final_object_count
initial_assertion_shape final_assertion_shape initial_assertion_budget final_assertion_budget
initial_alias_shape final_alias_shape initial_unchanged_alias_reuse final_unchanged_alias_reuse
initial_solid_evidence_fields final_solid_evidence_fields initial_read_result_must_be_null
max_steps_invalid max_writes_invalid max_reads_invalid zero_model_steps expected_sequence_budget
expected_operation_invalid write_expected_read_result read_expected_result_missing
expected_arguments_invalid dispatch_or_step_budget_differs_from_expected_sequence
core_tool_case_shape abstention_case_shape multistep_case_shape recovery_case_shape
case_not_canonical_json'''.split())


def check_cases(spec, cases):
    validate_spec(spec)
    report = {'status': 'needs_correction', 'errors': [], 'execution_authorized': False,
              'sealed': False, 'model_calls': 0, 'rhino_calls': 0,
              'geometry_correctness_verified': False, 'independence_verified': False}
    errors = report['errors']
    if type(cases) is not list or len(cases) != 40:
        errors.append({'code': 'exactly_40_case_objects_required'})
        return report
    for index, case in enumerate(cases, 1):
        try:
            validate_case(case)
        except Exception as exc:
            code = str(exc) if isinstance(exc, FormalPlanError) and str(exc) in CASE_ERRORS else 'invalid_case_structure'
            errors.append({'row': index, 'code': code})
    if errors:
        return report
    if Counter(c['stratum'] for c in cases) != spec['comparison_plan']['strata']:
        errors.append({'code': 'fixed_12_8_8_6_6_strata_required'})
    for key in ('family_id', 'template_family', 'task_text'):
        if len({c[key] for c in cases}) != 40:
            errors.append({'code': key + '_reuse'})
    if errors:
        return report
    try:
        compiled = compile_cases(spec['comparison_plan'], cases)
        from plugin.rhino_listener.c5_research_channel import LIMIT
        from plugin.rhino_listener.c5_research_native import canonical
        if any(len((canonical(v)+'\n').encode()) > LIMIT for v in (cases, dict(spec, compiled=compiled))):
            errors.append({'code': 'private_channel_byte_budget_exceeded'})
    except Exception:
        errors.append({'code': 'fixed_tool_coverage_or_compiled_contract_invalid'})
    if not errors:
        report.update(status='case_structure_passed_not_sealed', family_count=40, slot_count=80)
    return report
