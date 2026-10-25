"""Bounded eight-slot field worker protocol; no implicit retry or provider."""
import time
from training.c5_reuse_evidence import exact,is_sha,require,sha,strict
from training.c5_reuse_field_scope import PROTOCOL,common_scope
from training.c5_reuse_field_wire import frame,FRAME_LIMIT
from training.c5_reuse_field_transport import READ_LIMIT
from training.c5_reuse_development_plan import ORDER


def receive(pipe,deadline,guard):
    raw=b''
    while b'\n' not in raw:
        guard();chunk=pipe.read(deadline)
        require(type(chunk) is bytes and 0<len(chunk)<=READ_LIMIT,'reuse_worker_eof_or_chunk')
        raw+=chunk
        require(len(raw)<=FRAME_LIMIT,'reuse_worker_frame_limit')
    require(raw.endswith(b'\n') and raw.count(b'\n')==1,'reuse_worker_extra_frame')
    value=strict(raw,limit=FRAME_LIMIT)
    require(raw==frame(value),'reuse_worker_frame_serialization')
    guard()
    return value


def send(pipe,value,deadline,guard):
    raw=frame(value);offset=0
    while offset<len(raw):
        guard();n=pipe.write(raw[offset:],deadline)
        require(type(n) is int and 0<n<=len(raw)-offset,'reuse_worker_partial_write')
        offset+=n
    guard()


def readiness(binding,qualification,worker_head):
    require(is_sha(qualification) and is_sha(worker_head),'reuse_worker_ready_anchors')
    return {'kind':'reuse_worker_loaded_ready','protocol':PROTOCOL,'scope_sha256':sha(common_scope(binding)),
            'qualification_sha256':qualification,'worker_open_head_sha256':worker_head,
            'model_requests_before_ready':0,'generation_stages_before_ready':0}


def validate_begin(value,binding):
    exact(value,('kind','protocol','scope_sha256','owner_readiness'))
    require(value['kind']=='reuse_begin_after_external_readiness' and value['protocol']==PROTOCOL
            and value['scope_sha256']==sha(common_scope(binding)),'reuse_worker_begin_scope')
    owner=value['owner_readiness']
    exact(owner,('study_id','instance_id','spec_sha256','runtime_sha256','host_baseline_head_sha256',
                'worker_readiness_sha256','actor','captured_after_host_baseline','approved_generation_start'))
    require(owner['study_id']==binding['study_id'] and owner['instance_id']==binding['instance_id']
            and owner['spec_sha256']==binding['spec_sha256'] and owner['runtime_sha256']==binding['runtime_sha256']
            and is_sha(owner['host_baseline_head_sha256']) and is_sha(owner['worker_readiness_sha256'])
            and owner['actor']=='repository_owner' and owner['captured_after_host_baseline'] is True
            and owner['approved_generation_start'] is True,'reuse_external_readiness_record')
    # Matching records do not prove direct human provenance; outside custody is
    # mandatory in the complete field audit and cannot be minted by this loop.
    return owner


def serve(peer,pipe,qualification,guard,budget,journal,*,clock=time.monotonic,on_ready=lambda:None,
          on_request_start=lambda:None,on_request_end=lambda:None,on_begin=lambda:None):
    require(set(peer.plans)==set(ORDER) and all(len(p['steps'])==1 for p in peer.plans.values()),'reuse_worker_exact_eight_plan')
    def check():guard();budget()
    check();ready=readiness(peer.binding,qualification,peer.journal.head)
    send(pipe,ready,clock()+180,check)
    journal('worker_ready_published',{'ready':ready})
    on_ready()
    begin=receive(pipe,clock()+180,check)
    owner=validate_begin(begin,peer.binding)
    require(owner['worker_readiness_sha256']==sha(ready),'reuse_external_worker_ready_binding')
    journal('worker_begin_record_received',{'begin':begin,'human_provenance_independently_verified':False})
    on_begin()
    for index,slot in enumerate(ORDER):
        gap=peer.binding['limits']['first_request_idle_seconds'] if index==0 else peer.binding['limits']['between_requests_idle_seconds']
        sent=receive(pipe,clock()+gap,check)
        require(sent['request']['slot_id']==slot and sent['request']['step_index']==0,'reuse_worker_order_no_fill')
        on_request_start()
        result=peer.infer(sent)
        send(pipe,result,clock()+180,check)
        on_request_end()
        if peer.journal.blocked:raise RuntimeError('reuse_worker_retired_no_retry')
    # An explicit close frame prevents an EOF from being advertised as complete.
    closing=receive(pipe,clock()+peer.binding['limits']['between_requests_idle_seconds'],check)
    require(closing=={'kind':'reuse_worker_close','protocol':PROTOCOL,'scope_sha256':sha(common_scope(peer.binding))},
            'reuse_worker_close_scope')
    final={'kind':'reuse_worker_closed','protocol':PROTOCOL,'scope_sha256':sha(common_scope(peer.binding)),
           'worker_final_head_sha256':peer.journal.head,'requests':len(peer.spent),'generation_intents':peer.stages,
           'physical_gpu_release_verified':None,'whole_field_pass':False}
    journal('worker_close_recorded',{'receipt':final})
    send(pipe,final,clock()+180,check)
    return final
