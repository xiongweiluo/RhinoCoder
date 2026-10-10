"""Classify deterministic schema/alias rejection BEFORE consent reservation."""
from plugin.rhino_listener.c5_research_native import NativeError, validate_native_arguments

VALUE_REASONS = frozenset({'unsafe numeric bound', 'unsafe string/physical ID', 'nonpositive dimensions',
    'invalid alias set', 'invalid vector', 'zero rotation axis', 'nonpositive scale', 'color outside RGB range',
    'overlapping boolean roles'})


def rejection(name, arguments, native, schemas):
    try:
        validate_native_arguments(name, arguments, schemas)
    except NativeError as exc:
        if str(exc) not in VALUE_REASONS: raise
        return {'status': 'known_prepermission_rejection_no_dispatch', 'reason': 'unsafe_native_value',
            'permission_reserved': False, 'native_dispatches': 0}
    from training.c5_formal20_privacy import LABEL
    if any(not LABEL.fullmatch(arguments[k]) for k in ('layer_name', 'group_name') if k in arguments):
        return {'status': 'known_prepermission_rejection_no_dispatch', 'reason': 'nonpublic_research_label',
            'permission_reserved': False, 'native_dispatches': 0}
    aliases = {row['alias'] for row in native['objects']}
    targets = [arguments['object_id']] if 'object_id' in arguments else []
    for key in ('object_ids', 'input0_ids', 'input1_ids'): targets += arguments.get(key, [])
    if any(a not in aliases for a in targets):
        return {'status': 'known_prepermission_rejection_no_dispatch', 'reason': 'unknown_native_alias',
            'permission_reserved': False, 'native_dispatches': 0}
    return None
