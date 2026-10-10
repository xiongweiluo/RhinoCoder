"""Isolated startup-ready phase; no model, task, host or state on import.

The whole exact owner lifecycle must admit the process beforehand. Readiness
is identity/zero-consumption evidence, never a tool permission. Unknown or
malformed frames permanently block; no reconnect, resend or parser repair.
Legacy FramedPipe and retired deployed studies remain untouched.
"""
import os
import selectors
import time

from plugin.rhino_listener.c5_research_native import digest, require
from training.c5_model_transport import FramedPipe, LIMIT, SHA, NAME, strict_json

PROTOCOL='c5-modelbridge-startup-ready-v1'


def startup_receipt(study_id,freeze_sha,source_sha,environment_sha,model_identities):
    require(isinstance(study_id,str) and NAME.fullmatch(study_id), 'startup study identity')
    require(all(isinstance(v,str) and SHA.fullmatch(v) for v in (freeze_sha,source_sha,environment_sha)),
        'startup complete freeze/source/environment binding')
    require(isinstance(model_identities,dict) and set(model_identities)=={'base','lora'}
        and all(isinstance(v,str) and SHA.fullmatch(v) for v in model_identities.values()),
        'startup both actual model identities required')
    return {'protocol':PROTOCOL,'study_id':study_id,'runtime_freeze_sha256':freeze_sha,
        'source_inventory_sha256':source_sha,'environment_sha256':environment_sha,
        'model_identities':dict(model_identities),'model_loaded':True,'generation_requests':0,
        'generation_stages':0,'holdout_rows_read':0,'status':'loaded_verified_ready_before_requests'}


def validate_startup_receipt(value,expected):
    require(isinstance(value,dict) and value==expected and digest(value)==digest(expected),
        'exact loaded zero-consumption startup receipt differs')
    return value


class StartupReadyPipe(FramedPipe):
    def __init__(self,process,expected,*,timeout=180,startup_timeout=180,clock=time.monotonic):
        super().__init__(process,timeout=timeout,clock=clock)
        require(type(startup_timeout) in (int,float) and 0<startup_timeout<=180, 'bounded startup window required')
        validate_startup_receipt(expected,startup_receipt(expected['study_id'],expected['runtime_freeze_sha256'],
            expected['source_inventory_sha256'],expected['environment_sha256'],expected['model_identities']))
        self.expected,self.startup_timeout,self.ready=expected,startup_timeout,False

    def wait_ready(self):
        if self.blocked or self.ready or self.buffer:
            self.blocked=True
            require(False,'startup can be consumed only once')
        self.blocked=True
        deadline=self.clock()+self.startup_timeout
        os.set_blocking(self.process.stdout.fileno(),False)
        with selectors.DefaultSelector() as poll:
            poll.register(self.process.stdout,selectors.EVENT_READ)
            while b'\n' not in self.buffer:
                remaining=deadline-self.clock()
                require(remaining>0 and poll.select(remaining), 'unknown startup readiness; no retry')
                chunk=os.read(self.process.stdout.fileno(),65536)
                require(chunk, 'startup EOF; no retry')
                self.buffer+=chunk
                require(len(self.buffer)<=LIMIT, 'startup frame exceeds bound')
        line,self.buffer=self.buffer.split(b'\n',1)
        require(not self.buffer,'unsolicited startup/task frames')
        value=validate_startup_receipt(strict_json(line),self.expected)
        self.ready,self.blocked=True,False
        return value

    def exchange(self,sent):
        if not self.ready:
            self.blocked=True
            require(False,'no task transmission before verified startup')
        return super().exchange(sent)
