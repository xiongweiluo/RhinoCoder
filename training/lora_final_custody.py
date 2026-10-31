"""Owner-side pure sealing checks; agents use only synthetic unit fixtures.

Automated text overlap checks cannot prove historical inventory completeness,
semantic independence or fixture correctness. These remain explicit owner facts.
"""
import hashlib
from datetime import datetime, timezone
from difflib import SequenceMatcher

from plugin.rhino_listener.c5_research_native import digest, require
from data_pipeline.training_views import numeric_template_signature
from training.lora_comparison_plan import compile_cases
from training.lora_final_preparation import validate_spec
from tools.c5_rhino_formal20_owner_exclusion import _texts, _merkle_root
from plugin.rhino_listener.lora_final_admission import CATEGORIES, FLAGS


def seal(spec, cases, exclusions, encrypted, attestation):
    validate_spec(spec)
    compiled = compile_cases(spec['comparison_plan'], cases)
    require(set(exclusions) == set(CATEGORIES) and all(type(v) is list and v for v in exclusions.values()),
            'complete exclusion categories required; unknown inventory blocks sealing')
    reference = spec['exclusion_reference']
    require(all(len(exclusions[k]) >= n for k,n in reference['minimum_counts'].items())
            and len(exclusions['original80']) == 80
            and _merkle_root(exclusions['original80']) == reference['original80_merkle_root'],
            'historical inventory count or original80 identity differs')
    require(set(attestation) == {'actor', 'sealed_at_utc', *FLAGS} and attestation['actor'] == 'repository_owner'
            and all(attestation[k] is True for k in FLAGS), 'owner custody facts incomplete')
    sealed = attestation['sealed_at_utc']
    require(type(sealed) is str and sealed.endswith('Z'), 'UTC seal time required')
    stamp = datetime.fromisoformat(sealed.replace('Z','+00:00'))
    require(datetime(2026,10,27,tzinfo=timezone.utc) <= stamp <= datetime.now(timezone.utc), 'seal time outside preparation window')
    require(set(encrypted) == {'sha256', 'bytes', 'format'} and encrypted['format'] in {'age-x25519','aes-256-gcm'}
            and type(encrypted['bytes']) is int and 0 < encrypted['bytes'] <= 10*1024**2
            and type(encrypted['sha256']) is str and len(encrypted['sha256']) == 64
            and all(c in '0123456789abcdef' for c in encrypted['sha256']), 'encrypted artifact commitment required')
    history = [row for rows in exclusions.values() for row in rows]
    require(all(type(row) is dict for row in history), 'exclusion row shape differs')
    for key in ('family_id','template_family'):
        require(not {c[key] for c in cases} & {r.get(key) for r in history if type(r.get(key)) is str}, 'historical identity overlap')
    signatures = [numeric_template_signature(c['task_text']) for c in cases]
    historical = set(numeric_template_signature(t) for r in history for t in _texts(r))
    require(all(hashlib.sha256(('historical-text:'+text).encode()).hexdigest()
                not in reference['historical_numeric_hashes'] for text in signatures), 'published historical fingerprint overlap')
    require(len(set(signatures)) == 40, 'new numeric templates overlap')
    for i, text in enumerate(signatures):
        others = historical | set(signatures[:i])
        require(text not in others and all(SequenceMatcher(None,text,other).ratio() < .92 for other in others),
                'exact numeric or near-duplicate overlap')
    package = dict(spec, compiled=compiled)
    from plugin.rhino_listener.c5_research_channel import LIMIT
    from plugin.rhino_listener.c5_research_native import canonical
    require(all(len((canonical(v)+'\n').encode()) <= LIMIT for v in (cases,package)), 'private channel package exceeds fixed byte budget')
    receipt = {'schema_version':1, 'study_id':spec['study_id'], 'status':'owner_sealed_unconsumed_not_execution_authority',
        'spec_sha256':digest(spec), 'choices_sha256':spec['choices_sha256'], 'runtime_package_sha256':digest(package),
        'cases_sha256':digest(cases), 'compiled_sha256':digest(compiled), 'schedule_sha256':digest(compiled['views']['schedule']),
        'family_count':40, 'slot_count':80, 'strata':dict(spec['comparison_plan']['strata']),
        'encrypted_artifact':encrypted, 'custodian_attestation':attestation,
        'exclusions':{k:{'rows':len(rows),'sha256':digest(rows)} for k,rows in exclusions.items()},
        'automated_overlap_count':0, 'execution_authorized':False,
        'agent_private_access':False, 'model_calls':0, 'rhino_calls':0}
    return package, receipt
