"""Synthetic-only injected framed transport; no SSH, models or Rhino imports.

One intent is fsynced before IO. Partial writes advance a byte offset; they
never resend a prefix. Any ambiguous write/EOF/timeout/frame/ACK retires this
session. No reconnect, automatic stop signal or recovery command exists.
"""
import os
import selectors
import time

from training.c5_reuse_evidence import MAX_FRAME, require, request, strict, validate_response, wire


class PipeEndpoint:
    """CPU fixture adapter for already supplied file descriptors.

    This creates no process or connection. Caller owns exact CPU fixture process
    lifetime. Availability deadlines are logical, not hard OS/CUDA preemption.
    """
    def __init__(self, write_fd, read_fd, clock=time.monotonic):
        require(type(write_fd) is int and type(read_fd) is int and write_fd != read_fd, 'pipe_fds')
        self.write_fd, self.read_fd, self.clock = write_fd, read_fd, clock
        os.set_blocking(write_fd, False)
        os.set_blocking(read_fd, False)

    def _wait(self, fd, kind, deadline):
        left = deadline - self.clock()
        require(left > 0, 'pipe_deadline')
        with selectors.DefaultSelector() as selector:
            selector.register(fd, kind)
            require(selector.select(left), 'pipe_deadline')

    def write(self, remaining, deadline):
        while True:
            self._wait(self.write_fd, selectors.EVENT_WRITE, deadline)
            try:
                return os.write(self.write_fd, remaining)
            except BlockingIOError:
                continue

    def read(self, deadline):
        while True:
            self._wait(self.read_fd, selectors.EVENT_READ, deadline)
            try:
                return os.read(self.read_fd, MAX_FRAME + 1)
            except BlockingIOError:
                continue


class SyntheticTransport:
    def __init__(self, journal, endpoint, *, timeout=1.0, clock=time.monotonic):
        require(type(timeout) in (int, float) and 0 < timeout <= 180, 'timeout_bound')
        self.journal, self.endpoint, self.timeout, self.clock = journal, endpoint, timeout, clock
        summary = journal.summary
        self.blocked = bool(summary['retired'] or summary['sealed'] or summary['unresolved_requests'])

    def exchange(self, slot, route, step=0):
        # One outstanding exchange across all wrappers sharing this journal,
        # including reentrant callbacks and multiple threads in one process.
        require(self.journal.exchange_lock.acquire(blocking=False), 'exchange_already_active')
        try:
            return self._exchange_locked(slot, route, step)
        finally:
            self.journal.exchange_lock.release()

    def _exchange_locked(self, slot, route, step):
        require(not self.blocked, 'session_retired_no_retry')
        sent = request(self.journal.identity, slot, route, step)
        raw = wire(sent)
        # Deliberately no IO before the durable immutable intent.
        self.journal.append({'kind': 'intent', 'request_raw': raw.decode()})
        self.blocked = True
        started = self.clock()
        deadline = started + self.timeout
        last = started
        def check():
            nonlocal last
            now = self.clock()
            require(last <= now < deadline, 'whole_exchange_deadline')
            last = now
        try:
            offset = 0
            while offset < len(raw):
                check()
                count = self.endpoint.write(raw[offset:], deadline)
                require(type(count) is int and 0 < count <= len(raw) - offset, 'partial_write_count')
                offset += count
            check()
            self.journal.append({'kind': 'sent', 'request_id': sent['request_id'], 'bytes': offset})
            buffer = b''
            while b'\n' not in buffer:
                check()
                chunk = self.endpoint.read(deadline)
                require(type(chunk) is bytes and chunk, 'pipe_eof_or_invalid')
                # Persist malformed, partial and late bytes before validating.
                # Normal endpoints cap a single read at MAX_FRAME + 1.
                require(len(chunk) <= MAX_FRAME + 1, 'read_chunk_bound')
                self.journal.append({'kind': 'received', 'request_id': sent['request_id'],
                                     'raw_hex': chunk.hex()})
                buffer += chunk
                require(len(buffer) <= MAX_FRAME, 'frame_bound')
            require(buffer.endswith(b'\n') and buffer.count(b'\n') == 1, 'extra_or_partial_frame')
            value = strict(buffer, MAX_FRAME)
            validate_response(value, sent)
            require(buffer == wire(value), 'response_serialization')
            # Deadline includes parsing/validation and durable ACK evidence.
            check()
            self.journal.append({'kind': 'ack', 'request_id': sent['request_id'], 'response_raw': buffer.decode()})
            check()
        except BaseException:
            # Do not erase an ACK observed just before a late deadline; retire
            # separately. Never leak exception strings or reconnect on failure.
            try:
                self.journal.append({'kind': 'retire', 'reason': 'transport_unknown'})
            except BaseException:
                pass  # A poisoned/torn journal remains incomplete, not repaired.
            raise
        self.blocked = False
        return value
