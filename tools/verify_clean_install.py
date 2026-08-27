#!/usr/bin/env python3
"""在临时 clean-room 中复制公开仓库、安装锁定依赖并验证首次任务。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 600) -> None:
    print(f"[clean-room] {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=timeout)


def _copy_public_workspace(destination: Path) -> int:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    count = 0
    for relative_text in completed.stdout.splitlines():
        source = ROOT / relative_text
        if not source.is_file():
            continue
        target = destination / relative_text
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        count += 1
    return count


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _read_local_json(url: str, *, timeout: float) -> dict[str, object]:
    """读取本机验收接口，不继承可能劫持 localhost 的系统代理。"""
    with _DIRECT_OPENER.open(url, timeout=timeout) as response:
        return json.load(response)


async def _verify_replay_websocket(port: int) -> int:
    import aiohttp

    events = []
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"http://127.0.0.1:{port}/ws") as websocket:
            snapshot = await websocket.receive_json(timeout=5)
            if snapshot.get("type") != "snapshot":
                raise RuntimeError("首次 WebSocket 消息不是 snapshot")
            await websocket.send_json({"type": "replay", "name": "basic_stack.json"})
            while True:
                event = await websocket.receive_json(timeout=10)
                if event.get("replay"):
                    events.append(event)
                if event.get("type") == "run.completed":
                    break
    sequences = [event.get("seq") for event in events]
    if sequences != list(range(1, len(events) + 1)):
        raise RuntimeError(f"Replay 事件顺序错误: {sequences}")
    return len(events)


def _verify_offline_first_task(copy_root: Path, python: Path, env: dict[str, str]) -> int:
    port = _free_port()
    server_env = {**env, "RHINOCODER_RHINO_URL": "http://127.0.0.1:1"}
    process = subprocess.Popen(
        [str(python), "-m", "agent.ui_server", "--port", str(port)],
        cwd=copy_root,
        env=server_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        last_error = "尚未发起健康检查"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr else ""
                raise RuntimeError(f"UI Server 提前退出: {stderr[-1000:]}")
            try:
                health = _read_local_json(
                    f"http://127.0.0.1:{port}/api/health",
                    timeout=5,
                )
                if health.get("status") == "ok":
                    break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(0.2)
        else:
            raise RuntimeError(f"UI Server 健康检查超时；最后错误: {last_error}")
        replays = _read_local_json(
            f"http://127.0.0.1:{port}/api/replays",
            timeout=5,
        ).get("replays")
        expected = ["basic_stack.json", "self_correction.json", "table_group.json"]
        if replays != expected:
            raise RuntimeError(f"Replay 列表错误: {replays}")
        return asyncio.run(_verify_replay_websocket(port))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _live_environment(base: dict[str, str]) -> dict[str, str]:
    from dotenv import dotenv_values

    values = dotenv_values(ROOT / ".env") if (ROOT / ".env").is_file() else {}
    allowed = {
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_RETRIES",
        "LLM_INPUT_CACHE_HIT_COST_PER_M_TOKENS",
        "LLM_INPUT_CACHE_MISS_COST_PER_M_TOKENS",
        "LLM_OUTPUT_COST_PER_M_TOKENS",
        "LLM_PRICING_CHECKED_AT",
        "LLM_PRICING_SCHEDULE",
    }
    env = dict(base)
    for key in allowed:
        value = values.get(key) or os.environ.get(key)
        if value:
            env[key] = str(value)
    key = env.get("DEEPSEEK_API_KEY", "")
    if not key or key.startswith("<"):
        raise RuntimeError("--live 需要当前项目 .env 中的有效模型配置")
    return env


def verify_clean_install(*, local_rhino: bool, live: bool, keep: bool) -> dict[str, object]:
    if sys.platform != "darwin":
        raise RuntimeError("clean-room 发布验收必须在 macOS 执行")
    temp_root = Path(tempfile.mkdtemp(prefix="rhinocoder-clean-room-"))
    copy_root = temp_root / "RhinoCoder"
    copy_root.mkdir()
    try:
        copied = _copy_public_workspace(copy_root)
        env = dict(os.environ)
        env.update(
            {
                "RHINOCODER_PYTHON": sys.executable,
                "RHINOCODER_VENV_DIR": str(copy_root / ".venv"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        _run(["./scripts/bootstrap.sh"], cwd=copy_root, env=env)
        python = copy_root / ".venv" / "bin" / "python"
        if not python.is_file() or not (copy_root / "agent" / "ui" / "dist" / "index.html").is_file():
            raise RuntimeError("bootstrap 未生成 Python 虚拟环境或 UI 构建")
        env_text = (copy_root / ".env").read_text(encoding="utf-8")
        if "<your-deepseek-api-key>" not in env_text:
            raise RuntimeError("bootstrap 生成的 .env 不再是安全占位符")

        _run([str(python), "-m", "pytest", "-q"], cwd=copy_root, env=env)
        _run([str(python), "eval/run_eval.py", "--dry-run"], cwd=copy_root, env=env)
        _run([str(python), "tools/check_release_consistency.py"], cwd=copy_root, env=env)
        replay_events = _verify_offline_first_task(copy_root, python, env)

        local_rhino_completed = False
        if local_rhino:
            _run(
                [str(python), "tools/read_only_rhino_smoke.py"],
                cwd=copy_root,
                env=env,
                timeout=120,
            )
            local_rhino_completed = True

        live_completed = False
        if live:
            live_env = _live_environment(env)
            prompt = "读取当前 Rhino 场景摘要并报告对象数量；不要创建、删除、移动或修改任何对象。"
            _run(
                [str(python), "agent/main.py", "--prompt", prompt],
                cwd=copy_root,
                env=live_env,
                timeout=240,
            )
            live_completed = True
        result = {
            "passed": True,
            "platform": "macOS",
            "architecture": os.uname().machine,
            "python": ".venv/bin/python",
            "copied_files": copied,
            "offline_replay_events": replay_events,
            "local_mcp_rhino_read_only_task": local_rhino_completed,
            "live_read_only_task": live_completed,
            "workspace": str(copy_root) if keep else "removed_after_validation",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    finally:
        if not keep:
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-rhino", action="store_true", help="通过 localhost MCP 执行只读 Rhino 首任务，不调用外部 LLM")
    parser.add_argument("--live", action="store_true", help="额外运行只读 LLM + MCP + Rhino 首任务")
    parser.add_argument("--keep", action="store_true", help="验收后保留临时目录")
    args = parser.parse_args()
    try:
        verify_clean_install(local_rhino=args.local_rhino, live=args.live, keep=args.keep)
    except Exception as exc:
        print(f"Clean-room install verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
