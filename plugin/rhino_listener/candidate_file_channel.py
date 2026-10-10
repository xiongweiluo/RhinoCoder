"""Private same-host file handoff for signed R candidate envelopes.

No watcher, Listener route, or automatic retry is installed. The issuer writes
one complete signed request atomically; the Rhino-side caller explicitly reads
one named request on the main thread. A replay still reaches the atomic gate,
which refuses it. File ownership/mode and HMAC are checked at both ends.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import stat
from contextlib import contextmanager

from .candidate_envelope_gate import _canonical, _signature, _validate_payload


_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{24,128}\Z")
_MAX_ENVELOPE_BYTES = 8192
_NOFOLLOW = os.O_NOFOLLOW  # Candidate is Mac/Linux-only; no symlink-follow fallback.
_DIRECTORY = os.O_DIRECTORY


class ChannelError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@contextmanager
def _private_directory(path):
    try:
        descriptor = os.open(str(path), os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ChannelError("unsafe_channel_directory")
        yield descriptor
    except ChannelError:
        raise
    except OSError as exc:
        raise ChannelError("channel_unavailable") from exc
    finally:
        if "descriptor" in locals():
            os.close(descriptor)


def _read_owned_file(directory_fd, name, expected_size=None):
    descriptor = None
    try:
        descriptor = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=directory_fd)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ChannelError("unsafe_channel_file")
        if info.st_size > _MAX_ENVELOPE_BYTES or (expected_size is not None and info.st_size != expected_size):
            raise ChannelError("invalid_channel_file_size")
        value = os.read(descriptor, _MAX_ENVELOPE_BYTES + 1)
        if len(value) != info.st_size:
            raise ChannelError("channel_file_changed")
        return value
    except ChannelError:
        raise
    except OSError as exc:
        raise ChannelError("channel_file_unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def create_private_channel(path):
    """Explicit one-time initialization; never overwrite an existing channel."""

    try:
        os.mkdir(str(path), 0o700)
    except FileExistsError as exc:
        raise ChannelError("channel_already_exists") from exc
    except OSError as exc:
        raise ChannelError("channel_unavailable") from exc
    with _private_directory(path) as directory_fd:
        descriptor = None
        try:
            descriptor = os.open("handoff.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                                 0o600, dir_fd=directory_fd)
            secret = secrets.token_bytes(32)
            if os.write(descriptor, secret) != len(secret):
                raise ChannelError("secret_write_incomplete")
            os.fsync(descriptor)
            os.fsync(directory_fd)
        except OSError as exc:
            raise ChannelError("secret_creation_failed") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
    return path


def load_private_secret(path):
    with _private_directory(path) as directory_fd:
        return _read_owned_file(directory_fd, "handoff.key", expected_size=32)


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ChannelError("duplicate_json_key")
        value[key] = item
    return value


def _checked_envelope(envelope, secret):
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
        raise ChannelError("invalid_envelope")
    try:
        payload = json.loads(_canonical(envelope["payload"]))
        _validate_payload(payload)
        signature = envelope["signature"]
        expected = _signature(secret, payload)
    except Exception as exc:
        raise ChannelError("invalid_envelope") from exc
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise ChannelError("invalid_signature")
    return {"payload": payload, "signature": signature}


def publish_signed_envelope(path, envelope):
    """Atomically publish one request; target filename cannot be overwritten."""

    secret = load_private_secret(path)
    checked = _checked_envelope(envelope, secret)
    request_id = checked["payload"]["request_id"]
    if not _REQUEST_ID.fullmatch(request_id):
        raise ChannelError("invalid_request_id")
    encoded = _canonical(checked).encode("utf-8")
    if len(encoded) > _MAX_ENVELOPE_BYTES:
        raise ChannelError("envelope_too_large")
    target = request_id + ".json"
    temporary = ".handoff-" + secrets.token_urlsafe(18)
    with _private_directory(path) as directory_fd:
        descriptor = None
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                                 0o600, dir_fd=directory_fd)
            if os.write(descriptor, encoded) != len(encoded):
                raise ChannelError("envelope_write_incomplete")
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            os.link(temporary, target, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                    follow_symlinks=False)
            os.fsync(directory_fd)
        except FileExistsError as exc:
            raise ChannelError("request_already_published") from exc
        except OSError as exc:
            raise ChannelError("publish_failed") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
    return request_id


def read_signed_envelope(path, request_id):
    """Read one exact request; no directory scan or automatic execution."""

    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ChannelError("invalid_request_id")
    secret = load_private_secret(path)
    with _private_directory(path) as directory_fd:
        raw = _read_owned_file(directory_fd, request_id + ".json")
    try:
        envelope = json.loads(raw, object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ChannelError("invalid_json") from exc
    checked = _checked_envelope(envelope, secret)
    if checked["payload"]["request_id"] != request_id:
        raise ChannelError("request_id_mismatch")
    return checked
