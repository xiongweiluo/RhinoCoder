#! python 3
"""Separate one-use safety closure, NOT C replay or successful study cleanup.

No effects on import. New exact cleanup spec/runtime grant is mandatory.
Only the retained empty read-lora fixture, seven keys and three exact
delegates may be touched; no capture/execute request or new subscription.
"""
from pathlib import Path
import hashlib
import hmac
import json
import sqlite3
import sys
import time

ID='C5SAFE-HOSTASSURANCE-C-20261007-A'
RETIRED='C5DEV-HOSTASSURANCE-20261007-C'
STATE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-state-20261007-C')
SOURCE=Path('/Users/xiongweiluo/RhinoCoder/data/training/c5/hostassurance-dev-source-20261007-C')
ROOT=Path(__file__).resolve().parents[1]
SPEC='eval/c5/hostassurance-c-cleanup-spec-20261007.json'
FREEZE='eval/c5/hostassurance-c-cleanup-runtime-20261007.json'
ORIGINAL_SHA='bbbbca84474d5cd397f2e011775cb17b50f6f4a7328c6cee339a4aedf13090d1'
ACTIVE_SHA='de8fa7924ad4cf7fbeffdbe982f0b559a77eca7a8cf1f24175df642404ec6cfa'
UNUSED=('read-base','clarify-base','clarify-lora','unsupported-lora','unsupported-base')


def require(condition,message):
    if not condition:raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read(path):
    require(path.resolve()==path and path.is_file() and 0<path.stat().st_size<=1048576,'bounded regular fixed JSON required')
    def pairs(rows):
        result={}
        for k,v in rows:
            require(k not in result,'duplicate JSON key');result[k]=v
        return result
    return json.loads(path.read_bytes(),object_pairs_hook=pairs,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))


def validate_retired(result,created,request,response,write_count,read_row):
    """Pure raw preconditions; never reinterpret a late receipt as timely."""
    require(result.get('status')=='modelbridge_fail_retired_no_replay'
        and result.get('remote_process_exit_code')==0 and result.get('holdout_calls')==0
        and len(result.get('slots',[]))==3 and result.get('hub_stop') is None,'retired C failure differs')
    for row,slot in zip(result['slots'][:2],('write-base','write-lora')):
        require(row['slot']==slot and row['error'] is None and row['close']['status']=='closed'
            and row['stop']['status']=='stopped','previous slots not verifiably closed')
    last=result['slots'][2]
    require(last['slot']=='read-lora' and last['error']=='NativeError: unknown native acknowledgement; never guess cleanup'
        and last['close'] is None and last['stop'] is None,'original unknown failure must remain')
    require(created=={'active_serial':268435457,'fixture_serial':268435475,'python_major_minor':[3,9],
        'rhino_major':8,'rhino_version':'8.21.25188.17002','runtime_freeze_sha256':ORIGINAL_SHA},'known C fixture identity differs')
    require(set(request)=={'kind','envelope'} and request['kind']=='execute','last request is not original execution')
    p=request['envelope']['payload']
    require(p['owner_freeze_sha256']==ORIGINAL_SHA and p['operation']=='get_scene_summary'
        and p['arguments']=={} and p['consent_row_sha256'] is None,'last request must be scoped readonly summary')
    empty={'groups':{},'objects':[],'unit':'Millimeters'}
    require(response['status']=='done' and response['payload']==p and response['stable_idle_samples']==3
        and response['before']==response['after']==response['immediate_after']==response['result']==empty
        and response['before_state']==response['after_state']==response['immediate_after_state']==p['expected']
        and len(response['settling_samples'])==3
        and all(s=={'active_sha256':ACTIVE_SHA,'native':empty,'state':p['expected']} for s in response['settling_samples']),
        'late readonly completion/raw stable geometry differs')
    require(type(write_count) is int and write_count==0 and read_row=={
        'request_id':p['request_id'],'payload_sha256':digest(p),'state':'done','result_sha256':response['result_sha256']},
        'read-only ledger completion differs')
    return p


