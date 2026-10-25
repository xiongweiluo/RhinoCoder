"""CPU-only diagnostic evidence/cleanup prototypes, unused by field entries.

No SSH, process discovery, model, grant or registry actions. Callbacks in
CPU tests are synthetic; this module grants no authority to live callbacks.
"""
import hashlib

class BoundedCapture:
    def __init__(self,cap=262144):
        if type(cap) is not int or not 1<=cap<=262144:raise ValueError('capture_cap')
        self.cap=cap;self.data=bytearray();self.total=0;self.hash=hashlib.sha256();self.finished=False
    def feed(self,chunk):
        if self.finished or type(chunk) is not bytes or not 0<len(chunk)<=65536:raise ValueError('capture_chunk')
        self.total+=len(chunk);self.hash.update(chunk)
        self.data.extend(chunk[:max(0,self.cap-len(self.data))])
    def finish(self,*,eof,exit_status):
        if self.finished or type(eof) is not bool or (exit_status is not None and type(exit_status) is not int):raise ValueError('capture_finish')
        self.finished=True
        return {'retained_bytes':len(self.data),'observed_bytes':self.total,'observed_bytes_sha256':self.hash.hexdigest(),
                'retained_bytes_sha256':hashlib.sha256(self.data).hexdigest(),'truncated':self.total>self.cap,
                'eof_observed':eof,'exit_status':exit_status,
                'complete_raw_capture':eof and self.total<=self.cap and exit_status is not None,
                'execution_success_proven':False,'execution_authority':False,'retry_allowed':False}

class FailureCleanupOnce:
    def __init__(self):self.used=False
    def run(self,gpu_stop,known_native_cleanup):
        if self.used:raise ValueError('cleanup_no_retry')
        self.used=True;rows=[]
        for name,callback in (('qualified_gpu_stop',gpu_stop),('known_native_cleanup',known_native_cleanup)):
            try:result=callback();rows.append({'action':name,'returned':result,'error_type':None})
            except BaseException as error:rows.append({'action':name,'returned':None,'error_type':type(error).__name__})
        return {'observations':rows,'whole_field_pass':False,'full_cleanup_proven':False,'execution_authority':False,'retry_allowed':False}
