"""Fixed native12 client; NEW owner grant required, no model/GPU/holdout loader.

No arbitrary spec/output/recovery paths; original B and all formal entries are
unreachable. Preparation/engine claims and every raw response remain private.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import secrets
import time

from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_research_gate import signature
from plugin.rhino_listener.c5_research_native import READS,digest,require
from plugin.rhino_listener.c5_research_provenance import SourceGuard
from tools.c5_native12_common import ROOT,STATE,OUTPUT,ID,TASK,fixed_scope
from training.c5_inventory import load_public_mcp_tools
from training.consent_candidate import ConsentStore,DELEGATED_HEADLESS_SCOPE
from training.tool_controller_candidate import SceneState
from training.c5_research_audit import audit_permission_execution
from training.c5_rhino_scorer import score_readback


def scope():
    spec,freeze,schemas,approval=fixed_scope()
    source=SourceGuard(ROOT,freeze['source_files'],freeze['source_inventory_sha256'])
    source()
    return spec,freeze,schemas,approval,source


def prepare():
    spec,freeze,schemas,approval,source=scope()
    publish_json(STATE,ID+'.admission.claim.json',{'probe_id':ID,'spec_sha256':digest(spec),
                 'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    OUTPUT.mkdir(mode=0o700)  # Exclusive; fresh output is not recovery.
    publish_json(OUTPUT,'owner-approval.json',approval)
    publish_json(OUTPUT,'handoff.key',{'key_hex':secrets.token_bytes(32).hex()})
    publish_json(OUTPUT,'prepared.json',{'probe_id':ID,'spec_sha256':digest(spec),
                 'runtime_freeze_sha256':digest(freeze),'source_inventory_sha256':freeze['source_inventory_sha256'],
                 'model_calls':0,'gpu_calls':0,'formal_holdout_calls':0})
    return {'status':'prepared_owner_approved_not_executed','probe_id':ID}


class Scene:
    """Cached actual UI capture; native gate independently rejects any drift.

    This is not an oracle or a claim that cached state is a fresh Rhino read.
    Permission can be spent if state subsequently drifts; no write is retried.
    """
    def __init__(self,capture): self.capture=capture
    def snapshot(self):
        state=self.capture['state']
        rows=self.capture['native']['objects']
        summary={'unit':'Millimeters','objects':[{k:r[k] for k in ('alias','min','max','layer','color','groups')} for r in rows],
                 'groups':self.capture['native']['groups']}
        return SceneState(state['revision'],state['scene_sha256'],summary)


class FixedClient:
    def __init__(self,source,secret,freeze_sha,*,clock=time.time,monotonic=time.monotonic):
        self.source,self.secret,self.freeze_sha=source,secret,freeze_sha
        self.clock,self.monotonic=clock,monotonic
        self.seq,self.deadline=1,monotonic()+300
        self.unresolved=False

    def exchange(self,kind,envelope):
        self.source()
        require(not self.unresolved and self.seq<=40 and self.monotonic()<self.deadline,'bounded/unknown client state')
        self.unresolved=True
        publish_json(OUTPUT,'request-%04d.json'%self.seq,{'kind':kind,'envelope':envelope})
        stop=min(self.monotonic()+25,self.deadline)
        name='response-%04d.json'%self.seq
        while not (OUTPUT/name).exists():
            if self.monotonic()>=stop: raise TimeoutError('unknown native acknowledgement; never resend or guess cleanup')
            time.sleep(0.05)
        result=read_json(OUTPUT,name)
        self.unresolved=False
        self.seq+=1
        return result

    def control(self,action):
        p={'version':1,'request_id':secrets.token_urlsafe(24),'task_sha256':hashlib.sha256(TASK.encode()).hexdigest(),
           'owner_freeze_sha256':self.freeze_sha,'action':action,'expires_at':int(self.clock())+120}
        return self.exchange('control',{'payload':p,'signature':signature(self.secret,p)})


def drive():
    spec,freeze,schemas,approval,source=scope()
    require(read_json(STATE,ID+'.admission.claim.json')['runtime_freeze_sha256']==digest(freeze), 'admission missing/different')
    require(read_json(STATE,ID+'.engine-started.json')['runtime_freeze_sha256']==digest(freeze), 'engine claim missing/different')
    # A driver crash is not a retry permission, even if the scene is empty.
    publish_json(STATE,ID+'.driver-started.json',{'probe_id':ID,'runtime_freeze_sha256':digest(freeze),'replay_allowed':False})
    bootstrap=read_json(OUTPUT,'bootstrap.json')
    require(bootstrap['owner_freeze_sha256']==digest(freeze) and bootstrap['task_sha256']==hashlib.sha256(TASK.encode()).hexdigest()
            and bootstrap['source_sha256']==freeze['source_inventory_sha256'] and not bootstrap['native']['objects'], 'fresh bootstrap differs')
    client=FixedClient(source,bytes.fromhex(read_json(OUTPUT,'handoff.key')['key_hex']),digest(freeze))
    store=ConsentStore(OUTPUT/'consent.sqlite3',load_public_mcp_tools())
    with store._tx() as db:
        db.execute('CREATE TABLE c5_native_control_handoff (observation_sha256 TEXT PRIMARY KEY,state TEXT NOT NULL,request_id TEXT UNIQUE,payload_sha256 TEXT)')
    result={'probe_id':ID,'status':'native12_incomplete','receipts':[],'cleanup_verified':False,
            'model_calls':0,'gpu_calls':0,'formal_holdout_calls':0,'formal_quality_claim':False}
    error=None
    try:
        for index,step in enumerate(spec['steps']):
            actual=client.control('capture')
            require(actual.get('status')=='captured','native capture failed')
            scene=Scene(actual)
            name,args=step['name'],step['arguments']
            observation=digest({'spec_sha256':digest(spec),'ordinal':index,'actual_state':actual['state'],'fixed_call':step})
            with store._tx() as db:
                db.execute("INSERT INTO c5_native_control_handoff VALUES(?,'reserved',NULL,NULL)",(observation,))
            if name in READS:
                request_id,row_sha,expiry=secrets.token_urlsafe(24),None,int(time.time())+120
            else:
                link=store.prepare(TASK,name,args,scene=scene,ttl_seconds=120,delegated_scope=DELEGATED_HEADLESS_SCOPE)
                require(store.approve_delegated_headless(link)=='approved','fixed disposable permission failed')
                store._consume(link,task=TASK,tool_name=name,arguments=args,scene=scene)
                row,_=store.inspect(link)
                request_id,row_sha,expiry=link.request_id,digest(row),row['expires_at']
            p={'version':1,'request_id':request_id,'task_sha256':hashlib.sha256(TASK.encode()).hexdigest(),
               'owner_freeze_sha256':digest(freeze),'expected':actual['state'],'operation':name,'arguments':args,
               'consent_row_sha256':row_sha,'expires_at':expiry}
            if name not in READS:
                with store._tx() as db: store._event(db,request_id,'signed_handoff_issued',digest(p))
            with store._tx() as db:
                db.execute("UPDATE c5_native_control_handoff SET state='issued',request_id=?,payload_sha256=? WHERE observation_sha256=?",(request_id,digest(p),observation))
            receipt=client.exchange('execute',{'payload':p,'signature':signature(client.secret,p)})
            result['receipts'].append(receipt)
            require(receipt.get('status')=='done','native step failed; do not continue mutations')
        # Predeclared terminal negative: no fabricated permission is consumed,
        # and no model observation is invented. The invalid signature must be
        # rejected before reservation; only close/stop follows the blocked UI.
        p={**result['receipts'][-1]['payload'],'request_id':secrets.token_urlsafe(24),
           'operation':'create_box','arguments':{'width':2,'depth':3,'height':4},
           'expected':result['receipts'][-1]['after_state'],'consent_row_sha256':'e'*64,
           'expires_at':int(time.time())+120}
        result['terminal_negative']=client.exchange('execute',{'payload':p,'signature':'0'*64})
        require(result['terminal_negative'].get('status')=='failed_no_retry'
                and result['terminal_negative'].get('error')=='handoff signature rejected','terminal invalid signature not rejected as frozen')
    except BaseException as exc:
        error=type(exc).__name__+': '+str(exc)
    # Unknown acknowledgement means no guessed close or repeated request.
    if not client.unresolved:
        try:
            result['close']=client.control('close')
            require(result['close'].get('status')=='closed','close unverified')
            result['stop']=client.control('stop')
            require(result['stop'].get('status')=='stopped','stop unverified')
            result['cleanup_verified']=True
        except BaseException as exc:
            error=(error+'; ' if error else '')+type(exc).__name__+': '+str(exc)
    result['error']=error
    result['status']='native12_execution_complete_not_independently_audited' if error is None and len(result['receipts'])==12 else 'native12_fail_retired_no_replay'
    publish_json(OUTPUT,'result.json',result)
    return {k:result[k] for k in ('probe_id','status','error','cleanup_verified','model_calls','gpu_calls','formal_holdout_calls')}


def audit():
    spec,freeze,schemas,approval,source=scope()
    result=read_json(OUTPUT,'result.json')
    require(result['status']=='native12_execution_complete_not_independently_audited'
            and result['error'] is None and len(result['receipts'])==12,'incomplete/failed run not promoted')
    receipts=result['receipts']
    for name in (ID+'.admission.claim.json',ID+'.engine-started.json',ID+'.driver-started.json'):
        claim=read_json(STATE,name)
        require(claim['probe_id']==ID and claim['runtime_freeze_sha256']==digest(freeze)
                and claim['replay_allowed'] is False,'permanent claim differs')
    actual_requests=sorted(p.name for p in OUTPUT.iterdir() if p.name.startswith('request-') and p.suffix=='.json')
    require(actual_requests==['request-%04d.json'%i for i in range(1,28)],'extra/missing request beyond fixed transcript')
    require([r['payload']['operation'] for r in receipts]==[s['name'] for s in spec['steps']]
            and [r['payload']['arguments'] for r in receipts]==[s['arguments'] for s in spec['steps']], 'actual fixed execution differs')
    for index,receipt in enumerate(receipts):
        raw=read_json(OUTPUT,'execute-%04d.json'%(2*index+2))
        require(raw['payload']==receipt['payload'] and raw['result']==receipt['result']
                and raw['after']==receipt['immediate_after'] and raw['after_state']==receipt['immediate_after_state']
                and receipt['stable_idle_samples']==3 and len(receipt['settling_samples'])>=3,
                'raw/settled evidence differs')
        stable=receipt['settling_samples'][-3:]
        require(stable[0]==stable[1]==stable[2] and stable[-1]['native']==receipt['after']
                and stable[-1]['state']==receipt['after_state'],'settling not independently stable')
    bound=audit_permission_execution(OUTPUT/'consent.sqlite3',OUTPUT/'fixture.sqlite3',receipts,
                                    task_sha256=hashlib.sha256(TASK.encode()).hexdigest(),owner_freeze_sha256=digest(freeze),
                                    handoff_table='c5_native_control_handoff')
    # Fixed, independent mathematical assertions for EVERY native step;
    # never copy a claimed success flag or only score the final bbox.
    for index,receipt in enumerate(receipts[:-1]):
        if index<3:
            box={'min':[0,0,0],'max':[17,19,23],'centroid':[8.5,9.5,11.5],'volume':7429,'solid':True,'face_count':6}
        elif index==3:
            box={'min':[11,13,17],'max':[28,32,40],'centroid':[19.5,22.5,28.5],'volume':7429,'solid':True,'face_count':6}
        elif index==4:
            box={'min':[-32,11,17],'max':[-13,28,40],'centroid':[-22.5,19.5,28.5],'volume':7429,'solid':True,'face_count':6}
        else:
            box={'min':[-64,33,68],'max':[-26,84,160],'centroid':[-45,58.5,114],'volume':178296,'solid':True,'face_count':6}
        if index>=6: box['layer']='C5DEV::native12'
        if index>=7: box['color']=[37,83,149]
        box['groups']=['native12_group'] if index>=8 else []
        objects={'box-1':box}
        if index>=1:
            objects['sphere-2']={'min':[-5,-5,-5],'max':[5,5,5],'centroid':[0,0,0],
                                 'volume':500*math.pi/3,'solid':True,'face_count':1,'groups':[]}
        if index>=2:
            objects['cylinder-3']={'min':[-3,-3,0],'max':[3,3,7],'centroid':[0,0,3.5],
                                   'volume':63*math.pi,'solid':True,'face_count':3,
                                   'groups':['native12_group'] if index>=8 else []}
        changed=({'box-1'} if 3<=index<=7 else {'box-1','cylinder-3'} if index==8 else set())
        unchanged=[o['alias'] for o in receipt['before']['objects'] if o['alias'] not in changed]
        if index in {0,1,2}: unchanged=[o['alias'] for o in receipt['before']['objects']]
        read_expected=None
        if index==9:
            read_expected={'object_id':'box-1','min':[-64,33,68],'max':[-26,84,160],'center':[-45,58.5,114]}
        elif index==10:
            read_expected={**receipt['before'],'objects':[{k:r[k] for k in ('alias','min','max','layer','color','groups')} for r in receipt['before']['objects']]}
        check=score_readback(receipt['before'],receipt['after'],{'object_count':len(objects),
                              'objects':objects,'unchanged':unchanged,'read_result':read_expected},
                              read_result=receipt['result'] if index in {9,10} else None)
        require(check['geometry_passed'],'independent native stage failed: '+str(index+1))
    expected=spec['independent_assertions']
    box=dict(expected['box_final']); box.pop('alias')
    difference=dict(expected['difference_final']); difference.pop('alias')
    difference['volume']=difference.pop('volume_pi_multiple')*math.pi
    last=receipts[-1]
    assertions={'object_count':2,'objects':{'box-1':box,'difference-4':difference},'unchanged':['box-1'],'read_result':None}
    geometry=score_readback(last['before'],last['after'],assertions)
    require(geometry['geometry_passed'] and last['after']['groups']==expected['final_group_members'],'independent geometry/attributes failed')
    close,stop=result['close'],result['stop']
    negative=read_json(OUTPUT,'response-0025.json')
    require(negative==result['terminal_negative'] and negative['status']=='failed_no_retry'
            and negative['error']=='handoff signature rejected' and negative['error_type']=='NativeError', 'expected negative response differs')
    require(not (OUTPUT/'execute-0025.json').exists(),'negative unexpectedly produced execute receipt')
    capture=close['close_capture']
    bootstrap=read_json(OUTPUT,'bootstrap.json')
    created=read_json(OUTPUT,'engine-created.json')
    require(created['python_major_minor']==[3,9] and created['rhino_major']==8
            and created['rhino_version'] and created['python_version'],'actual runtime family/version not recorded')
    require(created['fixture_serial']==bootstrap['fixture_serial']
            and created['active_serial']==bootstrap['active_serial']
            and created['runtime_freeze_sha256']==bootstrap['owner_freeze_sha256']==digest(freeze)
            and bootstrap['source_sha256']==freeze['source_inventory_sha256'],'engine/bootstrap source identity differs')
    require(close['status']=='closed' and stop['status']=='stopped' and stop['had_failure'] is True
            and capture['fixture_registry_absent'] is True and capture['fixture_serial']==bootstrap['fixture_serial']
            and capture['before_close_active_serial']==capture['after_close_active_serial']==bootstrap['active_serial']
            and close['source_sha256']==stop['source_sha256']==freeze['source_inventory_sha256']
            and capture['initial_active_sha256']==capture['before_close_active_sha256']==capture['after_close_active_sha256']==bootstrap['active_sha256']==close['active_sha256']==stop['active_sha256']
            and close['key_absence']=={'key_removed':True,'actual_absence_checked':True}
            and capture['fixture_before_close_native']==receipts[-1]['after']
            and not (OUTPUT/'handoff.key').exists() and stop['hook_removed_in_same_callback'] is True,
            'raw closure/key/stop/active proof differs')
    return {'probe_id':ID,'status':'independent_native12_development_control_verified_not_model_quality',
            'source_inventory_sha256':freeze['source_inventory_sha256'],'spec_sha256':digest(spec),'runtime_freeze_sha256':digest(freeze),
            'signed_write_requests':bound['write_count'],'signed_read_requests':bound['read_count'],
            'terminal_invalid_signature_rejected_no_dispatch':True,
            'native_tools_covered':12,'model_calls':0,'gpu_calls':0,'formal_holdout_calls':0,
            'rhino_version':created['rhino_version'],'python_version':created['python_version'],
            'formal_quality_claim':False,'complete_C5_engineering_gate_passed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','drive','audit'))
    a=parser.parse_args()
    import json
    print(json.dumps({'prepare':prepare,'drive':drive,'audit':audit}[a.mode](),ensure_ascii=False,sort_keys=True))


if __name__=='__main__': main()