def binding(spec,freeze,approval,script_sha):
    require(spec['study_id']==freeze['study_id']==ID and spec['retired_study_id']==RETIRED
        and spec['retired_runtime_sha256']==ORIGINAL_SHA and spec['fixture_serial']==268435475
        and spec['geometry_tool_dispatches']==spec['model_calls']==spec['gpu_calls']==spec['holdout_calls']==0
        and spec['new_fixtures']==spec['new_subscriptions']==0
        and spec['fixture_closes_max']==1 and spec['ephemeral_keys_remove_max']==7
        and spec['idle_exact_remove_calls_max']==2 and spec['assemblyload_exact_remove_calls_max']==1
        and spec['original_result_rewrite_allowed'] is False and spec['replay_allowed'] is False
        and spec['complete_handler_absence_claimed'] is False and spec['logical_budget_seconds']==180,
        'new exact narrow cleanup scope required')
    require(freeze['spec_sha256']==digest(spec) and freeze['cleanup_script_sha256']==script_sha
        and freeze['retired_runtime_canonical_sha256']==ORIGINAL_SHA,'cleanup source/runtime binding differs')
    expected={'study_id':ID,'actor':'repository_owner','approved':True,
        'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),
        'scope':'retired C only; known empty read-lora closure, seven ephemeral keys, exact two Idle and one AssemblyLoad detach; no replay'}
    require(approval==expected and digest(approval)==digest(expected),
        'separate exact cleanup owner approval required')


