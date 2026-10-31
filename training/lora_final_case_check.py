"""Owner-only formatting aid. Reuse the scorer contract; never repair cases.

Pure CPU, no file I/O, model, Rhino, seal or execution authority. Only public
synthetic fixtures may be passed by agents. Error output is an explicit
allowlist: private exception messages/IDs/values are never returned.
"""
from collections import Counter
from itertools import islice

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


def field_details(case):
    """Advisory only; the original validator remains the acceptance authority.

    Paths contain only public schema keys and ordinal indexes, never supplied
    keys, aliases, values or exception messages. Inspect at most eight seeds.
    """
    import math
    from training.c5_formal20_plan import _schemas, SEED_OPERATIONS
    from plugin.rhino_listener.c5_research_native import _schema_value, GUID
    details = []
    def add(path, reason, expected=None):
        item = {'field': path, 'reason': reason}
        if expected is not None: item['expected'] = expected
        if len(details) < 128: details.append(item)
    for label in ('initial_assertions', 'final_assertions'):
        assertion = case.get(label)
        if isinstance(assertion, dict):
            for name, kind, description in (('objects', dict, 'object'), ('unchanged', list, 'array')):
                if name in assertion and not isinstance(assertion[name], kind):
                    add(label+'.'+name, 'wrong_type', description)
    seeds = case.get('fixture_recipe')
    if not isinstance(seeds, list): return details
    schemas = _schemas()
    for index, seed in enumerate(seeds[:8]):
        if not isinstance(seed, dict): continue
        operation, args = seed.get('operation'), seed.get('arguments')
        if not isinstance(operation, str) or operation not in SEED_OPERATIONS or not isinstance(args, dict): continue
        prefix = 'fixture_recipe[%d].arguments' % index
        schema = schemas[operation]; properties = schema['properties']
        for name in schema.get('required', []):
            if name not in args: add(prefix+'.'+name, 'missing_required_field')
        for position, (name, value) in enumerate(islice(args.items(), 64), 1):
            if name not in properties:
                add(prefix+'.<unknown-field-%d>' % position, 'unknown_field', sorted(properties))
                continue
            path = prefix+'.'+name
            try: valid = _schema_value(value, properties[name])
            except Exception: valid = False
            if not valid:
                kinds = properties[name].get('anyOf', [properties[name]])
                expected = '|'.join(k['type'] for k in kinds)
                add(path, 'schema_type_or_array_limit', expected)
                # Array element positions only, without exposing their values.
                array_schema = next((k for k in kinds if k['type']=='array'), None)
                if isinstance(value, list) and array_schema:
                    if len(value)>16: add(path, 'array_length_exceeds_16')
                    for i, part in enumerate(value[:16]):
                        try: part_valid = _schema_value(part, array_schema['items'])
                        except Exception: part_valid = False
                        if not part_valid: add(path+'[%d]' % i, 'wrong_element_type', array_schema['items']['type'])
                continue
            if type(value) in (int, float) and (not math.isfinite(value) or abs(value)>100000):
                add(path, 'numeric_bound', 'finite; absolute value <= 100000')
            if isinstance(value, str) and (not 0<len(value)<=80 or any(ord(c)<32 for c in value) or GUID.search(value)):
                add(path, 'string_contract', '1..80 characters; no control characters or GUID')
            if operation.startswith('create_') and type(value) in (int,float) and value<=0:
                add(path, 'nonpositive_dimension', '> 0')
            if name=='object_ids':
                if not value: add(path, 'empty_alias_array')
                if len(set(value))!=len(value): add(path, 'duplicate_alias')
                for i, part in enumerate(value):
                    if not 0<len(part)<=80 or GUID.search(part) or any(ord(c)<32 for c in part):
                        add(path+'[%d]' % i, 'alias_contract', '1..80 characters; no control characters or GUID')
            if name in ('axis','center_point','scale_factor') and value is not None:
                if len(value)!=3: add(path, 'vector_length', 'exactly 3 numbers')
                for i, part in enumerate(value):
                    if abs(part)>100000: add(path+'[%d]' % i, 'numeric_bound', 'absolute value <= 100000')
                if name=='axis' and not any(v!=0 for v in value): add(path, 'zero_rotation_axis')
                if name=='scale_factor':
                    for i, part in enumerate(value):
                        if part<=0: add(path+'[%d]' % i, 'nonpositive_scale', '> 0')
            if operation=='set_object_color' and name in ('r','g','b') and not 0<=value<=255:
                add(path, 'rgb_range', '0..255')
    return details


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
            error = {'row': index, 'code': code}
            try:
                details = field_details(case) if isinstance(case, dict) else []
            except Exception:
                details = [{'field': 'case', 'reason': 'field_diagnostic_unavailable'}]
            if details: error['details'] = details
            errors.append(error)
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
