"""Pure finite watchdog contract, shared by freeze validation and supervisor."""
from .c5_research_native import require

LIMITS={'model_seconds':360,'startup_seconds':600,
    'first_request_idle_seconds':600,'between_requests_idle_seconds':3600}

def watchdog_limits(spec):
    value=spec.get('runtime_limits')
    require(type(value) is dict and set(value)==set(LIMITS)
        and all(type(value[k]) is int and value[k]==v for k,v in LIMITS.items())
        and type(spec.get('per_request_timeout_seconds')) is int
        and spec['per_request_timeout_seconds']==value['model_seconds']
        and type(spec.get('startup_timeout_seconds')) is int
        and spec['startup_timeout_seconds']==value['startup_seconds'],
        'formal_reuse_complete_frozen_watchdog_limits_required')
    return dict(value)
