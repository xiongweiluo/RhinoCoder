"""Pure new development wire and generation-return checks; no providers."""
import math
from training.c5_reuse_evidence import exact, raw_sha, require, sha
from training.c5_reuse_field_scope import PROTOCOL, STUDY, validate_binding
from training.c5_model_transport import validate_request
from training.c5_contract import DECODE_CONFIG

def validate_return(value, prompt_sha, stage):
    exact(value, ('raw','tokens','seconds','prompt_sha256','output_sha256'))
    require(stage in ('selector', 'invocation'), 'peer_stage')
    require(type(value['raw']) is str and len(value['raw'].encode()) <= 262144
            and type(value['tokens']) is int and 0 <= value['tokens'] <= DECODE_CONFIG[stage+'_max_new_tokens']
            and type(value['seconds']) in (int,float) and math.isfinite(value['seconds']) and value['seconds'] >= 0
            and value['prompt_sha256'] == prompt_sha and value['output_sha256'] == raw_sha(value['raw'].encode()),
            'peer_raw_generation_binding')


def envelope(binding, request):
    validate_binding(binding)
    validate_request(request)
    require(request['probe_id'] == STUDY and request['runtime_freeze_sha256'] == binding['runtime_sha256'],
            'new_peer_request_scope')
    return {'protocol': PROTOCOL, 'scope_sha256': sha(binding), 'request': request}
