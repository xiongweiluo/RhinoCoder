#!/usr/bin/env python3
"""Ask an opt-in Rhino idle session for one *read-only* write-grade snapshot."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
from pathlib import Path


def submit(directory: Path) -> tuple[str, Path]:
    fd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError("unsafe_session_directory")
        request_id = secrets.token_hex(32)
        name = "request-" + request_id + ".json"
        value = json.dumps({"version": 1, "request_id": request_id}, sort_keys=True).encode()
        request_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=fd)
        try:
            if os.write(request_fd, value) != len(value):
                raise IOError("short_request_write")
            os.fsync(request_fd)
        finally:
            os.close(request_fd)
        os.fsync(fd)
    finally:
        os.close(fd)
    return request_id, directory / ("response-" + request_id + ".json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    request_id, response = submit(args.directory)
    print(json.dumps({"request_id": request_id, "response": str(response)}, sort_keys=True))


if __name__ == "__main__":
    main()
