"""Python 3.9 host wire: bounded detached JSON and new-study HMAC receipts.

No training dependency, Rhino import, I/O, execution grant or key creation.
"""
import hmac
import json
import re

from .c5_research_gate import signature
from .c5_research_native import canonical, digest, require

PROTOCOL = 'lora-public-development-wire-v1'
STUDY = 'lora-optimization-development-v1'


def detached(value):
    raw = canonical(value)
    require(len(raw.encode()) <= 1024 * 1024, 'bounded development frame required')
    return json.loads(raw)


def host_response(secret, runtime, slot, sequence, request, value):
    require(type(runtime) is str and re.fullmatch('[0-9a-f]{64}', runtime), 'exact runtime required')
    payload = {'protocol': PROTOCOL, 'study_id': STUDY, 'runtime_sha256': runtime,
               'slot_id': slot, 'sequence': sequence, 'request_sha256': digest(request), 'value': value}
    return detached({'payload': payload, 'signature': signature(secret, payload)})


def verify_host(envelope, *, secret, runtime, slot, sequence, request):
    envelope = detached(envelope)
    require(set(envelope) == {'payload', 'signature'}, 'signed host envelope required')
    p = envelope['payload']
    require(type(p) is dict and set(p) == {'protocol', 'study_id', 'runtime_sha256', 'slot_id',
            'sequence', 'request_sha256', 'value'}, 'exact host receipt required')
    require(type(sequence) is int and sequence > 0 and type(p['sequence']) is int and p['sequence'] == sequence
            and p['protocol'] == PROTOCOL and p['study_id'] == STUDY and p['runtime_sha256'] == runtime
            and p['slot_id'] == slot and p['request_sha256'] == digest(request), 'host receipt scope differs')
    require(type(envelope['signature']) is str and hmac.compare_digest(
        signature(secret, p), envelope['signature']), 'host receipt signature differs')
    require(type(p['value']) is dict, 'host value must be an object')
    return p['value']
