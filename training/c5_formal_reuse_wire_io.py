"""Captured original bytes, one outstanding frame, no resend/reconnect.

Logical caps include write, read, strict decoding and receipt validation.
Raw stdout/stderr are drained by the already frozen CapturedStreams primitive.
"""
import time
from plugin.rhino_listener.c5_research_native import require
from training.c5_formal_reuse_model_wire import frame,strict_json,LIMIT
from training.c5_startup_transport import startup_receipt,validate_startup_receipt
from training.c5_followup_diagnostics import CapturedPipe

class StartupReadyPipe:
    def __init__(self,process,expected,*,capture,timeout=360,startup_timeout=600,clock=time.monotonic):
        require(type(timeout) in (int,float) and 0<timeout<=360
            and type(startup_timeout) in (int,float) and 0<startup_timeout<=600,
            'formal_reuse_finite_frame_deadline')
        validate_startup_receipt(expected,startup_receipt(expected['study_id'],expected['runtime_freeze_sha256'],
            expected['source_inventory_sha256'],expected['environment_sha256'],expected['model_identities']))
        self.process,self.capture,self.expected=process,capture,expected
        self.timeout,self.startup_timeout,self.clock=timeout,startup_timeout,clock
        self.pipe=CapturedPipe(process.stdin.fileno(),process.stdout.fileno(),capture)
        self.buffer=b'';self.blocked=self.ready=False
    def _receive(self,deadline):
        while b'\n' not in self.buffer:
            require(self.clock()<deadline,'formal_reuse_complete_frame_timeout')
            chunk=self.pipe.read(deadline)
            require(chunk,'formal_reuse_frame_eof_no_replay');self.buffer+=chunk
            require(len(self.buffer)<=LIMIT,'formal_reuse_frame_capacity')
        line,self.buffer=self.buffer.split(b'\n',1)
        require(not self.buffer,'formal_reuse_unsolicited_frame')
        value=strict_json(line);self.capture.check()
        require(self.clock()<deadline,'formal_reuse_decoded_frame_timeout');return value
    def wait_ready(self):
        if self.blocked or self.ready or self.buffer:
            self.blocked=True;require(False,'formal_reuse_ready_once')
        self.blocked=True;deadline=self.clock()+self.startup_timeout
        value=validate_startup_receipt(self._receive(deadline),self.expected)
        require(self.clock()<deadline,'formal_reuse_ready_validation_timeout')
        self.blocked=False;self.ready=True;return value
    def exchange(self,sent):
        if not self.ready or self.blocked:
            self.blocked=True;require(False,'formal_reuse_unresolved_no_send')
        self.blocked=True;deadline=self.clock()+self.timeout;raw=frame(sent)
        require(len(raw)<=65536,'formal_reuse_request_frame_capacity')
        self.capture.check();offset=0
        while offset<len(raw):
            count=self.pipe.write(raw[offset:],deadline)
            require(type(count) is int and 0<count<=len(raw)-offset,'formal_reuse_partial_write_unknown')
            offset+=count
        value=self._receive(deadline)
        self.blocked=False;return value
