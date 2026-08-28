"""RhinoCoder 本地环境诊断。"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)


def _http_json(url: str) -> tuple[bool, str]:
    try:
        # 健康检查只访问固定 localhost 地址，不应继承系统代理设置。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=3) as response:  # noqa: S310 - localhost only
            payload = json.loads(response.read().decode("utf-8"))
        return True, json.dumps(payload, ensure_ascii=False)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python", (3, 11) <= sys.version_info[:2] < (3, 14), sys.version.split()[0]))
    checks.append(("MCP Server", (ROOT / "plugin/mcp_server/main.py").is_file(), "plugin/mcp_server/main.py"))
    checks.append(("UI build", (ROOT / "agent/ui/dist/index.html").is_file(), "agent/ui/dist/index.html"))

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    checks.append(("LLM config", bool(api_key and not api_key.startswith("<")), "configured" if api_key else "missing"))
    eval_token = os.environ.get("RHINOCODER_EVAL_TOKEN", "").strip()
    checks.append(("Eval token", bool(eval_token and not eval_token.startswith("<")), "configured" if eval_token else "missing"))

    rhino_ok, rhino_detail = _http_json("http://127.0.0.1:8080/health")
    ui_ok, ui_detail = _http_json("http://127.0.0.1:7860/api/health")
    checks.append(("Rhino Listener", rhino_ok, rhino_detail))
    try:
        rhino_payload = json.loads(rhino_detail) if rhino_ok else {}
    except json.JSONDecodeError:
        rhino_payload = {}
    reset_enabled = bool(rhino_payload.get("eval_reset_enabled"))
    checks.append(
        (
            "Rhino eval reset",
            reset_enabled,
            "enabled" if reset_enabled else "disabled; restart Listener after configuring .env",
        )
    )
    checks.append(("UI Server", ui_ok, ui_detail))

    for name, ok, detail in checks:
        print(f"{'✓' if ok else '✗'} {name:<16} {detail}")
    required = [ok for name, ok, _ in checks if name not in {"UI Server"}]
    return 0 if all(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
