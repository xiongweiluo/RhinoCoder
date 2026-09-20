#!/usr/bin/env python3
"""Authenticated loopback-only Qwen base/LoRA inference for P2 evaluation.

The server implements the narrow OpenAI Chat Completions surface used by the
agent.  It never reads A5 or P2 files, never binds a public interface, and logs
only hashes and token/resource metadata to a Git-ignored audit file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.config import DEFAULT_CONFIG, ReadinessError, load_config, project_path
from training.reporting import append_jsonl, git_revision
from training.runtime import _load_base_model, _load_tokenizer, _require_training_stack, require_gpu


TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = json.loads(json.dumps(messages, ensure_ascii=False))
    for message in normalized:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    function["arguments"] = json.loads(arguments)
                except json.JSONDecodeError:
                    pass
    return normalized


def _parse_tool_calls(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for index, raw in enumerate(TOOL_CALL_RE.findall(text), 1):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        arguments = value.get("arguments")
        if not name or not isinstance(arguments, dict):
            continue
        calls.append({
            "id": f"call_{index}_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
            },
        })
    return calls


class InferenceEngine:
    def __init__(
        self,
        *,
        mode: str,
        adapter: str | None,
        expected_adapter_sha256: str | None,
        config_path: str,
        audit_path: str,
    ) -> None:
        self.mode = mode
        self.audit_path = project_path(audit_path)
        self.git_revision = git_revision()
        self.config = load_config(config_path)
        self.stack = _require_training_stack()
        require_gpu(self.stack["torch"], self.config)
        self.tokenizer = _load_tokenizer(self.stack, self.config)
        base = _load_base_model(self.stack, self.config)
        if mode == "lora":
            if not adapter or not expected_adapter_sha256:
                raise ReadinessError(
                    "--adapter and --expected-adapter-sha256 are required for LoRA mode"
                )
            adapter_path = project_path(adapter).resolve()
            if not (adapter_path / "adapter_config.json").is_file():
                raise ReadinessError(f"adapter_config.json not found in {adapter_path}")
            model_path = adapter_path / "adapter_model.safetensors"
            actual_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
            if not secrets.compare_digest(actual_sha256, expected_adapter_sha256):
                raise ReadinessError("adapter_model.safetensors SHA-256 mismatch")
            self.adapter_model_sha256 = actual_sha256
            self.model = self.stack["PeftModel"].from_pretrained(
                base, str(adapter_path), is_trainable=False
            )
        else:
            self.adapter_model_sha256 = None
            self.model = base
        self.model.eval()
        self.model.config.use_cache = True
        self.stack["torch"].set_grad_enabled(False)

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages")
        tools = payload.get("tools") or []
        if not isinstance(messages, list) or not all(isinstance(item, dict) for item in messages):
            raise ValueError("messages must be a list of objects")
        if not isinstance(tools, list):
            raise ValueError("tools must be a list")
        rendered = self.tokenizer.apply_chat_template(
            _normalize_messages(messages),
            tools=tools or None,
            tokenize=False,
            add_generation_prompt=True,
        )
        encoded = self.tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
        encoded = {key: value.to(self.model.device) for key, value in encoded.items()}
        prompt_tokens = int(encoded["input_ids"].shape[1])
        started = time.monotonic()
        output = self.model.generate(
            **encoded,
            max_new_tokens=512,
            do_sample=False,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )
        continuation = output[0, prompt_tokens:]
        text = self.tokenizer.decode(continuation, skip_special_tokens=False)
        completion_tokens = int(continuation.shape[0])
        tool_calls = _parse_tool_calls(text)
        finish_reason = "tool_calls" if tool_calls else "stop"
        content = None if tool_calls else text.strip()
        request_id = "chatcmpl-" + uuid.uuid4().hex
        append_jsonl(self.audit_path, {
            "request_id": request_id,
            "created_at": _now(),
            "mode": self.mode,
            "git_revision": self.git_revision,
            "adapter_model_sha256": self.adapter_model_sha256,
            "request_sha256": _request_hash(payload),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tool_calls": len(tool_calls),
            "finish_reason": finish_reason,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "raw_content_persisted": False,
            "holdout_read": False,
        })
        return {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": f"qwen25-coder-7b-{self.mode}",
            "choices": [{
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content, "tool_calls": tool_calls},
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


class InferenceHandler(BaseHTTPRequestHandler):
    engine: InferenceEngine
    token: str

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "mode": self.engine.mode,
                    "git_revision": self.engine.git_revision,
                    "adapter_model_sha256": self.engine.adapter_model_sha256,
                },
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        supplied = self.headers.get("Authorization", "")
        if not secrets.compare_digest(supplied, "Bearer " + self.token):
            self._json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "unauthorized"}})
            return
        if self.path != "/v1/chat/completions":
            self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2_000_000:
                raise ValueError("invalid content length")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
            self._json(HTTPStatus.OK, self.engine.complete(payload))
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(exc)}})
        except Exception as exc:
            # The private server log may contain a traceback for operational
            # diagnosis, but never the request body, messages, token, or raw
            # model output.  The HTTP response remains type-only.
            traceback.print_exc()
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": {"message": f"{type(exc).__name__}: inference failed"}},
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("base", "lora"), required=True)
    parser.add_argument("--adapter")
    parser.add_argument("--expected-adapter-sha256")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument(
        "--audit-output",
        default="data/training/p2-model-comparison/inference-audit.jsonl",
    )
    args = parser.parse_args()
    if args.host not in LOOPBACK_HOSTS:
        raise SystemExit("refusing non-loopback bind")
    token = os.environ.get("RHINOCODER_P2_INFERENCE_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("RHINOCODER_P2_INFERENCE_TOKEN must contain at least 32 characters")
    engine = InferenceEngine(
        mode=args.mode,
        adapter=args.adapter,
        expected_adapter_sha256=args.expected_adapter_sha256,
        config_path=args.config,
        audit_path=args.audit_output,
    )
    handler = type("BoundInferenceHandler", (InferenceHandler,), {"engine": engine, "token": token})
    server = HTTPServer((args.host, args.port), handler)
    print(json.dumps({"status": "ready", "mode": args.mode, "host": args.host, "port": args.port}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
