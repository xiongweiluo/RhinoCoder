"""Independent readiness reconstruction; no producer helper or effects."""
from plugin.rhino_listener.c5_research_native import digest,require


def audit_startup_ready(mac,remote,freeze,study_id):
    expected={'protocol':'c5-modelbridge-startup-ready-v1','study_id':study_id,
        'runtime_freeze_sha256':digest(freeze),'source_inventory_sha256':freeze['source_inventory_sha256'],
        'environment_sha256':freeze['environment_sha256'],'model_identities':freeze['model_identities'],
        'model_loaded':True,'generation_requests':0,'generation_stages':0,'holdout_rows_read':0,
        'status':'loaded_verified_ready_before_requests'}
    require(isinstance(mac,dict) and isinstance(remote,dict) and mac==remote==expected
        and digest(mac)==digest(remote)==digest(expected), 'independent startup identity/zero-count evidence differs')
    return {'startup_record_identity_and_zero_counts_verified':True,
        'execution_authority':False,'formal_quality_claim':False}
