"""New local headless fixtures only; no access to existing document contents.

Not an entry point or grant. An approved, source-checked UI-thread host owns
the newly created fixture. Retains the existing geometry/read implementation,
with guards scoped to that document; no ActiveDoc read, switch or save.
"""
from __future__ import annotations

import threading

from .c5_research_native import NativeDoc, CORE, SCHEMA_SHA, digest, require


class DevelopmentDoc(NativeDoc):
    def __init__(self, fixture, schemas):
        import Rhino
        require(Rhino.RhinoApp.IsOnMainThread and fixture is not None
                and bool(fixture.IsHeadless) and not fixture.Path, "new unsaved headless fixture required")
        require(set(schemas) == CORE and digest(schemas) == SCHEMA_SHA, "unchanged native schemas required")
        self.doc, self.schemas = fixture, schemas
        self.serial, self.thread = int(fixture.RuntimeSerialNumber), threading.get_ident()
        self.closed, self.counter = False, 0
        self.guard()

    def guard(self):
        import Rhino
        require(not self.closed and threading.get_ident() == self.thread and Rhino.RhinoApp.IsOnMainThread,
                "closed or non-UI development fixture")
        registered = Rhino.RhinoDoc.FromRuntimeSerialNumber(self.serial)
        require(registered is not None and int(registered.RuntimeSerialNumber) == self.serial
                and int(self.doc.RuntimeSerialNumber) == self.serial and bool(self.doc.IsHeadless)
                and not self.doc.Path and str(self.doc.ModelUnitSystem) == "Millimeters",
                "owned headless document scope changed")

    def close(self):
        import Rhino
        require(not self.closed and threading.get_ident() == self.thread and Rhino.RhinoApp.IsOnMainThread
                and int(self.doc.RuntimeSerialNumber) == self.serial and bool(self.doc.IsHeadless)
                and not self.doc.Path, "close only this owned unsaved headless fixture")
        before, error = None, None
        try:
            before = self.readback()
        except Exception as exc:
            error = type(exc).__name__  # Bad geometry must not prevent owned-document disposal.
        self.doc.Dispose()
        self.closed = True
        require(Rhino.RhinoDoc.FromRuntimeSerialNumber(self.serial) is None,
                "owned fixture still registered after disposal")
        return {"status": "closed", "fixture_serial": self.serial, "fixture_registry_absent": True,
                "fixture_before_close_native": before, "readback_error": error,
                "existing_document_content_read": False}
