"""Privacy classification, cloud minimization, and outbound request auditing."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REQUEST_AUDIT_PATH = PROJECT_ROOT / "data" / "audit" / "model_requests.jsonl"
_AUDIT_LOCK = threading.Lock()


class PrivacyRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PrivacyAction(str, Enum):
    ALLOW_CLOUD = "allow_cloud"
    MINIMIZE_CLOUD = "minimize_cloud"
    FORCE_LOCAL = "force_local"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class PrivacySignal:
    code: str
    risk: PrivacyRisk
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "risk": self.risk.value,
            "reason": self.reason,
        }


@dataclass(slots=True)
class PrivacyDecision:
    decision_id: str
    timestamp: str
    risk: PrivacyRisk
    action: PrivacyAction
    reason_codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    cloud_allowed: bool = True
    requires_minimization: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk"] = self.risk.value
        payload["action"] = self.action.value
        return payload


class PrivacyViolation(RuntimeError):
    def __init__(self, code: str, message: str, findings: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.findings = list(findings)


SECRET_PATTERNS = (
    ("openai_style_key", re.compile(r"\b(?:sk|rk_live)-[A-Za-z0-9_-]{12,}\b")),
    ("github_token", re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{16,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
    (
        "bearer_token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(?:api[_ -]?key|access[_ -]?token|password|secret)\b"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{8,}"
        ),
    ),
)
POSIX_PATH_PATTERN = re.compile(r"(?<![\w.])/(?:Users|home|private|var|tmp|Volumes)/[^\s\"']+")
WINDOWS_PATH_PATTERN = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]+")
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
LABELED_IDENTITY_PATTERN = re.compile(
    r"(?i)(['\"]?(?:客户|业主|项目(?:代号|名称)?|工程名|customer|client|"
    r"project(?:[_ ]?(?:name|code))?)['\"]?)"
    r"\s*[:：=]\s*['\"]?([^\s,，。;；\n\"'<][^,，。;；\n\"']{1,79})['\"]?"
)
LAYER_PATTERN = re.compile(
    r"(?i)(['\"]?(?:layer(?:[_ ]?name)?|图层)['\"]?)"
    r"\s*[:：=]\s*['\"]?([^\s,，。;；\n\"'<][^,，。;；\n\"']{0,79})['\"]?"
)
GROUP_PATTERN = re.compile(
    r"(?i)(['\"]?(?:group(?:[_ ]?name)?|群组)['\"]?)"
    r"\s*[:：=]\s*['\"]?([^\s,，。;；\n\"'<][^,，。;；\n\"']{0,79})['\"]?"
)
LOCAL_ONLY_PATTERN = re.compile(
    r"(?i)(?:不要上传|禁止上云|仅本地|只在本地|本地处理|local[- ]only|do not upload)"
)
PROMPT_INJECTION_PATTERNS = (
    re.compile(r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions?"),
    re.compile(r"(?i)(?:reveal|print|show|dump|exfiltrate).{0,40}(?:system prompt|developer message|secret|token|environment)"),
    re.compile(r"(?i)(?:read|open|print|upload).{0,30}(?:\.env|credentials?|id_rsa|keychain)"),
    re.compile(r"(?:忽略|绕过).{0,20}(?:之前|以上|系统|开发者|安全).{0,20}(?:指令|规则|限制)"),
    re.compile(r"(?:泄露|显示|输出|上传|窃取).{0,30}(?:系统提示|开发者消息|密钥|令牌|环境变量|凭证)"),
    re.compile(r"(?:读取|打开).{0,20}(?:\.env|私钥|钥匙串|环境变量)"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_prompt_injection(value: str) -> bool:
    return any(pattern.search(value) for pattern in PROMPT_INJECTION_PATTERNS)


def detect_privacy_signals(prompt: str) -> list[PrivacySignal]:
    signals: list[PrivacySignal] = []
    for code, pattern in SECRET_PATTERNS:
        if pattern.search(prompt):
            signals.append(PrivacySignal(code, PrivacyRisk.CRITICAL, "请求包含凭证或密钥值"))
    if _has_prompt_injection(prompt):
        signals.append(
            PrivacySignal(
                "prompt_injection_or_exfiltration",
                PrivacyRisk.CRITICAL,
                "请求试图覆盖指令或提取系统/凭证数据",
            )
        )
    if LOCAL_ONLY_PATTERN.search(prompt):
        signals.append(PrivacySignal("explicit_local_only", PrivacyRisk.HIGH, "请求明确禁止上云"))
    if POSIX_PATH_PATTERN.search(prompt) or WINDOWS_PATH_PATTERN.search(prompt):
        signals.append(PrivacySignal("local_file_path", PrivacyRisk.HIGH, "请求包含本地文件路径"))
    if LABELED_IDENTITY_PATTERN.search(prompt):
        signals.append(
            PrivacySignal("customer_or_project_identity", PrivacyRisk.HIGH, "请求包含客户或项目标识")
        )
    if LAYER_PATTERN.search(prompt):
        signals.append(PrivacySignal("project_layer_name", PrivacyRisk.HIGH, "请求包含项目图层名"))
    if GROUP_PATTERN.search(prompt):
        signals.append(PrivacySignal("project_group_name", PrivacyRisk.HIGH, "请求包含项目群组名"))
    if EMAIL_PATTERN.search(prompt):
        signals.append(PrivacySignal("email_address", PrivacyRisk.MEDIUM, "请求包含邮箱地址"))
    return signals


def classify_request(prompt: str) -> PrivacyDecision:
    signals = detect_privacy_signals(prompt)
    risks = {signal.risk for signal in signals}
    if PrivacyRisk.CRITICAL in risks:
        risk = PrivacyRisk.CRITICAL
        action = PrivacyAction.BLOCK
    elif PrivacyRisk.HIGH in risks:
        risk = PrivacyRisk.HIGH
        action = PrivacyAction.FORCE_LOCAL
    elif PrivacyRisk.MEDIUM in risks:
        risk = PrivacyRisk.MEDIUM
        action = PrivacyAction.MINIMIZE_CLOUD
    else:
        risk = PrivacyRisk.LOW
        action = PrivacyAction.ALLOW_CLOUD
    return PrivacyDecision(
        decision_id=str(uuid4()),
        timestamp=_now(),
        risk=risk,
        action=action,
        reason_codes=[signal.code for signal in signals] or ["no_sensitive_signal"],
        reasons=[signal.reason for signal in signals] or ["未检测到需要阻断的隐私信号"],
        cloud_allowed=action in {PrivacyAction.ALLOW_CLOUD, PrivacyAction.MINIMIZE_CLOUD},
        requires_minimization=action is not PrivacyAction.ALLOW_CLOUD,
    )


def _redact_secret_patterns(value: str) -> str:
    for _code, pattern in SECRET_PATTERNS:
        value = pattern.sub("<SECRET_REDACTED>", value)
    return value


def minimize_text_for_cloud(value: str) -> str:
    value = _redact_secret_patterns(value)
    value = POSIX_PATH_PATTERN.sub("<PATH_REDACTED>", value)
    value = WINDOWS_PATH_PATTERN.sub("<PATH_REDACTED>", value)
    value = EMAIL_PATTERN.sub("<EMAIL_REDACTED>", value)
    value = LABELED_IDENTITY_PATTERN.sub(
        lambda match: f"{match.group(1)}: <IDENTITY_REDACTED>", value
    )
    value = LAYER_PATTERN.sub(lambda match: f"{match.group(1)}: <LAYER_REDACTED>", value)
    value = GROUP_PATTERN.sub(lambda match: f"{match.group(1)}: <GROUP_REDACTED>", value)
    if _has_prompt_injection(value):
        return "<PROMPT_INJECTION_REDACTED>"
    return value


def minimize_for_cloud(value: Any, *, parent_key: str = "") -> Any:
    key = parent_key.lower()
    if key == "arguments" and isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            pass
        else:
            return json.dumps(
                minimize_for_cloud(decoded),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
    if key in {
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "authorization",
        "access_token",
        "refresh_token",
    } or key.endswith(("_api_key", "_secret", "_password", "_token")):
        return "<SECRET_REDACTED>"
    if key in {"layer", "layer_name", "project_layer"}:
        return "Default" if value == "Default" else "<LAYER_REDACTED>"
    if key in {"group", "groups", "group_name", "group_names"}:
        if isinstance(value, list):
            return ["<GROUP_REDACTED>" for item in value if item]
        return "<GROUP_REDACTED>" if value else value
    if key in {"customer", "customer_name", "client", "client_name", "project_name", "project_code"}:
        return "<IDENTITY_REDACTED>" if value else value
    if isinstance(value, str):
        return minimize_text_for_cloud(value)
    if isinstance(value, dict):
        return {str(item_key): minimize_for_cloud(item, parent_key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [minimize_for_cloud(item, parent_key=parent_key) for item in value]
    return value


def minimize_messages_for_cloud(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    allowed_fields = {"role", "content", "name", "tool_call_id", "tool_calls"}
    minimized: list[dict[str, Any]] = []
    for message in messages:
        row = {
            str(key): minimize_for_cloud(value, parent_key=str(key))
            for key, value in message.items()
            if key in allowed_fields
        }
        minimized.append(row)
    return minimized


def cloud_sensitive_findings(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            child = f"{path}.{key}"
            if key_lower == "arguments" and isinstance(item, str):
                try:
                    decoded = json.loads(item)
                except json.JSONDecodeError:
                    pass
                else:
                    findings.extend(cloud_sensitive_findings(decoded, path=child))
                    continue
            if key_lower in {
                "api_key",
                "apikey",
                "token",
                "secret",
                "password",
                "authorization",
                "access_token",
                "refresh_token",
            } and item not in (None, "", "<SECRET_REDACTED>"):
                findings.append(f"{child}:secret_field")
            if key_lower in {
                "customer",
                "customer_name",
                "client",
                "client_name",
                "project_name",
                "project_code",
            } and item not in (None, "", "<IDENTITY_REDACTED>"):
                findings.append(f"{child}:identity_field")
            if key_lower in {"layer", "layer_name", "project_layer"} and not isinstance(item, dict):
                if item not in (None, "", "Default", "<LAYER_REDACTED>"):
                    findings.append(f"{child}:layer_field")
            if key_lower in {"group", "groups", "group_name", "group_names"} and not isinstance(item, dict):
                values = item if isinstance(item, (list, tuple)) else [item]
                if any(value not in (None, "", "<GROUP_REDACTED>") for value in values):
                    findings.append(f"{child}:group_field")
            findings.extend(cloud_sensitive_findings(item, path=child))
        return findings
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings.extend(cloud_sensitive_findings(item, path=f"{path}[{index}]"))
        return findings
    if not isinstance(value, str):
        return findings
    scrubbed = re.sub(r"<(?:SECRET|PATH|EMAIL|IDENTITY|LAYER|GROUP|PROMPT_INJECTION)_REDACTED>", "", value)
    for code, pattern in SECRET_PATTERNS:
        if pattern.search(scrubbed):
            findings.append(f"{path}:{code}")
    for code, pattern in (
        ("local_path", POSIX_PATH_PATTERN),
        ("windows_path", WINDOWS_PATH_PATTERN),
        ("email", EMAIL_PATTERN),
        ("identity", LABELED_IDENTITY_PATTERN),
        ("layer", LAYER_PATTERN),
        ("group", GROUP_PATTERN),
    ):
        if pattern.search(scrubbed):
            findings.append(f"{path}:{code}")
    if _has_prompt_injection(scrubbed):
        findings.append(f"{path}:prompt_injection")
    return findings


def prepare_cloud_messages(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    minimized = minimize_messages_for_cloud(messages)
    findings = cloud_sensitive_findings(minimized)
    if findings:
        raise PrivacyViolation(
            "privacy.outbound_blocked",
            "模型请求在最小化后仍包含敏感数据，已阻止发送。",
            findings,
        )
    return minimized


def request_audit_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get("RHINOCODER_MODEL_REQUEST_AUDIT_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def configured_request_audit_path(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    return Path(source.get("RHINOCODER_MODEL_REQUEST_AUDIT", DEFAULT_REQUEST_AUDIT_PATH)).expanduser().resolve()


def record_model_request(
    *,
    backend: str,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]] = (),
) -> None:
    if not request_audit_enabled():
        return
    findings = cloud_sensitive_findings({"messages": messages, "tools": tools})
    if findings:
        raise PrivacyViolation(
            "privacy.outbound_audit_failed",
            "拒绝记录或发送未通过隐私审计的模型请求。",
            findings,
        )
    path = configured_request_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "request_id": str(uuid4()),
        "timestamp": _now(),
        "backend": backend,
        "model": model,
        "message_count": len(messages),
        "tool_count": len(tools),
        "content_sha256": hashlib.sha256(
            json.dumps(
                {"messages": messages, "tools": tools},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "messages": list(messages),
        "tools": list(tools),
        "privacy_findings": [],
    }
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    with _AUDIT_LOCK:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line)
        path.chmod(0o600)


def sanitize_for_log(value: Any) -> str:
    minimized = minimize_for_cloud(value)
    if isinstance(minimized, str):
        return minimized
    return json.dumps(minimized, ensure_ascii=False, sort_keys=True)


class PrivacyLogFilter(logging.Filter):
    """Render and sanitize a record before any configured handler writes it."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:
            rendered = str(record.msg)
        if record.exc_info:
            rendered = f"{rendered} [exception_type={record.exc_info[0].__name__}]"
        record.msg = sanitize_for_log(rendered)
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return True


def install_privacy_log_filter(logger: logging.Logger | None = None) -> PrivacyLogFilter:
    """Attach the privacy filter to current handlers, without duplicating it."""

    target = logger or logging.getLogger()
    privacy_filter = PrivacyLogFilter()
    for handler in target.handlers:
        if not any(isinstance(item, PrivacyLogFilter) for item in handler.filters):
            handler.addFilter(privacy_filter)
    return privacy_filter
