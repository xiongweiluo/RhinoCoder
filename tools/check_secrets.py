"""轻量仓库密钥扫描，供本地与 CI 使用。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = {".env.example"}
PATTERNS = {
    "OpenAI/DeepSeek key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "assigned API key": re.compile(
        r"(?:API_KEY|SECRET|TOKEN)\s*=\s*['\"](?!<|your-|\$\{|0\b)[A-Za-z0-9_./+=-]{12,}['\"]",
        re.IGNORECASE,
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def repository_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in completed.stdout.splitlines() if line]


def main() -> int:
    findings: list[str] = []
    for path in repository_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative in ALLOWLIST or not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if "secret-scan: allow" in line:
                continue
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{relative}:{line_no}: {label}")

    if findings:
        print("Potential secrets detected:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