def main():
    spec,freeze=read(ROOT/SPEC),read(ROOT/FREEZE)
    script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    binding(spec,freeze,read(STATE/'manual-c-cleanup-owner-approval.json'),script_sha)
    require(hashlib.sha256((SOURCE/'eval/c5/hostassurance-development-runtime-freeze-20261007-c.json').read_bytes()).hexdigest()
        ==freeze['retired_runtime_file_sha256'],'complete original frozen runtime bytes differ')
    import Rhino
    matches=[(n,m,m._SESSION) for n,m in tuple(sys.modules.items())
        if n.startswith('rhino_c5_') and getattr(m,'_SESSION',None) is not None
        and getattr(m._SESSION,'state',None)==STATE and m._SESSION.spec.get('probe_id')==RETIRED]
    require(len(matches)==1,'unique retained C owner required')
    name,package,hub=matches[0];prefix=name+'.plugin.rhino_listener.'
    native=sys.modules[prefix+'c5_research_native'];channel=sys.modules[prefix+'c5_research_channel']
    scope=sys.modules[prefix+'c5_hostassurance_development_scope_c']
    _,old_freeze,_,_,guard=scope.scope(SOURCE,private_prefixes=(name,),check_time=False)
    guard();require(digest(old_freeze)==ORIGINAL_SHA,'retired original source closure differs')
    child=hub.child;q=STATE/'read-lora'
    require(child is not None and child.directory==q and child.pending is None and child.seq==10
        and child.attached and not child.stopped and not child.close_attempted
        and hub.fixture is child.gate.backend.doc and hub.opened==['write-base','write-lora','read-lora']
        and hub.attached and not hub.stopped and hub.seq==4 and not hub.assurance.finished,
        'retained owner/pending/delegate state differs; never guess')
    require({p.name for p in q.glob('request-*.json')}=={'request-%04d.json'%n for n in range(1,10)}
        and {p.name for p in q.glob('response-*.json')}=={'response-%04d.json'%n for n in range(1,10)}
        and not (STATE/'hub-request-0004.json').exists(),'extra/missing requests forbid cleanup')
    for slot in UNUSED:
        require(not (STATE/(slot+'.engine-started.claim.json')).exists() and not (STATE/slot/'engine-created.json').exists(),
            'future slot may have opened')
    con=sqlite3.connect((q/'fixture.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
    con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON');con.execute('BEGIN')
    try:
        rows=[dict(r) for r in con.execute('SELECT * FROM c5_read')]
        require(len(rows)==1,'one completed read required')
        payload=validate_retired(read(STATE/'result.json'),read(q/'engine-created.json'),
            read(q/'request-0009.json'),read(q/'response-0009.json'),
            con.execute('SELECT COUNT(*) FROM candidate_write').fetchone()[0],rows[0])
    finally:con.close()
    original=read(q/'request-0009.json')
    gate_module=sys.modules[prefix+'c5_research_gate']
    require(hmac.compare_digest(original['envelope']['signature'],gate_module.signature(child.gate.secret,payload)),
        'original read signature differs; historical verification is not replay')
    backend=child.gate.backend;active=Rhino.RhinoDoc.ActiveDoc
    require(Rhino.RhinoApp.IsOnMainThread and active is not None and int(active.RuntimeSerialNumber)==268435457
        and native.active_content_digest(active)==ACTIVE_SHA and backend.serial==268435475
        and not backend.closed and Rhino.RhinoDoc.FromRuntimeSerialNumber(268435475) is not None
        and backend.readback()=={'groups':{},'objects':[],'unit':'Millimeters'}
        and child.gate.atomic.snapshot()==payload['expected'],'actual known empty fixture/active binding differs')
    original_result_sha=hashlib.sha256((STATE/'result.json').read_bytes()).hexdigest()
    channel.publish_json(STATE,ID+'.claim.json',{'study_id':ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    started=time.monotonic();progress={'study_id':ID,'retired_study_id':RETIRED,'original_result_sha256':original_result_sha}
    def budget():require(time.monotonic()-started<180,'logical cleanup budget reached; not CLR preemption')
    try:
        budget();child.blocked=hub.blocked=True
        Rhino.RhinoApp.Idle-=child._callback;child.attached=False
        progress['child_idle_exact_remove_call_completed']=True
        Rhino.RhinoApp.Idle-=hub._callback;hub.attached=False
        progress['hub_idle_exact_remove_call_completed']=True
        budget();child.close_attempted=True
        progress['fixture_close_attempted']=True
        closed=backend.close();progress['close_capture']=closed
        require(closed['fixture_registry_absent'] is True,'actual registry closure unknown')
        removed={}
        for directory,key in [(q,'handoff.key')]+[(STATE/s,'handoff.key') for s in UNUSED]+[(STATE,'hub.key')]:
            budget();removed[str((directory/key).relative_to(STATE))]=channel.remove_private_key(directory,key)
            progress['key_absence']=dict(removed)
        require(all(r=={'key_removed':True,'actual_absence_checked':True} for r in removed.values()) and len(removed)==7,
            'seven scoped key deletions not verified')
        child.stopped=hub.stopped=True
        budget();receipt=hub.assurance.finish();progress['host_receipt']=receipt
        channel.publish_json(STATE,'host-continuity-terminal-receipt.json',receipt)
        require(hub.assurance.detached and receipt['record_count']>=55,'observer exact detach not verified')
        package._SESSION=None
        require(native.active_content_digest(Rhino.RhinoDoc.ActiveDoc)==ACTIVE_SHA
            and hashlib.sha256((STATE/'result.json').read_bytes()).hexdigest()==original_result_sha,
            'active content/original failure changed')
        progress.update(status='retired_c_manual_safety_closed_not_frozen_success',
            fixture_registry_absent=True,complete_handler_absence_proven=False,field_remains_failure=True,
            geometry_tool_dispatches=0,model_calls=0,gpu_calls=0,holdout_calls=0)
        channel.publish_json(STATE,'manual-c-cleanup-result.json',progress)
        print('C5_MANUAL_C_HOST_EXTERNAL_RECEIPT '+json.dumps(receipt,sort_keys=True))
        print('C5_RETIRED_C_MANUAL_SAFETY_CLOSED_NO_REPLAY')
    except BaseException as exc:
        progress.update(status='manual_c_cleanup_failed_no_retry',error_type=type(exc).__name__,field_remains_failure=True)
        channel.publish_json(STATE,'manual-c-cleanup-failure.json',progress)
        raise


if __name__=='__main__':main()
