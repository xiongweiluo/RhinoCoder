"""Bounded C5 development wire, no loader, fixture, approval or holdout access.

The separately frozen lifecycle entry must claim the route/fixture before
using this module. A constructor is not owner authority. Nothing here can
repair a model output, change a prompt, retry or grant a Rhino permission.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import selectors
import time

from plugin.rhino_listener.c5_research_channel import publish_json,read_json
from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_contract import CONTRACT_ID, DECODE_CONFIG
from training.c5_rhino_adapter import invoke_step, step_input

PROTOCOL = 'c5-modelbridge-development-v1'
LIMIT = 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}\Z')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z')
REQUEST_KEYS = {'protocol','probe_id','request_id','slot_id','route','step_index',
                'task','scene','binding_sha256','runtime_freeze_sha256'}
RESPONSE_KEYS = {'protocol','request_sha256','runtime_freeze_sha256','model_identity_sha256',
                 'observation','generation_receipts','seconds','status'}


def strict_json(raw):
    require(isinstance(raw,bytes) and 0 < len(raw) <= LIMIT,'bounded UTF-8 wire required')
    def pairs(items):
        value = {}
        for key,item in items:
            require(key not in value,'duplicate wire key')
            value[key] = item
        return value
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite wire JSON')))


def frame(value):
    raw = (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    require(len(raw) <= LIMIT,'wire frame exceeds bound')
    return raw


def request(probe_id,slot_id,route,step_index,task,scene,binding,runtime_freeze_sha256,request_id):
    require(isinstance(binding,dict) and set(binding)=={'document_key','revision','scene_sha256'}
            and type(binding['revision']) is int and binding['revision'] >= 0
            and all(isinstance(binding[k],str) and SHA.fullmatch(binding[k]) for k in ('document_key','scene_sha256')),
            'trusted actual pre-generation binding required')
    value = {'protocol':PROTOCOL,'probe_id':probe_id,'request_id':request_id,'slot_id':slot_id,
             'route':route,'step_index':step_index,'task':task,'scene':scene,
             'binding_sha256':digest(binding),'runtime_freeze_sha256':runtime_freeze_sha256}
    validate_request(value)
    return strict_json(frame(value))  # Detach mutable caller data.


def validate_request(value):
    require(isinstance(value,dict) and set(value)==REQUEST_KEYS and value['protocol']==PROTOCOL,'exact development wire required')
    require(all(isinstance(value[k],str) and NAME.fullmatch(value[k]) for k in ('probe_id','request_id','slot_id'))
            and value['route'] in {'base','lora'} and type(value['step_index']) is int
            and 0 <= value['step_index'] < 4,'request identity/step budget differs')
    require(all(isinstance(value[k],str) and SHA.fullmatch(value[k]) for k in ('binding_sha256','runtime_freeze_sha256')),
            'wire freeze/state digest differs')
    require(isinstance(value['task'],str) and len(value['task'].encode()) <= 4096,'bounded task required')
    outbound = step_input(value['task'],value['scene'])  # Physical IDs/scoring fields rejected.
    from agent.privacy import classify_request,PrivacyAction
    require(classify_request(outbound).action is PrivacyAction.ALLOW_CLOUD,'privacy refused before remote transmission')
    # Extra fail-closed restriction of this DEVELOPMENT wire only. Never
    # relax/change the default product privacy classifier or redact-and-send.
    require(not re.search(r'身份证|护照|密码|API[_ -]?KEY|(?<!\d)\d{17}[\dXx](?!\d)',outbound,re.I),
            'sensitive content refused by isolated development wire')
    frame(value)


def validate_response(value, sent, model_identity_sha256):
    validate_request(sent)
    require(isinstance(value,dict) and set(value)==RESPONSE_KEYS and value['protocol']==PROTOCOL
            and value['request_sha256']==digest(sent)
            and value['runtime_freeze_sha256']==sent['runtime_freeze_sha256']
            and value['model_identity_sha256']==model_identity_sha256
            and value['status']=='completed_one_attempt_not_authorized','response scope/model identity differs')
    require(type(value['seconds']) in (int,float) and math.isfinite(value['seconds']) and value['seconds'] >= 0,
            'response duration differs')
    observed,generated = value['observation'],value['generation_receipts']
    require(isinstance(observed,dict) and observed.get('contract_id')==CONTRACT_ID
            and set(observed) in ({'contract_id','status','calls','user_step_sha256','scene_binding',
                                   'name','arguments','repair_count','dispatch_count'},
                                  {'contract_id','status','calls','user_step_sha256','scene_binding',
                                   'name','arguments','repair_count','dispatch_count','error_type'})
            and observed.get('status') in {'abstained_no_dispatch','unsupported_for_c5_no_dispatch',
                'selector_contract_failure_no_dispatch','invocation_contract_failure_no_dispatch',
                'schema_valid_not_authorized','operational_failure_no_retry'}
            and observed.get('scene_binding') is None
            and all(type(observed.get(k)) is int and observed[k]==0 for k in ('repair_count','dispatch_count'))
            and observed.get('user_step_sha256')==hashlib.sha256(step_input(sent['task'],sent['scene']).encode()).hexdigest(),
            'remote observation binding/contract differs')
    require(isinstance(observed.get('calls'),list) and isinstance(generated,list)
            and 1 <= len(generated)==len(observed['calls']) <= 2
            and [c.get('stage') for c in observed['calls']]==['selector','invocation'][:len(observed['calls'])],
            'generation receipt count/stage differs')
    require((observed['status']=='schema_valid_not_authorized') ==
            (len(observed['calls'])==2 and observed['calls'][-1].get('parsed') is True
             and isinstance(observed.get('name'),str) and isinstance(observed.get('arguments'),dict)),
            'successful structured call status differs')
    for i,(call,generation) in enumerate(zip(observed['calls'],generated)):
        require(isinstance(call,dict) and set(call) in (
                {'stage','prompt_sha256','generation_attempted','parsed'},
                {'stage','prompt_sha256','generation_attempted','parsed','raw','output_sha256'})
                and call['generation_attempted'] is True and type(call['parsed']) is bool
                and generation['stage']==call['stage']==('selector' if i==0 else 'invocation')
                and type(generation['tokens']) is int and 0 <= generation['tokens'] <= DECODE_CONFIG[call['stage']+'_max_new_tokens']
                and type(generation['seconds']) in (int,float) and math.isfinite(generation['seconds']) and generation['seconds'] >= 0
                and generation['prompt_sha256']==call['prompt_sha256']
                and generation['attempted'] is True,'stage/count/latency receipt differs')
        if 'raw' in call:
            require(generation.get('raw')==call['raw']
                    and generation.get('output_sha256')==call['output_sha256']==hashlib.sha256(call['raw'].encode()).hexdigest(),
                    'raw generation hash differs')
        else:
            require(observed['status']=='operational_failure_no_retry' and generation.get('error_type'),
                    'missing raw without retained operational failure')
    frame(value)
    return observed


class OneShotModelSession:
    """Remote core. A verified lifecycle supplies exact plans/source/model.

    Every (slot, step) is O_EXCL spent before rendering/generation. Neither
    a new request ID nor another instance using the same state can replay it.
    Raw stage evidence survives a crash after generation. Plans contain only
    natural user steps and bounded policy, not scorer labels/tool parameters.
    """
    def __init__(self,probe_id,freeze_sha,plans,state,tokenizer,generate,route_context,identities,guard,check_budget):
        self.probe_id,self.freeze,self.plans,self.state = probe_id,freeze_sha,plans,state
        self.tokenizer,self.generate,self.route_context = tokenizer,generate,route_context
        self.identities,self.guard,self.check_budget = identities,guard,check_budget
        self.blocked = False

    def infer(self,sent):
        require(not self.blocked,'uncertain model session blocked')
        validate_request(sent)
        require(sent['probe_id']==self.probe_id and sent['runtime_freeze_sha256']==self.freeze,'new frozen development scope differs')
        plan = self.plans.get(sent['slot_id'])
        require(plan is not None and plan['route']==sent['route']
                and sent['step_index'] < len(plan['steps']) and sent['task']==plan['steps'][sent['step_index']],
                'task outside approved development plan')
        self.guard(); self.check_budget()
        key = digest({'slot':sent['slot_id'],'step':sent['step_index'],'freeze':self.freeze})
        if sent['step_index']:
            prior_key = digest({'slot':sent['slot_id'],'step':sent['step_index']-1,'freeze':self.freeze})
            prior = read_json(self.state,prior_key+'-response.json')
            require(prior['observation']['status']=='schema_valid_not_authorized','cannot continue failed/abstained model slot')
        publish_json(self.state,'generation-'+key+'.claim.json',{'request_sha256':digest(sent),'replay_allowed':False})
        self.blocked = True
        receipts = []
        started = time.monotonic()
        def generate(prompt,stage):
            self.guard(); self.check_budget()
            item = {'stage':stage,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                    'attempted':True,'tokens':0,'seconds':0.0}
            receipts.append(item)
            publish_json(self.state,key+'-'+stage+'-attempt.json',item)
            call_started = time.monotonic()
            try:
                raw = self.generate(prompt,stage)
                require(isinstance(raw,dict) and isinstance(raw.get('raw'),str),'model raw generation missing')
                item.update(raw)
                require(item['prompt_sha256']==hashlib.sha256(prompt.encode()).hexdigest()
                        and item['output_sha256']==hashlib.sha256(item['raw'].encode()).hexdigest(),'actual model generation hash differs')
            except BaseException as exc:
                item.update(error_type=type(exc).__name__,seconds=time.monotonic()-call_started)
                publish_json(self.state,key+'-'+stage+'-failure.json',item)
                raise
            publish_json(self.state,key+'-'+stage+'-raw.json',item)
            try:
                self.guard(); self.check_budget()
            except BaseException as exc:
                item['error_type'] = type(exc).__name__
                publish_json(self.state,key+'-'+stage+'-postcheck-failure.json',item)
                raise
            return raw
        with self.route_context(sent['route']):
            observed = invoke_step(self.tokenizer,generate,step_input(sent['task'],sent['scene']))
        value = {'protocol':PROTOCOL,'request_sha256':digest(sent),'runtime_freeze_sha256':self.freeze,
                 'model_identity_sha256':self.identities[sent['route']],'observation':observed,
                 'generation_receipts':receipts,'seconds':time.monotonic()-started,
                 'status':'completed_one_attempt_not_authorized'}
        validate_response(value,sent,self.identities[sent['route']])
        publish_json(self.state,key+'-response.json',value)
        # Model contract failures are classified, never repaired. Operational
        # uncertainty blocks ALL further generation in this process.
        self.blocked = observed['status']=='operational_failure_no_retry'
        return value


class FramedPipe:
    """Private SSH subprocess pipes. At most one outstanding request; no resend.

    The lifecycle must record a permanent local slot claim before exchange.
    Timeout/EOF/bad frame leaves this object permanently blocked. No automatic
    kill/reconnect/restart is provided; actual remote settlement must be read.
    """
    def __init__(self,process,*,timeout=120,clock=time.monotonic):
        require(type(timeout) in (int,float) and 0 < timeout <= 180,'bounded pipe timeout required')
        self.process,self.timeout,self.clock = process,timeout,clock
        self.buffer = b''
        self.blocked = False

    def exchange(self,sent):
        require(not self.blocked,'unresolved transport; do not reconnect/retry')
        self.blocked = True
        data = frame(sent)
        require(len(data) <= 65536,'bounded pipe request required')
        deadline = self.clock()+self.timeout
        os.set_blocking(self.process.stdin.fileno(),False)
        os.set_blocking(self.process.stdout.fileno(),False)
        # Complete a single frame's known remaining bytes, never retransmit
        # its prefix/full request. The write itself must not block forever.
        offset = 0
        with selectors.DefaultSelector() as writer:
            writer.register(self.process.stdin,selectors.EVENT_WRITE)
            while offset < len(data):
                remaining = deadline-self.clock()
                require(remaining > 0 and writer.select(remaining),'uncertain remote pipe write timeout')
                try: wrote = os.write(self.process.stdin.fileno(),data[offset:])
                except BlockingIOError: continue
                require(wrote > 0,'uncertain remote pipe write')
                offset += wrote
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout,selectors.EVENT_READ)
            while b'\n' not in self.buffer:
                remaining = deadline-self.clock()
                require(remaining > 0 and selector.select(remaining),'unknown remote acknowledgement; no retry')
                chunk = os.read(self.process.stdout.fileno(),65536)
                require(chunk,'unexpected remote EOF; no retry')
                self.buffer += chunk
                require(len(self.buffer) <= LIMIT,'remote frame exceeds bound')
        line,self.buffer = self.buffer.split(b'\n',1)
        require(not self.buffer,'unsolicited extra remote frame')
        value = strict_json(line)
        require(isinstance(value,dict) and value.get('request_sha256')==digest(sent),'wrong/late remote response binding')
        self.blocked = False
        return value


def rebind_observation(response,sent,model_identity_sha256,actual_binding):
    """Trusted Mac boundary, not a signing operation. Reparses unchanged raw.

    A later ResearchSigner must still recheck the current scene/task/schema
    before consumption; this digest binding is no permission itself.
    """
    require(digest(actual_binding)==sent['binding_sha256'],'local actual scene changed during generation')
    observed = strict_json(frame(validate_response(response,sent,model_identity_sha256)))
    from training.c5_inventory import load_public_mcp_tools
    from training.c5_contract import parse_selection,parse_invocation
    if observed['status']=='schema_valid_not_authorized':
        tools = load_public_mcp_tools()
        selected = parse_selection(observed['calls'][0]['raw'],tools)
        parsed = parse_invocation(observed['calls'][1]['raw'],selected,tools)
        require(parsed['name']==observed['name'] and parsed['arguments']==observed['arguments'],'unchanged raw/parsed observation differs')
    observed['scene_binding'] = strict_json(frame(actual_binding))
    return observed
