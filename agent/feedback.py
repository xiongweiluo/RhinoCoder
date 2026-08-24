"""用户反馈写入兼容入口。"""

from __future__ import annotations

from typing import Optional

from agent.runtime import utc_now
from agent.trace_store import save_feedback

VALID_LABELS = {"accepted", "partial", "rejected"}


def record_feedback(
    run_id: str,
    instruction: str,
    label: str,
    *,
    note: Optional[str] = None,
) -> None:
    if label not in VALID_LABELS:
        raise ValueError(f"label 必须是 {sorted(VALID_LABELS)}")
    save_feedback(
        {
            "run_id": run_id,
            "instruction": instruction,
            "label": label,
            "note": (note or "")[:1000],
            "timestamp": utc_now(),
        }
    )
