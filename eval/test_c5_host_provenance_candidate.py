"""Candidate design positive/negative controls; entirely invented metadata."""
import copy

import pytest

from training.c5_host_provenance_candidate import POLICY, digest, validate_candidate, ProvenanceDesignError


def fixture():
    roles = {n:'/synthetic/'+n for n in ('rhino_host','dotnet_runtime','python_runtime','pythonnet_generator','research_entry')}
    files = {p:'a'*64 for p in roles.values()}
    assemblies = [{'name':'synthetic-host','instance_id':'host-instance','kind':'file_assembly',
        'file':roles['rhino_host'],'metadata_sha256':'b'*64,'metadata_scope':'file_bytes_and_structure'},
        {'name':'synthetic-emitted','instance_id':'opaque-instance','kind':'opaque_host_dynamic',
         'file':None,'metadata_sha256':'c'*64,'metadata_scope':'structure_only_not_code_bytes'}]
    baseline = {'process_identity':'d'*64,'project_files':{'/synthetic/source.py':'e'*64},
        'python_origin_bindings':{n:{'origin':'unknown','host_role':'pythonnet_generator',
            'binding_scope':'controlled_process_opaque_host_assumption_not_causal_proof','object_identity':n+'-object'}
            for n in ('CLR','clr')}, 'assemblies':assemblies, 'assembly_inventory_sha256':digest(assemblies),
        'native_images_sha256':'f'*64,'warmup_completed':True,'baseline_sealed':True}
    manifest = {'policy':POLICY,'design_only':True,'file_inventory':files,'file_roles':roles,
        'opaque_trust_assumptions':{'trusted_host_may_emit_unverifiable_code':True,
            'assembly_names_are_not_generator_proof':True,'no_untrusted_inprocess_code_assumed':True,
            'not_a_sandbox_against_local_host_compromise':True},'sealed_baseline':baseline}
    observation = copy.deepcopy(baseline)
    observation.update(phase='pre_dispatch',model_input_is_data_only=True,unattributed_load_events=[],event_stream_complete=True)
    return manifest, observation


def test_positive_candidate_never_grants_execution_or_byte_proof():
    manifest, observation = fixture()
    value = validate_candidate(manifest, observation)
    assert value['opaque_assembly_count'] == 1
    for field in ('emitted_bytecode_or_causal_generator_origin_proven','actual_runtime_evidence_verified',
                  'legacy_byte_closure_verified','execution_ready','formal_admission_supported'):
        assert value[field] is False


@pytest.mark.parametrize('field,value', [
    ('process_identity','0'*64), ('project_files',{'/synthetic/source.py':'0'*64}),
    ('native_images_sha256','0'*64), ('warmup_completed',False), ('baseline_sealed',False),
    ('python_origin_bindings',{}), ('assemblies',[]), ('assembly_inventory_sha256','0'*64),
    ('unattributed_load_events',['synthetic unexplained load']), ('event_stream_complete',False),
    ('model_input_is_data_only',False), ('phase','warmup')])
def test_changed_or_incomplete_observation_fails_closed(field, value):
    manifest, observation = fixture()
    observation[field] = value
    with pytest.raises(ProvenanceDesignError): validate_candidate(manifest, observation)


@pytest.mark.parametrize('change', ['same_name_new_instance','new_dynamic_assembly','same_instance_changed_metadata'])
def test_names_or_inventory_self_reports_cannot_excuse_dynamic_changes(change):
    manifest, observation = fixture()
    if change == 'same_name_new_instance': observation['assemblies'][1]['instance_id']='different'
    elif change == 'new_dynamic_assembly': observation['assemblies'].append(copy.deepcopy(observation['assemblies'][1]))
    else: observation['assemblies'][1]['metadata_sha256']='0'*64
    observation['assembly_inventory_sha256']=digest(observation['assemblies'])
    with pytest.raises(ProvenanceDesignError): validate_candidate(manifest, observation)


@pytest.mark.parametrize('change', ['remove_trust_assumption','pretend_byte_verified','missing_generator','unsealed_baseline','real_execution'])
def test_candidate_requires_honest_limits_and_complete_declared_identity(change):
    manifest, observation = fixture()
    if change == 'remove_trust_assumption': manifest['opaque_trust_assumptions']={}
    elif change == 'pretend_byte_verified': manifest['sealed_baseline']['assemblies'][1]['metadata_scope']='file_bytes_and_structure'
    elif change == 'missing_generator': del manifest['file_inventory'][manifest['file_roles']['pythonnet_generator']]
    elif change == 'unsealed_baseline': manifest['sealed_baseline']['baseline_sealed']=False
    else: manifest['design_only']=False
    with pytest.raises(ProvenanceDesignError): validate_candidate(manifest, observation)
