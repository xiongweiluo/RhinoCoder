#!/usr/bin/env python3
"""Validate the public P0 diagrams, Replay GIF, subtitles, and their hash manifest."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "demo" / "demo-assets-manifest.json"
EXPECTED_ARTIFACTS = {
    "docs/assets/replay-demo.gif",
    "docs/assets/architecture.svg",
    "docs/assets/data-flow.svg",
}
REQUIRED_TEXT_ASSETS = {
    "docs/demo/README.md",
    "docs/demo/demo-script.md",
    "docs/demo/rhinocoder-demo.zh-CN.srt",
    "docs/demo/rhinocoder-demo.en.srt",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gif_info(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    if len(data) < 13 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError("not a GIF")
    width, height = struct.unpack_from("<HH", data, 6)
    packed = data[10]
    offset = 13
    if packed & 0x80:
        offset += 3 * (2 ** ((packed & 0x07) + 1))
    frames = 0
    while offset < len(data):
        marker = data[offset]
        offset += 1
        if marker == 0x3B:
            break
        if marker == 0x21:
            if offset >= len(data):
                raise ValueError("truncated extension")
            offset += 1
            while True:
                if offset >= len(data):
                    raise ValueError("truncated extension data")
                size = data[offset]
                offset += 1
                if size == 0:
                    break
                offset += size
        elif marker == 0x2C:
            if offset + 9 > len(data):
                raise ValueError("truncated image descriptor")
            frames += 1
            descriptor_packed = data[offset + 8]
            offset += 9
            if descriptor_packed & 0x80:
                offset += 3 * (2 ** ((descriptor_packed & 0x07) + 1))
            offset += 1
            while True:
                if offset >= len(data):
                    raise ValueError("truncated image data")
                size = data[offset]
                offset += 1
                if size == 0:
                    break
                offset += size
        else:
            raise ValueError(f"unexpected GIF marker 0x{marker:02x}")
    return width, height, frames


def check_demo_assets(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    manifest_path = root / "docs" / "demo" / "demo-assets-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"demo asset manifest unreadable: {exc}"]

    source = manifest.get("source") or {}
    source_path = root / str(source.get("path", ""))
    if source.get("classification") != "synthetic_replay":
        findings.append("demo source is not classified as synthetic_replay")
    if not source_path.is_file():
        findings.append("demo source is missing")
    else:
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(f"demo source is invalid JSON: {exc}")
        else:
            if payload.get("provenance") != "synthetic" or payload.get("privacy", {}).get("reviewed") is not True:
                findings.append("demo source lacks synthetic/privacy-reviewed declarations")
        if _sha256(source_path) != source.get("sha256"):
            findings.append("demo source SHA-256 drift")

    artifacts = manifest.get("artifacts") or []
    paths = {item.get("path") for item in artifacts if isinstance(item, dict)}
    if paths != EXPECTED_ARTIFACTS:
        findings.append("demo artifact set does not match the required diagrams and GIF")
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            findings.append("invalid demo artifact entry")
            continue
        path = root / item["path"]
        if not path.is_file():
            findings.append(f"missing demo artifact: {item['path']}")
            continue
        if _sha256(path) != item.get("sha256"):
            findings.append(f"demo artifact SHA-256 drift: {item['path']}")
        if path.suffix == ".svg":
            text = path.read_text(encoding="utf-8")
            if "<svg" not in text or "<title" not in text or "<desc" not in text:
                findings.append(f"diagram lacks accessible SVG metadata: {item['path']}")
        elif path.suffix == ".gif":
            try:
                width, height, frames = _gif_info(path)
            except ValueError as exc:
                findings.append(f"invalid Replay GIF: {exc}")
            else:
                expected = (item.get("width"), item.get("height"), item.get("frames"))
                if (width, height, frames) != expected:
                    findings.append(f"Replay GIF dimensions/frames drift: {(width, height, frames)} != {expected}")

    for relative in REQUIRED_TEXT_ASSETS:
        path = root / relative
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            findings.append(f"missing or empty demo text asset: {relative}")
    return findings


def main() -> int:
    findings = check_demo_assets()
    if findings:
        print("Demo asset check failed:")
        for finding in findings:
            print(f"  ✗ {finding}")
        return 1
    print("Demo asset check passed (2 diagrams, 1 synthetic 9-frame GIF, 2 subtitle tracks).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
