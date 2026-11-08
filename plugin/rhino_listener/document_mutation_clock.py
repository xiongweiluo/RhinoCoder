"""Opt-in document-local ABA watermark; no Rhino import/effects on import.

The content fingerprint remains authoritative too. This clock covers the
listed document events, not arbitrary silent mutations by other plugins.
Missing/failed event bindings poison the session instead of falling back to
geometry equality or to a process-wide counter.
"""
import threading

from .candidate_atomic_gate import AtomicGateError

EVENTS = ('AddRhinoObject', 'DeleteRhinoObject', 'ReplaceRhinoObject',
          'UndeleteRhinoObject', 'PurgeRhinoObject', 'ModifyObjectAttributes',
          'LayerTableEvent', 'DocumentPropertiesChanged', 'GroupTableEvent')


class DocumentMutationClock:
    def __init__(self, serial, attach, detach, *, event_limit=256):
        if type(serial) is not int or serial <= 0 or type(event_limit) is not int or event_limit <= 0:
            raise AtomicGateError('invalid_document_clock')
        self.serial, self.attach, self.detach = serial, attach, detach
        self.thread = threading.get_ident()
        self.event_limit, self.epoch = event_limit, 0
        self.counts = dict.fromkeys(EVENTS, 0)
        self.bindings, self.faults = [], []
        self.active = self.started = self.closed = False
        self.close_result = None

    def _handler(self, name):
        def callback(sender, args):
            try:
                # Only identity of an unrelated document is accessed, never its
                # contents. An unreadable identity cannot safely be ignored.
                serial = int(args.Document.RuntimeSerialNumber)
                if serial != self.serial:
                    return
                if threading.get_ident() != self.thread or self.closed:
                    raise AtomicGateError('document_event_lifecycle')
                if self.epoch >= self.event_limit:
                    raise AtomicGateError('document_event_capacity')
                self.epoch += 1
                self.counts[name] += 1
            except BaseException:
                # Exceptions escaping a .NET event may be swallowed by Rhino.
                # Persist a bounded poison flag that every snapshot checks.
                if 'event_unverified' not in self.faults:
                    self.faults.append('event_unverified')
        return callback

    def start(self):
        if self.started or threading.get_ident() != self.thread:
            raise AtomicGateError('document_clock_start')
        self.started = True
        try:
            for name in EVENTS:
                callback = self._handler(name)
                # Retain even a partially attached delegate for exact removal.
                self.bindings.append((name, callback))
                self.attach(name, callback)
            self.active = True
        except BaseException:
            self.faults.append('subscription_unverified')
            self.close()
            raise

    def snapshot(self):
        if (not self.active or self.closed or self.faults or
                threading.get_ident() != self.thread or len(self.bindings) != len(EVENTS)):
            raise AtomicGateError('document_clock_unverified')
        return self.epoch

    def close(self):
        if self.closed or threading.get_ident() != self.thread:
            raise AtomicGateError('document_clock_close')
        self.closed, self.active = True, False
        removed = []
        for name, callback in reversed(self.bindings):
            try:
                self.detach(name, callback)
                removed.append(name)
            except BaseException:
                self.faults.append('detach_unverified:' + name)
        self.close_result = {'exact_delegates_removed': sorted(removed),
                'removal_verified': len(removed) == len(self.bindings),
                'counts': dict(self.counts), 'epoch': self.epoch, 'faults': list(self.faults)}
        return self.close_result


def for_rhino_document(doc):
    import Rhino
    def attach(name, callback):
        # Python.NET event operators, with the same callback retained for -=.
        event = getattr(Rhino.RhinoDoc, name)
        event.__iadd__(callback)
    def detach(name, callback):
        event = getattr(Rhino.RhinoDoc, name)
        event.__isub__(callback)
    return DocumentMutationClock(int(doc.RuntimeSerialNumber), attach, detach)
