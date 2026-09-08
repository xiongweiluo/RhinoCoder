#!/usr/bin/env python3
"""Generate the sanitized README GIF from the synthetic self-correction Replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "eval" / "replays" / "self_correction.json"
DEFAULT_OUTPUT = ROOT / "docs" / "assets" / "replay-demo.gif"


def _pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - maintainer-only asset generation
        raise SystemExit(
            "Pillow is required only to regenerate the GIF. Install it in a disposable "
            "environment; it is not a RhinoCoder runtime dependency."
        ) from exc
    return Image, ImageDraw, ImageFont


def _font(font_module: Any, size: int, *, bold: bool = False):
    candidates = [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return font_module.truetype(str(candidate), size=size, index=1 if bold and candidate.suffix == ".ttc" else 0)
    return font_module.load_default()


def _round(draw: Any, box: tuple[int, int, int, int], fill: str, outline: str = "#2c3a40", radius: int = 14) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def _text(draw: Any, xy: tuple[int, int], value: str, font: Any, fill: str = "#e8eef0") -> None:
    draw.text(xy, value, font=font, fill=fill)


def _event_title(event: dict[str, Any]) -> str:
    payload = event.get("payload") or {}
    return str(payload.get("name") or payload.get("tool") or event.get("type", "event"))


def _latest_scene(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for event in reversed(events):
        if event.get("type") == "scene.checked":
            return ((event.get("payload") or {}).get("scene_summary") or {}).get("objects") or []
    return []


def render_frame(events: list[dict[str, Any]], caption: str):
    Image, ImageDraw, ImageFont = _pillow()
    image = Image.new("RGB", (960, 540), "#0b0f11")
    draw = ImageDraw.Draw(image)
    title = _font(ImageFont, 25, bold=True)
    body = _font(ImageFont, 14)
    body_bold = _font(ImageFont, 14, bold=True)
    small = _font(ImageFont, 12)

    _text(draw, (34, 24), "RhinoCoder", title)
    _text(draw, (172, 32), "SANITIZED REPLAY · v0.3.0", small, "#79bea9")
    draw.ellipse((878, 31, 890, 43), fill="#72d6b9")
    _text(draw, (898, 29), "Replay", body, "#aebbc0")

    _round(draw, (28, 68, 932, 124), "#141b1e")
    _text(draw, (48, 82), "创建并校正一个蓝色球体", body_bold)
    _text(draw, (48, 104), caption, small, "#8fc9ff")

    route = next((event for event in events if event.get("type") == "route.selected"), None)
    _round(draw, (28, 138, 932, 196), "#142126", "#315047")
    _text(draw, (48, 151), "PRIVACY + ROUTE", small, "#79bea9")
    if route:
        payload = route.get("payload") or {}
        _text(draw, (48, 171), f"low risk  →  {payload.get('selected_backend')}  ·  no fallback", body_bold)
    else:
        _text(draw, (48, 171), "request enters local privacy gate", body, "#aebbc0")

    _round(draw, (28, 210, 600, 496), "#141b1e")
    _text(draw, (48, 228), "VERIFIABLE TOOL TRACE", small, "#79bea9")
    visible = events[-7:]
    y = 258
    for event in visible:
        event_type = str(event.get("type"))
        success = (event.get("payload") or {}).get("success")
        color = "#df665a" if success is False else "#72d6b9"
        draw.ellipse((50, y + 4, 60, y + 14), fill=color)
        _text(draw, (72, y), _event_title(event)[:33], body_bold)
        _text(draw, (360, y + 1), event_type[:27], small, "#84959b")
        y += 31

    _round(draw, (616, 210, 932, 366), "#141b1e")
    _text(draw, (636, 228), "SCENE SUMMARY", small, "#79bea9")
    scene = _latest_scene(events)
    if scene:
        obj = scene[0]
        color = tuple(obj.get("color") or [120, 130, 135])
        draw.ellipse((646, 270, 706, 330), fill=color, outline="#dbe8ec", width=2)
        _text(draw, (728, 270), str(obj.get("name") or obj.get("type")), body_bold)
        _text(draw, (728, 296), f"size  {' × '.join(map(str, obj.get('size') or []))}", small, "#aebbc0")
        _text(draw, (728, 319), "asserted geometry", small, "#8fc9ff")
    else:
        _text(draw, (636, 270), "Waiting for scene evidence…", body, "#718087")

    _round(draw, (616, 382, 932, 496), "#141b1e")
    checks = [event for event in events if event.get("type") == "assertion.checked"]
    status = "RUNNING"
    color = "#8fc9ff"
    if events and events[-1].get("type") == "run.completed":
        status, color = "COMPLETED · ASSERTIONS PASS", "#72d6b9"
    elif checks and (checks[-1].get("payload") or {}).get("success") is False:
        status, color = "MISMATCH FOUND · CORRECTING", "#ff9a8e"
    _text(draw, (636, 402), "STATUS", small, "#79bea9")
    _text(draw, (636, 430), status, body_bold, color)
    _text(draw, (636, 461), f"{len(events)} events · {len(checks)} assertion checks", small, "#aebbc0")

    _text(draw, (30, 514), "Synthetic coordinates and IDs · no real user/project data", small, "#718087")
    return image


def generate(source: Path, output: Path) -> None:
    Image, _, _ = _pillow()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("provenance") != "synthetic" or payload.get("privacy", {}).get("reviewed") is not True:
        raise SystemExit("Refusing to render a Replay that is not explicitly synthetic and privacy reviewed.")
    events = payload.get("events") or []
    stops = [1, 3, 5, 6, 7, 9, 10, 11, 12]
    captions = [
        "A natural-language task starts a traceable run.",
        "The local privacy gate approves sanitized geometry; rules choose a backend.",
        "Rhino geometry is read back through Scene Summary.",
        "A programmatic assertion finds the size/color mismatch.",
        "The closed loop starts a targeted correction.",
        "Scale and color tools update the same Rhino object.",
        "A second scene read captures the corrected result.",
        "The locked assertion now passes.",
        "The run completes with events, metrics, and evidence.",
    ]
    frames = [render_frame(events[:stop], caption) for stop, caption in zip(stops, captions, strict=True)]
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=[900, 900, 1100, 1300, 900, 900, 1000, 1100, 1800],
        loop=0,
        optimize=True,
        disposal=2,
    )
    with Image.open(output) as result:
        print(f"Generated {output.relative_to(ROOT)}: {result.n_frames} frames, {output.stat().st_size} bytes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    generate(args.source.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
