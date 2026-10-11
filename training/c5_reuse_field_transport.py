"""New development framed channel over supplied descriptors; no launcher.

Complete deadline includes guards, durable intent/receive/ACK, and validation.
Unknown state retires the permanent controller admission without reconnect.
This is not the synthetic-only transport and grants no execution authority.
"""
import os
import selectors
import stat
import time

from training.c5_reuse_evidence import canonical, require, sha, strict
from training.c5_reuse_field_journal import FieldJournal
from training.c5_reuse_field_scope import validate_binding
from training.c5_reuse_field_wire import approved_request, validate_peer_result, FRAME_LIMIT, frame

READ_LIMIT=32768


class FieldPipe:
    def __init__(self,write_fd,read_fd,*,clock=time.monotonic):
        require(type(write_fd) is int and type(read_fd) is int and write_fd!=read_fd, 'field_pipe_fds')
        for fd in (write_fd,read_fd):
            info=os.fstat(fd)
            require(stat.S_ISFIFO(info.st_mode) or stat.S_ISSOCK(info.st_mode), 'field_pipe_type')
            os.set_blocking(fd,False)
        self.write_fd,self.read_fd,self.clock=write_fd,read_fd,clock

    def _wait(self,fd,kind,deadline):
        with selectors.DefaultSelector() as selector:
            selector.register(fd,kind)
            remaining=deadline-self.clock()
            require(remaining>0 and selector.select(remaining), 'field_pipe_deadline')

    def write(self,raw,deadline):
        while True:
            self._wait(self.write_fd,selectors.EVENT_WRITE,deadline)
            try: return os.write(self.write_fd,raw)
            except BlockingIOError: continue

    def read(self,deadline):
        while True:
            self._wait(self.read_fd,selectors.EVENT_READ,deadline)
            try: return os.read(self.read_fd,READ_LIMIT)
            except BlockingIOError: continue


class FieldModelChannel:
    def __init__(self,binding,registry,endpoint,guard,budget,plans,*,clock=time.monotonic,journal=None):
        validate_binding(binding)
        require(binding['endpoint']=='mac', 'field_controller_mac')
        require(sha(plans)==binding['development_plan_sha256'], 'field_transport_plan')
        guard(); budget()
        if journal is None:
            journal=FieldJournal(binding,'controller',registry)
        else:
            from training.c5_reuse_field_journal import read_journal
            require(journal.binding==binding and journal.role=='controller' and len(journal.records)==1
                    and journal.records[0]['kind']=='open' and not journal.blocked,'field_new_supervised_controller_journal')
            require(read_journal(journal.root,binding,'controller',journal.head)==journal.records,'field_supervised_controller_disk')
        require(journal.lock.acquire(blocking=False),'field_controller_ownership_busy')
        try:
            require(not getattr(journal,'controller_owner_attached',False),'field_controller_owner_already_attached')
            journal.controller_owner_attached=True
        finally:journal.lock.release()
        self.journal=journal
        self.binding=self.journal.binding
        self.plans=strict(canonical(plans))
        self.endpoint,self.guard,self.budget,self.clock=endpoint,guard,budget,clock
        self.spent=set()

    def exchange(self,sent):
        require(self.journal.lock.acquire(blocking=False), 'field_exchange_active')
        try:
            require(not self.journal.blocked, 'field_transport_retired_no_retry')
            sent=strict(canonical(sent),limit=FRAME_LIMIT)
            approved_request(self.binding,sent,self.plans)
            key=(sent['request']['slot_id'],sent['request']['step_index'])
            require(key not in self.spent and len(self.spent)<56, 'field_request_consumed')
            start=last=self.clock()
            deadline=start+180
            def check():
                nonlocal last
                now=self.clock()
                require(last<=now<deadline, 'field_whole_exchange_deadline')
                last=now
                self.guard(); self.budget()
            check()
            self.journal.blocked=True
            self.spent.add(key)
            raw=frame(sent)
            self.journal.append('wire_intent',{'request_sha256':sha(sent),'frame_hex':raw.hex()})
            offset=0
            while offset<len(raw):
                check()
                count=self.endpoint.write(raw[offset:],deadline)
                require(type(count) is int and 0<count<=len(raw)-offset, 'field_partial_write_count')
                offset+=count
            self.journal.append('wire_sent',{'request_sha256':sha(sent),'bytes':offset})
            check()
            buffer=b''
            while b'\n' not in buffer:
                check()
                chunk=self.endpoint.read(deadline)
                require(type(chunk) is bytes, 'field_receive_type')
                self.journal.append('wire_received',{'request_sha256':sha(sent),'raw_hex':chunk[:READ_LIMIT].hex(),
                    'observed_bytes':len(chunk),'truncated':len(chunk)>READ_LIMIT})
                require(0<len(chunk)<=READ_LIMIT, 'field_eof_or_oversize_chunk')
                buffer+=chunk
                require(len(buffer)<=FRAME_LIMIT, 'field_response_size')
            require(buffer.endswith(b'\n') and buffer.count(b'\n')==1, 'field_extra_or_partial_frame')
            result=strict(buffer,limit=FRAME_LIMIT)
            require(buffer==frame(result), 'field_response_serialization')
            observed=validate_peer_result(self.binding,sent,result)
            check()
            self.journal.append('wire_ack',{'request_sha256':sha(sent),'frame_sha256':sha(result)})
            check()
            self.journal.blocked=observed['status']=='operational_failure_no_retry'
            return result
        except BaseException as error:
            self.journal.blocked=True
            try: self.journal.append('wire_retired',{'error_type':type(error).__name__})
            except BaseException: pass  # Torn/unwritable evidence stays incomplete.
            raise
        finally:
            self.journal.lock.release()
