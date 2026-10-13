#!/usr/bin/env python3
"""Read-only preparation review; never writes grants or opens field actors."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from training.c5_reuse_evidence import canonical,require,sha
from training.c5_recovery_policy import POLICY,affected_checks
from training.c5_recovery_history import validate_history
from plugin.rhino_listener.c5_followup_scope import material

SPEC='eval/c5/reuse-followup-development-spec-20261012-d.json'
RUNTIME='eval/c5/reuse-followup-development-runtime-freeze-20261012-d.json'
NEW_SOURCES=(
    'training/c5_recovery_policy.py','training/c5_recovery_confirmation.py',
    'training/c5_recovery_storage.py','training/c5_recovery_stop.py',
    'training/c5_recovery_controller.py','training/c5_recovery_history.py',
    'tools/check_c5_recovery_preparation.py','eval/test_c5_recovery.py',
)
def raw_sha(value):return hashlib.sha256(value).hexdigest()
def history_document(root):
    s=json.loads((root/SPEC).read_bytes());r=json.loads((root/RUNTIME).read_bytes())
    g=json.loads((root/'eval/c5/reuse-followup-admission-genesis-20261012-d.json').read_bytes())
    d=json.loads((root/'eval/c5/reuse-followup-development-readiness-failure-20261012-d.json').read_bytes())
    pins={}
    for endpoint,roles in (('mac',('controller','host')),('gpu',('worker','stop'))):
        binding=material(s,r,now=1,endpoint=endpoint,cleanup_only=True)
        manifest={'schema':2,'endpoint':endpoint,'genesis':g,'genesis_sha256':sha(g),
                  'binding_sha256':sha(binding),'study_id':s['study_id'],'replay_allowed':False}
        files=dict(g['legacy_snapshot'][endpoint]['file_sha256'])
        files['followup-v2-genesis.json']=raw_sha(canonical(manifest)+b'\n')
        for role in roles:
            tombstone={'study_id':s['study_id'],'role':role,'scope_sha256':sha(binding),'replay_allowed':False}
            files['followup-d-'+role+'.consumed.json']=raw_sha(canonical(tombstone)+b'\n')
        pins[endpoint]=files
    retirements={k:{'retirement_raw_sha256':v['retirement_raw_sha256'],
                    'retired_grant_raw_sha256':v['retired_grant_raw_sha256']}
                 for k,v in g['retirements'].items()}
    require(d['retirement']['mac']['retirement_raw_sha256']==d['retirement']['gpu']['retirement_raw_sha256']
            and d['retirement']['mac']['active_grant_absent'] is d['retirement']['gpu']['active_grant_absent'] is True,
            'recovery_d_retirement_receipts')
    retirements[s['instance_id']]={'retirement_raw_sha256':d['retirement']['mac']['retirement_raw_sha256'],
                                   'retired_grant_raw_sha256':d['retirement']['mac']['grant_preserved_raw_sha256']}
    return validate_history({'protocol':POLICY['protocol'],'retirements':retirements,
        'registry_file_sha256':pins,'historical_consumption_nonempty':True,
        'old_no_go_preserved':True,'old_active_grants_must_be_absent':True})

def review(root=ROOT):
    root=Path(root);require(root.is_absolute() and root.resolve()==root,'recovery_review_root')
    old=json.loads((root/RUNTIME).read_bytes());files=dict(old['source_files'])
    for name,pin in files.items():
        require(raw_sha((root/name).read_bytes())==pin,'recovery_legacy_source_changed')
    files[RUNTIME]=raw_sha((root/RUNTIME).read_bytes())
    for name in NEW_SOURCES:files[name]=raw_sha((root/name).read_bytes())
    history=history_document(root)
    spec={'protocol':POLICY['protocol'],'status':'PREPARATION_ONLY','policy':POLICY,
          'history_sha256':sha(history),'changed_groups':['retry_policy','confirmation','stop'],
          'affected_checks':affected_checks(['retry_policy','confirmation','stop']),
          'new_field_identity':None,'execution_ready':False,'new_execution_grant_received':False,
          'private_formal_data_access_allowed':False,'default_route_change_allowed':False,
          'source_revision_requires_new_exact_approval':True,
          'new_campaign_during_retry_allowed':False}
    runtime={'protocol':POLICY['protocol'],'review_spec_sha256':sha(spec),'source_files':files,
             'legacy_d_spec_sha256':old['spec_sha256'],'legacy_d_runtime_sha256':sha(old),
             'legacy_environment_sha256':old['environment_sha256'],
             'legacy_model_assets_sha256':old['model_assets_sha256'],
             'legacy_host_readable_files_sha256':old['host_readable_files_sha256'],
             'field_actors_registered':False,'deployed_to_mac_or_gpu':False,'execution_ready':False}
    return {'review_spec':spec,'review_runtime':runtime,'history':history,
            'review_spec_sha256':sha(spec),'review_runtime_sha256':sha(runtime),
            'legacy_source_files_reverified':len(old['source_files']),
            'review_source_files':len(files),'source_inventory_sha256':sha(files),
            'model_or_rhino_calls':0,'global_registry_writes':0,'private_formal_reads':0,
            'execution_authority':False,'fresh_field_environment_or_asset_bytes_attested':False}

if __name__=='__main__':
    value=review()
    saved=ROOT/'eval/c5/engineering-recovery-preparation-review-20261013.json'
    if '--check' in sys.argv:
        require(json.loads(saved.read_bytes())==value,'recovery_saved_review_changed')
    print(json.dumps({k:v for k,v in value.items() if k not in ('review_spec','review_runtime','history')},sort_keys=True))
