"""Finite public-history load permit framing, not a private task frame.

Generic evidence records keep their original 256 KiB bound. This control
message retains the exact original ledger and all scope/chain checks.
"""
from training.c5_reuse_evidence import canonical, strict, require

from plugin.rhino_listener.c5_slot_tail_policy import POLICY

# Leave 256 KiB inside the existing 1 MiB export/JSON envelope for exit evidence.
MAX_BYTES = POLICY["public_load_permit_bytes_max"]


def encode(value):
    raw = canonical(value) + b'\n'
    require(len(raw) <= MAX_BYTES, 'formal_reuse_load_permit_size')
    return raw


def decode(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES
            and raw.endswith(b'\n'), 'formal_reuse_load_permit_frame')
    return strict(raw, limit=MAX_BYTES)


def receive(stream):
    return decode(stream.readline(MAX_BYTES + 1))


def saved(path):
    from training.c5_recovery_storage import read_private
    return decode(read_private(path))
