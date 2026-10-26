"""Bounded streams and exact-owned Linux child supervision; no launch on import.

Only the subsequently approved entry may construct OwnedChild. Signals are
limited to its own Popen child pinned by pidfd, never a discovered process.
"""
import json
import os
import selectors
import signal
import subprocess
import time

from plugin.rhino_listener.c5_research_native import canonical, require

LIMIT = 1024 * 1024


class JsonPipe:
    def __init__(self, read_fd, write_fd):
        self.read_fd, self.write_fd, self.buffer = read_fd, write_fd, bytearray()
        os.set_blocking(read_fd, False)
        os.set_blocking(write_fd, False)

    def _wait(self, fd, event, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError('bounded pipe deadline')
        with selectors.DefaultSelector() as sel:
            sel.register(fd, event)
            if not sel.select(remaining): raise TimeoutError('bounded pipe deadline')

    def send(self, value, deadline):
        raw = (canonical(value) + '\n').encode()
        require(len(raw) <= LIMIT, 'oversized wire frame')
        position = 0
        while position < len(raw):
            self._wait(self.write_fd, selectors.EVENT_WRITE, deadline)
            try: position += os.write(self.write_fd, raw[position:])
            except BlockingIOError: continue

    def receive(self, deadline):
        def pairs(items):
            result = {}
            for key, value in items:
                require(key not in result, 'duplicate wire key')
                result[key] = value
            return result
        while b'\n' not in self.buffer:
            self._wait(self.read_fd, selectors.EVENT_READ, deadline)
            try: block = os.read(self.read_fd, min(65536, LIMIT + 1 - len(self.buffer)))
            except BlockingIOError: continue
            if not block: raise EOFError('wire closed before complete frame')
            self.buffer.extend(block)
            require(len(self.buffer) <= LIMIT, 'oversized wire frame')
        row, _, rest = self.buffer.partition(b'\n')
        self.buffer = bytearray(rest)
        return json.loads(row, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite wire value')))


class OwnedChild:
    def __init__(self, command, *, cwd, env, stderr, journal):
        require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'owned pidfd required')
        self.journal, self.fd, self.process = journal, None, None
        self.closed = False
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=stderr, start_new_session=True, close_fds=True)
        try:
            self.fd = os.pidfd_open(self.process.pid, 0)
            # Unreaped Popen child pinned before release; no name/PID discovery.
            journal('child-created', {'pid': self.process.pid, 'parent_pid': os.getpid(), 'command': command})
            self.pipe = JsonPipe(self.process.stdout.fileno(), self.process.stdin.fileno())
        except BaseException:
            # No release has been sent. The fixed worker must exit on EOF or
            # its ten-second admission timeout; unqualified children get no signal.
            self.process.stdin.close()
            try: self.process.wait(timeout=15)
            finally:
                self.process.stdout.close()
                if self.fd is not None: os.close(self.fd)
            raise

    def close(self):
        require(not self.closed, 'owned stop already attempted')
        self.closed = True
        attempts = []
        try:
            self.process.stdin.close()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                for sig, label, wait in [(signal.SIGTERM, 'SIGTERM', 10), (signal.SIGKILL, 'SIGKILL', 10)]:
                    if self.process.poll() is not None: break
                    self.journal('signal-intent-' + label, {'pid': self.process.pid, 'signal': label, 'attempts_max': 1})
                    signal.pidfd_send_signal(self.fd, sig, None, 0)
                    attempts.append(label)
                    try: self.process.wait(timeout=wait); break
                    except subprocess.TimeoutExpired: pass
            result = {'pid': self.process.pid, 'signals': attempts, 'exit_observed': self.process.poll() is not None,
                      'returncode': self.process.returncode, 'gpu_absence_verified': None}
            self.journal('child-stop', result)
            return result
        finally:
            os.close(self.fd)
            self.process.stdout.close()
