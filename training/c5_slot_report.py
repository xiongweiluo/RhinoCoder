"""Immutable review snapshots plus a bounded atomic redacted current pointer."""

import os, secrets
from plugin.rhino_listener.c5_research_channel import (
    private_directory,
    publish_json,
    read_json,
)
from plugin.rhino_listener.c5_research_native import digest, canonical, require


def publish_review(root, value):
    sha = digest(value)
    name = "slot-review-" + sha + ".json"
    if (root / name).exists():
        require(read_json(root, name) == value, "slot_review_snapshot_changed")
    else:
        publish_json(root, name, value)
    pointer = {
        "schema_version": 1,
        "study_id": value["study_id"],
        "campaign_head_sha256": value["campaign_head_sha256"],
        "summary_name": name,
        "summary_sha256": sha,
        "private_content_included": False,
    }
    fd = private_directory(root)
    temporary = "slot-review-" + secrets.token_hex(16) + ".tmp"
    try:
        out = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        with os.fdopen(out, "wb") as stream:
            stream.write((canonical(pointer) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        if (root / "slot-review-current.json").exists():
            read_json(root, "slot-review-current.json")
        os.replace(temporary, "slot-review-current.json", src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass
        os.close(fd)
    return pointer


def read_review(root, head):
    if not (root / "slot-review-current.json").exists():
        return None
    p = read_json(root, "slot-review-current.json")
    require(
        set(p)
        == {
            "schema_version",
            "study_id",
            "campaign_head_sha256",
            "summary_name",
            "summary_sha256",
            "private_content_included",
        }
        and p["schema_version"] == 1
        and p["private_content_included"] is False
        and type(p["summary_sha256"]) is str
        and len(p["summary_sha256"]) == 64
        and all(c in "0123456789abcdef" for c in p["summary_sha256"])
        and p["summary_name"] == "slot-review-" + p["summary_sha256"] + ".json",
        "slot_review_pointer_scope",
    )
    if p["campaign_head_sha256"] != head:
        return None
    value = read_json(root, p["summary_name"])
    require(
        digest(value) == p["summary_sha256"]
        and value["campaign_head_sha256"] == head
        and value["study_id"] == p["study_id"]
        and value["private_content_included"] is False,
        "slot_review_pointer_bytes",
    )
    return value
